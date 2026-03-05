#!/usr/bin/env python3
"""
Super Advanced Script Analyzer v2.0 – AI-Heuristic Edition
Optimized for Termux | Never misclassify theme scripts again!
Author: Grok (for Sparrow)
"""

import argparse
import ast
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict

# ====================== AI-HEURISTIC PURPOSE ENGINE ======================
PURPOSE_CATEGORIES = {
    "termux_theme_changer": {
        "score": 100,
        "keywords": ["colors.properties", "termux-reload-settings", "font", "theme", "property", "figlet", "toilet", "neofetch", "starship"],
        "commands": ["termux-reload-settings", "am broadcast", "termux-toast"]
    },
    "termux_utility": {
        "score": 80,
        "keywords": ["termux-", "pkg install", "termux-setup-storage", "termux-clipboard", "termux-wake-lock"],
        "commands": ["termux-"]
    },
    "compression": {
        "score": 70,
        "keywords": ["compress", "gzip", "tar", "zip", "xz", "7z", "rar"],
        "commands": ["tar", "gzip", "zip"]
    },
    "backup_sync": {
        "score": 65,
        "keywords": ["backup", "rsync", "sync", "cp -r", "mv -r"],
        "commands": ["rsync"]
    },
    "downloader": {
        "score": 60,
        "keywords": ["download", "curl", "wget", "youtube-dl", "yt-dlp"],
        "commands": ["curl", "wget", "yt-dlp"]
    },
    # Add more categories as you like...
}

def ai_detect_purpose(content: str, commands: set) -> tuple[str, str]:
    """AI-like scoring engine – picks best purpose"""
    scores = {}
    text_lower = content.lower()

    for cat_name, data in PURPOSE_CATEGORIES.items():
        score = 0
        # Keyword match
        for kw in data["keywords"]:
            score += text_lower.count(kw) * 10
        # Command match
        for cmd in data["commands"]:
            if any(c.startswith(cmd) for c in commands):
                score += 25
        scores[cat_name] = score

    if not any(scores.values()):
        return "general_utility", "→ General utility script"

    best = max(scores, key=scores.get)
    desc_map = {
        "termux_theme_changer": "Termux theme / color scheme changer",
        "termux_utility": "Termux system utility",
        "compression": "File/folder compression & archiving",
        "backup_sync": "Backup / synchronization tool",
        "downloader": "Downloader / fetcher",
    }
    return best, f"→ {desc_map.get(best, best.replace('_', ' ').title())}"


# ====================== MAIN ANALYZER ======================
def analyze_script(file_path: Path) -> Dict:
    content = file_path.read_text(encoding="utf-8", errors="replace")
    shebang = content.split("\n", 1)[0] if content.startswith("#!") else ""

    is_python = file_path.suffix.lower() == ".py" or "python" in shebang.lower()
    lang = "python" if is_python else "bash"

    report = {
        "original_name": file_path.name,
        "language": lang,
        "purpose": "Unknown",
        "purpose_category": "general",
        "features": [],
        "requirements": [],
        "security_warnings": [],
        "suggested_name": file_path.name,
        "header": "",
    }

    # Extract all commands (fast regex)
    commands = set(re.findall(r'(?:^|\s|\||;)([a-zA-Z0-9_-]{2,30})(?:\s|$|\||;)', content))

    # AI Purpose Detection (this is the magic)
    purpose_cat, purpose_text = ai_detect_purpose(content, commands)
    report["purpose_category"] = purpose_cat
    report["purpose"] = purpose_text

    if lang == "python":
        try:
            tree = ast.parse(content)
            funcs = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
            report["features"].append(f"Python functions: {len(funcs)}")
        except:
            pass

    # Termux & common features
    if "termux" in content.lower() or any(c.startswith("termux-") for c in commands):
        report["features"].append("Termux-specific script")
        report["requirements"].append("Termux environment")

    if purpose_cat == "termux_theme_changer":
        report["features"].append("Modifies \~/.termux/colors.properties or fonts")
        report["features"].append("Reloads settings with termux-reload-settings")

    report["features"].extend([f"Uses: {cmd}" for cmd in sorted(list(commands))[:8]])

    # Security
    if re.search(r"rm\s+-rf", content, re.IGNORECASE):
        report["security_warnings"].append("Dangerous rm -rf detected!")
    if re.search(r"eval\b", content, re.IGNORECASE):
        report["security_warnings"].append("eval() usage – security risk")

    # Smart name suggestion
    action = purpose_cat.replace("termux_", "").replace("_", " ")
    report["suggested_name"] = f"termux_{action}_tool.sh" if "termux" in purpose_cat else f"{purpose_cat}_script.sh"

    # Header
    header = f"""# {'='*75}
# ORIGINAL NAME   : {report['original_name']}
# SUGGESTED NAME  : {report['suggested_name']}
# PURPOSE         : {report['purpose']}
# LANGUAGE        : {lang.upper()}
# CATEGORY        : {purpose_cat.upper()}
# ANALYZED        : {datetime.now().strftime('%Y-%m-%d')}
# ANALYZER        : AI-Heuristic v2.0 (Termux Edition)
# {'='*75}
# FEATURES:
#   • {'\n#   • '.join(report['features']) if report['features'] else 'None detected'}
#
# REQUIREMENTS:
#   • {'\n#   • '.join(report['requirements']) if report['requirements'] else 'Standard shell'}
#
# SECURITY NOTES:
#   • {'\n#   • '.join(report['security_warnings']) if report['security_warnings'] else 'None detected'}
# {'='*75}
"""
    report["header"] = header
    return report


def print_report(report):
    print("═" * 85)
    print(f"  AI SCRIPT ANALYZER v2.0 → {report['original_name']}")
    print("═" * 85)
    print(f"Purpose          : {report['purpose']}")
    print(f"Suggested name   : {report['suggested_name']}")
    print("-" * 85)
    print("FEATURES:")
    for f in report["features"]:
        print(f"  • {f}")
    print("\nREQUIREMENTS:")
    for r in report["requirements"]:
        print(f"  • {r}")
    if report["security_warnings"]:
        print("\n⚠️ SECURITY WARNINGS:")
        for w in report["security_warnings"]:
            print(f"  • {w}")
    print("\n" + "─" * 85)
    print("COPY THIS HEADER TO TOP OF YOUR SCRIPT:\n")
    print(report["header"])


def add_header(file_path: Path, header: str):
    content = file_path.read_text(encoding="utf-8", errors="replace")
    if content.startswith("# ="):
        print("Header already exists.")
        return
    backup = file_path.with_suffix(".bak")
    file_path.rename(backup)
    file_path.write_text(header + "\n\n" + content, encoding="utf-8")
    print(f"✅ Header added! Backup: {backup.name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("file", type=Path)
    parser.add_argument("--add-header", "-a", action="store_true")
    args = parser.parse_args()

    if not args.file.is_file():
        print("File not found!")
        sys.exit(1)

    report = analyze_script(args.file)
    print_report(report)

    if args.add_header:
        add_header(args.file, report["header"])
