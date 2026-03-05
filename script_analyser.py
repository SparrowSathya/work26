#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║         Script Analyzer v3.1  —  Termux / REST Edition      ║
║  • NO Python ollama package needed — uses Ollama REST API    ║
║  • Auto-detects running Ollama on port 11434                 ║
║  • Starts Ollama once, stays running for whole session       ║
║  • Interactive prompts only when something is missing        ║
║  • Complexity grade A–F, security scan, perf hints           ║
╚══════════════════════════════════════════════════════════════╝
Usage:
  ./script_analyzer.py <file>           basic analysis
  ./script_analyzer.py <file> --ai      AI-powered (needs ollama running)
  ./script_analyzer.py <file> --ai -a   AI + write header into file
  ./script_analyzer.py *.sh --ai        batch mode
  ./script_analyzer.py <file> --watch   re-analyze on every save
"""

import re, os, sys, time, json, signal, hashlib, argparse, subprocess
import urllib.request, urllib.error
from datetime import datetime
from pathlib import Path
from textwrap import wrap

# ── ANSI ─────────────────────────────────────────────────────
class C:
    R="\033[91m"; Y="\033[93m"; G="\033[92m"; B="\033[94m"
    M="\033[95m"; CY="\033[96m"; W="\033[97m"; DIM="\033[2m"
    BO="\033[1m"; X="\033[0m"
def col(color, text): return f"{color}{text}{C.X}"

# ── CONFIG ────────────────────────────────────────────────────
OLLAMA_MODEL    = "qwen2.5:0.5b"
OLLAMA_API      = "http://127.0.0.1:11434"
OLLAMA_SERVE    = ["ollama", "serve"]
OLLAMA_PULL     = ["ollama", "pull", OLLAMA_MODEL]

_session = {"running": False, "we_started": False, "model_ok": False}

# ═════════════════════════════════════════════════════════════
# OLLAMA — pure REST, no Python package required
# ═════════════════════════════════════════════════════════════

def _http_get(path, timeout=4):
    try:
        with urllib.request.urlopen(f"{OLLAMA_API}{path}", timeout=timeout) as r:
            return json.loads(r.read())
    except Exception:
        return None

def ollama_alive() -> bool:
    return _http_get("/api/tags", timeout=3) is not None

def model_available() -> bool:
    data = _http_get("/api/tags", timeout=5)
    if not data:
        return False
    names = [m.get("name","") for m in data.get("models",[])]
    base  = OLLAMA_MODEL.split(":")[0]
    return any(base in n for n in names)

def ollama_chat(prompt: str) -> str:
    """POST to /api/chat and return assistant text."""
    payload = json.dumps({
        "model":    OLLAMA_MODEL,
        "stream":   False,
        "messages": [{"role":"user","content":prompt}]
    }).encode()
    req = urllib.request.Request(
        f"{OLLAMA_API}/api/chat",
        data=payload,
        headers={"Content-Type":"application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read())
        return data.get("message",{}).get("content","").strip()
    except urllib.error.URLError as e:
        raise RuntimeError(f"Ollama HTTP error: {e.reason}") from e

def _ask(prompt: str) -> bool:
    while True:
        a = input(f"  {prompt} [y/n]: ").strip().lower()
        if a in ("y","yes"): return True
        if a in ("n","no"):  return False

def _run_ok(cmd, timeout=6) -> bool:
    try:
        return subprocess.run(cmd, capture_output=True, timeout=timeout).returncode == 0
    except Exception:
        return False

def _start_ollama_serve():
    """Try to start 'ollama serve' in background via common binary locations."""
    candidates = [
        ["ollama", "serve"],
        [os.path.expanduser("~/../usr/bin/ollama"), "serve"],   # Termux
        ["/usr/local/bin/ollama", "serve"],
        ["/usr/bin/ollama", "serve"],
    ]
    for cmd in candidates:
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except FileNotFoundError:
            continue
    return False

def setup_ollama() -> bool:
    """
    Pure REST-based setup — never calls 'ollama --version' or 'ollama list'.
    Works with any Ollama wrapper/TUI on Termux.
    Returns True when the API is responding and the model is available.
    """
    if _session["running"] and _session["model_ok"]:
        return True

    # ── Step 1: Is the REST API already up? ──────────────────
    if not ollama_alive():
        print(f"\n  {col(C.Y,'ℹ')}  Ollama REST API not responding on {OLLAMA_API}")
        print(f"  {col(C.DIM,'  (start it with: ollama serve  in another terminal)')}")
        if not _ask("Try to start ollama serve automatically?"):
            print(f"  {col(C.DIM,'  Start it manually, then re-run with --ai')}")
            return False
        print(f"  {col(C.CY,'⏳')} Launching ollama serve in background…")
        started = _start_ollama_serve()
        if not started:
            print(f"  {col(C.R,'✗')} Could not find ollama binary to start server.")
            print(f"  {col(C.Y,'→')} Run manually in another terminal: ollama serve")
            return False
        for i in range(12):
            time.sleep(1)
            if ollama_alive():
                print(f"  {col(C.G,'✔')} API is up after {i+1}s")
                _session["we_started"] = True
                break
        else:
            print(f"  {col(C.R,'✗')} API still not responding after 12s.")
            print(f"  {col(C.Y,'→')} Run manually in another terminal: ollama serve")
            return False

    # ── Step 2: Is the model available? ──────────────────────
    if not model_available():
        print(f"\n  {col(C.Y,'ℹ')}  Model {col(C.W,OLLAMA_MODEL)} not found in Ollama (~2 GB download).")
        if not _ask(f"Pull {OLLAMA_MODEL} now?"):
            print(f"  {col(C.DIM,'AI disabled — run: ollama pull '+OLLAMA_MODEL)}")
            return False
        print(f"  {col(C.CY,'⏳')} Pulling {OLLAMA_MODEL} (this may take several minutes)…")
        # Pull via REST stream so we see progress without spawning ollama binary
        pull_payload = json.dumps({"name": OLLAMA_MODEL}).encode()
        pull_req = urllib.request.Request(
            f"{OLLAMA_API}/api/pull",
            data=pull_payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(pull_req, timeout=900) as resp:
                last_status = ""
                for raw_line in resp:
                    try:
                        d = json.loads(raw_line)
                        status = d.get("status","")
                        if status != last_status:
                            print(f"  {col(C.DIM,'  '+status)}")
                            last_status = status
                    except Exception:
                        pass
            if model_available():
                print(f"  {col(C.G,'✔')} Model ready.")
            else:
                print(f"  {col(C.R,'✗')} Pull completed but model not detected.")
                return False
        except Exception as e:
            print(f"  {col(C.R,'✗')} Pull failed: {e}")
            return False

    _session["running"]  = True
    _session["model_ok"] = True
    print(f"  {col(C.G,'✔')} Ollama ready  ({col(C.W,OLLAMA_MODEL)})")
    return True

def session_cleanup():
    if _session["we_started"] and ollama_alive():
        print(f"\n  {col(C.DIM,'Session done.')}", end=" ")
        if _ask("Stop ollama serve?"):
            # Kill by port since we can't rely on 'ollama serve' process name
            _run_ok(["pkill","-f","ollama serve"], timeout=4)
            _run_ok(["fuser","-k","11434/tcp"], timeout=4)
            print(f"  {col(C.G,'✔')} Stopped.")
        else:
            print(f"  {col(C.DIM,'Left running.')}")

# ═════════════════════════════════════════════════════════════
# KNOWLEDGE BASE
# ═════════════════════════════════════════════════════════════

CATEGORIES = {
    "web":        ["curl","wget","requests","httpx","aiohttp","flask","django","fastapi","nginx","apache"],
    "file_mgmt":  ["shutil","pathlib","cp","mv","rm","find","rsync","tar","zip","glob"],
    "data":       ["pandas","csv","json","sqlite","mysql","psql","numpy","parquet","xlsx","polars"],
    "devops":     ["docker","kubectl","terraform","ansible","git","ssh","systemd","cron","helm"],
    "security":   ["hashlib","ssl","openssl","gpg","iptables","ufw","nmap","chmod","cryptography"],
    "media":      ["ffmpeg","convert","imagemagick","pillow","cv2","sox","vlc","moviepy"],
    "system":     ["psutil","subprocess","os","sys","signal","proc","top","htop","systemctl"],
    "network":    ["socket","paramiko","netstat","ping","traceroute","ifconfig","ip","scapy"],
    "text":       ["re","sed","awk","grep","diff","jq","xmllint","pandoc","nltk","spacy"],
    "ai_ml":      ["torch","tensorflow","sklearn","ollama","openai","transformers","llm","keras"],
    "backup":     ["rsync","borgbackup","tar","rclone","backup","snapshot","restic"],
    "monitoring": ["prometheus","grafana","alert","notify","log","journalctl","watch","sentry"],
    "automation": ["selenium","playwright","pyautogui","schedule","apscheduler","crontab"],
    "testing":    ["pytest","unittest","mock","hypothesis","coverage","tox","doctest"],
}

PKG_HINTS = {
    "requests":"pip install requests","httpx":"pip install httpx","aiohttp":"pip install aiohttp",
    "flask":"pip install flask","fastapi":"pip install fastapi uvicorn","django":"pip install django",
    "pandas":"pip install pandas","numpy":"pip install numpy","polars":"pip install polars",
    "psutil":"pip install psutil","paramiko":"pip install paramiko","pillow":"pip install Pillow",
    "cv2":"pip install opencv-python","torch":"pip install torch","tensorflow":"pip install tensorflow",
    "sklearn":"pip install scikit-learn","ollama":"pip install ollama","openai":"pip install openai",
    "transformers":"pip install transformers","bs4":"pip install beautifulsoup4",
    "sqlalchemy":"pip install sqlalchemy","cryptography":"pip install cryptography",
    "selenium":"pip install selenium","playwright":"pip install playwright",
    "pytest":"pip install pytest","hypothesis":"pip install hypothesis",
    "schedule":"pip install schedule","pexpect":"pip install pexpect",
    "rich":"pip install rich","typer":"pip install typer","click":"pip install click",
    "pydantic":"pip install pydantic",
    "jq":"apt/pkg install jq","ffmpeg":"apt/pkg install ffmpeg",
    "rsync":"apt/pkg install rsync","curl":"apt/pkg install curl",
    "wget":"apt/pkg install wget","nmap":"apt/pkg install nmap",
    "rclone":"apt/pkg install rclone","git":"apt/pkg install git",
}

SECURITY_PATTERNS = [
    (r'(?i)(password|passwd|secret|api_key|token|private_key)\s*=\s*["\'][^"\']{4,}',
     "CRITICAL","Hardcoded credential"),
    (r'\beval\s*\(',"HIGH","eval() — arbitrary code execution risk"),
    (r'subprocess\.(call|run|Popen).*shell\s*=\s*True',"HIGH","shell=True in subprocess — injection risk"),
    (r'os\.system\s*\(',"MEDIUM","os.system() — prefer subprocess"),
    (r'pickle\.(load|loads)\s*\(',"HIGH","Unsafe pickle deserialization"),
    (r'yaml\.load\s*\([^)]*\)',"MEDIUM","yaml.load() without Loader — use safe_load"),
    (r'(?i)hashlib\.md5',"LOW","MD5 is cryptographically weak"),
    (r'http://(?!localhost|127\.)',"LOW","Plain HTTP (unencrypted) URL"),
    (r'chmod\s+[0-7]*7[0-7][0-7]',"MEDIUM","World-writable file permissions"),
    (r'rm\s+-rf\b|shutil\.rmtree',"MEDIUM","Destructive file removal"),
    (r'except\s*:',"LOW","Bare except swallows all errors"),
    (r'tempfile\.mktemp\b',"MEDIUM","mktemp() race condition — use mkstemp()"),
]

PERF_PATTERNS = [
    (r'for\s+\w+\s+in\s+range\(len\(',
     "range(len(x)) loop","Use 'for item in x' or enumerate(x) instead"),
    (r'(?m)^\s.*\.append\(',
     "list.append() in loop","Consider list comprehension for bulk inserts"),
    (r'["\'][^"\']*["\'\s]*\+[^+\n]{0,40}\+',
     "String concatenation","Use f-strings or ''.join() — + in loops is O(n²)"),
    (r'time\.sleep\(\s*[0-9]',
     "Blocking sleep","Use asyncio.sleep() for async code"),
    (r'SELECT\s+\*\s+FROM',
     "SELECT * query","Select only needed columns"),
    (r'\.read\(\)',
     "Full file read","Read line-by-line or in chunks for large files"),
    (r'(?i)\bglobal\s+\w+',
     "Global variable","Global state causes coupling — prefer function params"),
    (r'requests\.(get|post|put|delete)\(',
     "Synchronous HTTP","Use httpx async or a session pool for multiple requests"),
]

# ═════════════════════════════════════════════════════════════
# AI PURPOSE DETECTION
# ═════════════════════════════════════════════════════════════

def ai_purpose(raw: str, commands: set, lang: str) -> tuple:
    if _session["running"] and _session["model_ok"]:
        snippet = raw[:2000]
        prompt = (
            f"You are a senior {lang} engineer. Analyze this {lang} script.\n"
            f"Reply with EXACTLY two lines:\n"
            f"LINE1: category — one of: web data devops security media system "
            f"network text ai_ml backup monitoring automation testing file_mgmt other\n"
            f"LINE2: One sentence (max 25 words) — what does this script do?\n\n"
            f"```{lang}\n{snippet}\n```"
        )
        try:
            resp  = ollama_chat(prompt)
            lines = resp.splitlines()
            cat   = lines[0].strip().lower() if lines else "other"
            purp  = lines[1].strip() if len(lines) > 1 else "Purpose identified by AI."
            if cat not in CATEGORIES: cat = "other"
            return cat, purp
        except Exception as e:
            print(f"  {col(C.Y,'⚠')} AI inference error: {e} — using heuristics")

    # heuristic fallback
    raw_low = raw.lower()
    scores  = {cat: sum(1 for kw in kws if kw in commands or kw in raw_low)
               for cat, kws in CATEGORIES.items()}
    scores  = {k:v for k,v in scores.items() if v}
    cat     = max(scores, key=scores.get) if scores else "other"
    top     = [kw for kw in CATEGORIES.get(cat,[]) if kw in commands or kw in raw_low][:4]
    purp    = (f"A {lang} {cat.replace('_',' ')} script using {', '.join(top)}."
               if top else f"A general-purpose {lang} script.")
    return cat, purp

# ═════════════════════════════════════════════════════════════
# ANALYSIS FUNCTIONS
# ═════════════════════════════════════════════════════════════

def detect_features(raw, lang):
    checks = {
        "Argument parsing":        r'argparse|getopts|\$1|\$@|click\.|typer\.',
        "File I/O":                r'open\s*\(|read_text|write_text|fopen|cat |tee ',
        "Networking / HTTP":       r'requests\.|httpx\.|curl |wget |socket\.|aiohttp',
        "Subprocess / shell":      r'subprocess\.|os\.system|popen|\$\(',
        "Regex usage":             r're\.|grep |sed |awk ',
        "Logging":                 r'logging\.|logger\.|loguru|journalctl',
        "Error handling":          r'try:|except |trap |set -e',
        "Async / concurrent":      r'async def|asyncio\.|threading\.|multiprocessing\.| &$',
        "Config / env vars":       r'os\.environ|dotenv|\.env|getenv|\$[A-Z_]{3,}',
        "AI / LLM":                r'ollama|openai|transformers|llm|gpt|anthropic',
        "Database":                r'sqlite|mysql|psql|sqlalchemy|\.execute\(',
        "Scheduling":              r'cron|schedule\.|apscheduler|watch ',
        "Unit testing":            r'pytest|unittest|def test_',
        "Type annotations":        r':\s*(int|str|float|bool|list|dict|Optional|Union)\b|->',
        "Context managers":        r'\bwith\s+open|\bwith\s+\w+\(',
        "Hashing / crypto":        r'hashlib\.|hmac\.|cryptography\.|ssl\.',
        "JSON / YAML":             r'json\.|yaml\.|toml\.',
        "Compression":             r'zipfile|tarfile|gzip|bz2|lzma',
        "CLI color output":        r'rich\.|colorama|\033\[',
        "Data classes":            r'@dataclass|BaseModel|pydantic',
    }
    return [n for n,p in checks.items() if re.search(p, raw, re.IGNORECASE)]

def complexity_score(raw, lang):
    lines = raw.splitlines()
    kw    = (r'\b(if|elif|for|while|except|and|or|with|match|case)\b'
             if lang=="python" else r'\b(if|elif|for|while|case|&&|\|\|)\b')
    decisions    = len(re.findall(kw, raw))
    functions    = len(re.findall(r'^\s*def\s+\w+' if lang=="python"
                                  else r'^\s*\w+\s*\(\s*\)\s*\{', raw, re.MULTILINE))
    classes      = len(re.findall(r'^\s*class\s+\w+', raw, re.MULTILINE))
    nested       = len(re.findall(r'^\s{8,}def\s+', raw, re.MULTILINE))
    code_lines   = [l for l in lines if l.strip() and not l.strip().startswith(("#","//"))]
    comment_lns  = [l for l in lines if l.strip().startswith(("#","//","/*","*"))]
    avg_len      = sum(len(l) for l in code_lines) / max(len(code_lines),1)
    max_ind      = max((len(l)-len(l.lstrip()) for l in code_lines), default=0)
    comm_ratio   = len(comment_lns) / max(len(lines),1)
    cyclomatic   = decisions + 1

    score = 100
    score -= min(cyclomatic * 1.2, 35)
    score -= min(nested * 5, 20)
    score -= min(max(avg_len - 60, 0), 15)
    score -= min(max(max_ind - 16, 0) * 0.5, 10)
    score += min(comm_ratio * 40, 12)
    score += min(functions * 2, 10)
    score = max(0, min(100, round(score)))

    grade, label = (("A","Excellent") if score>=90 else ("B","Good") if score>=80 else
                    ("C","Acceptable") if score>=70 else ("D","Needs Work") if score>=55 else
                    ("E","Poor") if score>=40 else ("F","Critical"))
    return dict(score=score, grade=grade, label=label, cyclomatic=cyclomatic,
                functions=functions, classes=classes, nested=nested,
                comment_ratio=round(comm_ratio*100,1), avg_line=round(avg_len,1),
                max_indent=max_ind, total=len(lines), code=len(code_lines),
                comments=len(comment_lns), blank=len([l for l in lines if not l.strip()]))

def security_scan(raw):
    out = []
    for no, line in enumerate(raw.splitlines(), 1):
        for pat, sev, desc in SECURITY_PATTERNS:
            if re.search(pat, line, re.IGNORECASE):
                out.append({"line":no,"sev":sev,"desc":desc,"snippet":line.strip()[:80]})
    return out

def perf_scan(raw, lang):
    if lang != "python": return []
    return [{"title":t,"tip":tip}
            for pat,t,tip in PERF_PATTERNS if re.search(pat, raw, re.IGNORECASE|re.MULTILINE)]

def detect_requirements(raw, lang):
    STDLIB = {
        "re","os","sys","time","datetime","pathlib","subprocess","argparse","json","csv",
        "math","random","string","collections","itertools","functools","threading",
        "multiprocessing","asyncio","socket","struct","hashlib","hmac","base64","io",
        "tempfile","shutil","glob","stat","signal","logging","unittest","typing","enum",
        "dataclasses","copy","textwrap","pprint","traceback","warnings","contextlib",
        "abc","ast","inspect","importlib","platform","getpass","configparser","pickle",
        "shelve","queue","heapq","bisect","weakref","gc","ctypes","urllib",
    }
    if lang == "python":
        imps = re.findall(r'^\s*(?:import|from)\s+([a-zA-Z0-9_]+)', raw, re.MULTILINE)
        return list(dict.fromkeys(
            PKG_HINTS.get(i, f"pip install {i}") for i in set(imps) if i not in STDLIB
        ))
    else:
        return list(dict.fromkeys(
            PKG_HINTS[t] for t in PKG_HINTS if re.search(rf'\b{re.escape(t)}\b', raw)
        ))

def misc_warnings(raw, lang):
    w = []
    if not raw.startswith("#!"):
        w.append("Missing shebang line")
    if re.search(r'TODO|FIXME|HACK|XXX', raw, re.IGNORECASE):
        w.append("Unresolved TODO/FIXME markers in code")
    if lang=="python" and not re.search(r'if\s+__name__\s*==\s*["\']__main__', raw):
        w.append("No __main__ guard — add for importability")
    if re.search(r'\t', raw):
        w.append("Tab characters found — mixed indentation risk")
    if max((len(l) for l in raw.splitlines()), default=0) > 120:
        w.append("Lines > 120 chars detected")
    return w

def build_suggestions(features, sec, perf, cx, lang):
    s, py, sh = [], lang=="python", lang=="bash"
    if "Error handling" not in features:
        s.append("Add try/except (Python) or set -euo pipefail + trap ERR (Bash)" if py or sh
                 else "Add error handling")
    if "Logging" not in features:
        s.append("Use logging module instead of print()" if py
                 else "Add a log() function writing to stderr or a logfile")
    if "Argument parsing" not in features:
        s.append("Add argparse/click for flexible CLI arguments" if py
                 else "Use getopts for flag/argument handling")
    if py and "Type annotations" not in features:
        s.append("Add type hints — improves IDE support and catches bugs with mypy")
    if py and "Unit testing" not in features:
        s.append("Add pytest tests for critical functions")
    if sh and cx["functions"] == 0:
        s.append("Wrap logic in functions (e.g. main()) for readability")
    if sh and "Unit testing" not in features:
        s.append("Consider bats-core for bash unit testing")
    if cx["comment_ratio"] < 10:
        s.append(f"Comment ratio {cx['comment_ratio']}% is low — aim for ≥15%")
    if cx["cyclomatic"] > 20:
        s.append(f"Cyclomatic complexity {cx['cyclomatic']} is high — split into smaller functions")
    if any(f["sev"]=="CRITICAL" for f in sec):
        s.append("🚨 CRITICAL security issues found — fix before deployment")
    if len(perf) >= 3:
        s.append("Multiple performance anti-patterns — profile with cProfile before optimizing")
    return s

# ═════════════════════════════════════════════════════════════
# MAIN ANALYZE
# ═════════════════════════════════════════════════════════════

def analyze(file: Path, use_ai: bool) -> dict:
    raw    = file.read_text(encoding="utf-8", errors="replace")
    shebang= raw.split("\n",1)[0].lower() if raw.startswith("#!") else ""
    lang   = "python" if (file.suffix==".py" or "python" in shebang) else "bash"
    cmds   = set(re.findall(r'(?:^|\s|\||;)([a-z][a-z0-9_-]{1,29})(?:\s|$|\||;)',
                            raw.lower(), re.MULTILINE))
    cat, purp = ai_purpose(raw, cmds, lang)
    cx        = complexity_score(raw, lang)
    feats     = detect_features(raw, lang)
    reqs      = detect_requirements(raw, lang)
    sec       = security_scan(raw)
    perf      = perf_scan(raw, lang)
    warns     = misc_warnings(raw, lang)
    suggs     = build_suggestions(feats, sec, perf, cx, lang)
    return dict(
        filename=file.name, filepath=str(file.resolve()), language=lang,
        category=cat, purpose=purp, features=feats, requirements=reqs,
        warnings=warns, security=sec, performance=perf, complexity=cx,
        suggestions=suggs, analyzed_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        ai_used=(_session["running"] and _session["model_ok"]),
        file_hash=hashlib.md5(raw.encode()).hexdigest()[:8],
    )

# ═════════════════════════════════════════════════════════════
# OUTPUT
# ═════════════════════════════════════════════════════════════

SEV_COL = {"CRITICAL":C.M,"HIGH":C.R,"MEDIUM":C.Y,"LOW":C.B}
GRD_COL = {"A":C.G,"B":C.G,"C":C.CY,"D":C.Y,"E":C.R,"F":C.R}

def pbar(score, w=30):
    f = round(score/100*w)
    k = C.G if score>=80 else C.Y if score>=55 else C.R
    return f"{k}{'█'*f}{'░'*(w-f)}{C.X} {score}/100"

def print_result(r):
    cx  = r["complexity"]
    gc  = GRD_COL.get(cx["grade"], C.W)
    SEP = col(C.B,"─"*64)
    DSP = col(C.B,"═"*64)

    print(f"\n{DSP}")
    print(f"  {col(C.BO+C.CY,'Script Analyzer v3.1')}  {col(C.DIM,'|')}  "
          f"{col(C.W,r['filename'])}  {col(C.DIM,r['file_hash'])}")
    print(DSP)
    print(f"  {col(C.CY,'Language')}  : {r['language'].capitalize()}")
    print(f"  {col(C.CY,'Category')}  : {r['category'].replace('_',' ').title()}")
    print(f"  {col(C.CY,'Purpose')}   : {r['purpose']}")
    print(f"  {col(C.CY,'AI engine')} : "
          +(col(C.G,f"✔ {OLLAMA_MODEL}") if r["ai_used"] else col(C.DIM,"heuristics")))
    print()

    print(SEP)
    print(f"  {col(C.BO,'CODE QUALITY')}  {col(gc,cx['grade'])} — {col(gc,cx['label'])}")
    print(f"  {pbar(cx['score'])}")
    print()
    print(f"  Lines   total {cx['total']}  code {cx['code']}  "
          f"comments {cx['comments']}  blank {cx['blank']}")
    print(f"  Cyclomatic complexity : {cx['cyclomatic']}"
          +(col(C.R,"  ⚠ high") if cx['cyclomatic']>20 else ""))
    print(f"  Functions / Classes  : {cx['functions']} / {cx['classes']}"
          +(f"  ({cx['nested']} nested)" if cx['nested'] else ""))
    print(f"  Comment ratio        : {cx['comment_ratio']}%"
          +(col(C.Y,"  ⚠ low") if cx['comment_ratio']<10 else ""))
    print(f"  Avg line length      : {cx['avg_line']} chars"
          +(col(C.Y,"  ⚠") if cx['avg_line']>80 else ""))
    print()

    if r["features"]:
        print(SEP)
        print(f"  {col(C.BO,'FEATURES')}  ({len(r['features'])})")
        items = r["features"]
        for i in range(0, len(items), 2):
            row = items[i:i+2]
            print("  "+"   ".join(f"{col(C.G,'✔')} {x:<36}" for x in row))
        print()

    print(SEP)
    sec = r["security"]
    if sec:
        print(f"  {col(C.BO,'SECURITY')}  {col(C.R,str(len(sec))+' issue(s)')}")
        for f in sec:
            sc = SEV_COL.get(f["sev"],C.W)
            print(f"  {col(sc,f['sev'][:4])}  line {f['line']:<5} {f['desc']}")
            print(f"       {col(C.DIM,f['snippet'])}")
    else:
        print(f"  {col(C.BO,'SECURITY')}  {col(C.G,'✔ No issues found')}")
    print()

    print(SEP)
    perf = r["performance"]
    if perf:
        print(f"  {col(C.BO,'PERFORMANCE')}  ({len(perf)} pattern(s))")
        for p in perf:
            print(f"  {col(C.Y,'⚡')} {col(C.W,p['title'])}")
            for ln in wrap(p["tip"], 56):
                print(f"     {col(C.DIM,ln)}")
    else:
        print(f"  {col(C.BO,'PERFORMANCE')}  {col(C.G,'✔ No anti-patterns detected')}")
    print()

    if r["requirements"]:
        print(SEP)
        print(f"  {col(C.BO,'REQUIREMENTS')}")
        for req in r["requirements"]:
            print(f"  {col(C.CY,'📦')} {req}")
        print()

    if r["warnings"]:
        print(SEP)
        print(f"  {col(C.BO,'WARNINGS')}")
        for w in r["warnings"]:
            print(f"  {col(C.Y,'⚠')}  {w}")
        print()

    if r["suggestions"]:
        print(SEP)
        print(f"  {col(C.BO,'SUGGESTIONS')}")
        for i,s in enumerate(r["suggestions"],1):
            lines = wrap(s, 57)
            print(f"  {col(C.M,str(i)+'.')} {lines[0]}")
            for ln in lines[1:]:
                print(f"     {ln}")
        print()

    print(DSP)
    print(f"  {r['analyzed_at']}  {col(C.DIM,'|')}  "
          f"AI: {'on — '+OLLAMA_MODEL if r['ai_used'] else 'off (heuristics)'}\n")

def build_header(r):
    cx = r["complexity"]
    s  = f"# {'═'*60}"
    def row(k,v): return f"#  {k:<18} {v}"
    lines = [s,
             row("Script:",r["filename"]),
             row("Language:",r["language"].capitalize()),
             row("Category:",r["category"].replace("_"," ").title()),
             row("Purpose:",r["purpose"]),
             row("Quality:",f"{cx['grade']} — {cx['label']} ({cx['score']}/100)"),
             row("Analyzed:",r["analyzed_at"]),
             row("AI used:","Yes ("+OLLAMA_MODEL+")" if r["ai_used"] else "No (heuristics)")]
    if r["requirements"]:
        lines.append(row("Requires:"," | ".join(r["requirements"][:3])))
    crit = [f for f in r["security"] if f["sev"] in ("CRITICAL","HIGH")]
    if crit:
        lines.append(row("⚠ Security:",f"{len(crit)} HIGH/CRITICAL issue(s)"))
    lines.append(s)
    return "\n".join(lines)+"\n"

# ═════════════════════════════════════════════════════════════
# WATCH MODE
# ═════════════════════════════════════════════════════════════

def watch_mode(file: Path, use_ai: bool):
    print(f"\n  {col(C.CY,'👁')} Watch mode — {file.name}  (Ctrl+C to stop)\n")
    last = None
    try:
        while True:
            h = hashlib.md5(file.read_bytes()).hexdigest()
            if h != last:
                last = h
                print_result(analyze(file, use_ai))
            time.sleep(2)
    except KeyboardInterrupt:
        print(f"\n  {col(C.DIM,'Watch stopped.')}")

# ═════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(description="Script Analyzer v3.1")
    ap.add_argument("files", type=Path, nargs="+")
    ap.add_argument("-a","--add-header", action="store_true")
    ap.add_argument("--ai",   action="store_true",
                    help=f"Use {OLLAMA_MODEL} via Ollama REST API")
    ap.add_argument("--watch",action="store_true",
                    help="Re-analyze on every file save")
    ap.add_argument("--no-color",action="store_true")
    args = ap.parse_args()

    if args.no_color:
        for a in vars(C):
            if not a.startswith("_"): setattr(C,a,"")

    signal.signal(signal.SIGINT,  lambda s,f: (session_cleanup(), sys.exit(0)))
    signal.signal(signal.SIGTERM, lambda s,f: (session_cleanup(), sys.exit(0)))

    files = [f for f in args.files if f.is_file()]
    if not files:
        print(f"  {col(C.R,'✗')} No valid files found.")
        sys.exit(1)

    # Setup AI once at start of session
    if args.ai:
        setup_ollama()

    if len(files) > 1:
        print(f"\n  {col(C.CY,'Batch mode')} — {len(files)} file(s)\n")

    for file in files:
        if args.watch and len(files)==1:
            watch_mode(file, args.ai)
        else:
            result = analyze(file, args.ai)
            print_result(result)
            if args.add_header:
                header   = build_header(result)
                original = file.read_text(encoding="utf-8",errors="replace")
                if "Script Analyzer" in original[:400]:
                    print(f"  {col(C.DIM,'ℹ Header already present.')}\n")
                else:
                    file.write_text(header+original, encoding="utf-8")
                    print(f"  {col(C.G,'✔')} Header written to {file}\n")

    session_cleanup()

if __name__ == "__main__":
    main()
