#!/data/data/com.termux/files/usr/bin/bash

MODEL="qwen2.5:0.5b"

# =========================
# 🚀 AUTO OLLAMA START + WARMUP
# =========================

# Start Ollama server if not running
if ! pgrep -f "ollama serve" >/dev/null; then
    echo "🚀 Starting Ollama server..."
    ollama serve >/dev/null 2>&1 &
    sleep 2
fi

# Warmup model (only if not already loaded recently)
WARMUP_FILE="/tmp/.dr_model_warm"

if [ ! -f "$WARMUP_FILE" ] || [ $(( $(date +%s) - $(stat -c %Y "$WARMUP_FILE" 2>/dev/null || echo 0) )) -gt 300 ]; then

    JSON=$(jq -n \
      --arg model "$MODEL" \
      '{model:$model, prompt:"hi", stream:false}')

    curl -s \
      -H "Content-Type: application/json" \
      -X POST http://localhost:11434/api/generate \
      -d "$JSON" >/dev/null 2>&1

    touch "$WARMUP_FILE"
fi

QUESTION="$*"

if [ -z "$QUESTION" ]; then
    echo "🤖 Dr Ultra: Ask something."
    exit 1
fi

# =========================
# ⚡ FAST LOCAL LOGIC
# =========================

# 1️⃣ SD Card Shortcut
if [[ "$QUESTION" == *"sdcard"* ]]; then
    match=$(grep "^alias .*cd /sdcard" ~/.bashrc 2>/dev/null | head -1)
    if [ -n "$match" ]; then
        alias_name=$(echo "$match" | cut -d'=' -f1 | sed 's/alias //')
        echo "⚡ Instant: Use shortcut → $alias_name"
    else
        echo "⚡ Instant: Use command → cd /sdcard"
    fi
    exit 0
fi

# 2️⃣ Package Count
if [[ "$QUESTION" == *"how many packages"* ]]; then
    count=$(pkg list-installed 2>/dev/null | wc -l)
    echo "⚡ Instant: You have $count packages installed."
    exit 0
fi

# 3️⃣ Show Aliases
if [[ "$QUESTION" == *"alias"* ]]; then
    echo "⚡ Instant: Your aliases:"
    grep "^alias" ~/.bashrc 2>/dev/null
    exit 0
fi

# 4️⃣ Clear Screen Help
if [[ "$QUESTION" == *"clear screen"* ]]; then
    echo "⚡ Instant: Use command → clear"
    echo "Or press Ctrl + L"
    exit 0
fi

# 5️⃣ Current Directory Help
if [[ "$QUESTION" == *"where am i"* ]]; then
    echo "⚡ Instant: Current directory → $(pwd)"
    exit 0
fi

# =========================
# 🧠 AI FALLBACK SECTION
# =========================

if ! curl -s http://localhost:11434 >/dev/null 2>&1; then
    echo "⚠ Ollama server not running."
    echo "Start it using: ollama serve"
    exit 1
fi

echo "🧠 Thinking..."

ALIASES=$(grep "^alias" ~/.bashrc 2>/dev/null | head -15)
PKGCOUNT=$(pkg list-installed 2>/dev/null | wc -l)

PROMPT="You are Dr.Termux Ultra. Keep answers short and direct.
User question: $QUESTION

Aliases:
$ALIASES

Total packages:
$PKGCOUNT
"

# Let jq safely build JSON (escapes newlines automatically)
JSON=$(jq -n \
  --arg model "$MODEL" \
  --arg prompt "$PROMPT" \
  '{model:$model, prompt:$prompt, stream:false}')

RESPONSE=$(curl -s http://localhost:11434/api/generate -d "$JSON")

AI_TEXT=$(echo "$RESPONSE" | jq -r '.response')

if [ -z "$AI_TEXT" ] || [ "$AI_TEXT" = "null" ]; then
    echo "⚠ AI parsing failed."
    echo "$RESPONSE"
else
    echo "$AI_TEXT"
fi
