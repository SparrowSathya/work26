#!/bin/bash
# ============================================
#  APK Finder & Mover
#  Searches all of /sdcard for .apk files
#  and moves them to /sdcard/Apk_Files/
# ============================================

DEST="/storage/emulated/0/Apk_Files"
SOURCE="/storage/emulated/0"

# --- Colors ---
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${CYAN}==============================${NC}"
echo -e "${CYAN}   APK Finder & Mover Script  ${NC}"
echo -e "${CYAN}==============================${NC}"
echo ""

# Create destination folder if it doesn't exist
if [ ! -d "$DEST" ]; then
    mkdir -p "$DEST"
    echo -e "${GREEN}[+] Created destination folder: $DEST${NC}"
else
    echo -e "${YELLOW}[~] Destination folder already exists: $DEST${NC}"
fi

echo ""
echo -e "${CYAN}[*] Scanning for .apk files in $SOURCE ...${NC}"
echo ""

# Find all APKs (excluding the destination folder to avoid re-processing)
mapfile -t APK_LIST < <(find "$SOURCE" -path "$DEST" -prune -o -iname "*.apk" -print 2>/dev/null)

TOTAL=${#APK_LIST[@]}

if [ "$TOTAL" -eq 0 ]; then
    echo -e "${YELLOW}[!] No .apk files found outside of $DEST.${NC}"
    exit 0
fi

echo -e "${GREEN}[+] Found ${TOTAL} APK file(s). Starting move...${NC}"
echo ""

MOVED=0
SKIPPED=0
FAILED=0

for APK in "${APK_LIST[@]}"; do
    FILENAME=$(basename "$APK")
    TARGET="$DEST/$FILENAME"

    # Handle duplicate filenames
    if [ -f "$TARGET" ]; then
        echo -e "${YELLOW}  [SKIP] Already exists: $FILENAME${NC}"
        ((SKIPPED++))
        continue
    fi

    mv "$APK" "$TARGET" 2>/dev/null
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}  [MOVED] $FILENAME${NC}"
        ((MOVED++))
    else
        echo -e "${RED}  [FAIL] Could not move: $APK${NC}"
        ((FAILED++))
    fi
done

echo ""
echo -e "${CYAN}==============================${NC}"
echo -e "${GREEN}  Done!${NC}"
echo -e "  Moved  : ${GREEN}${MOVED}${NC}"
echo -e "  Skipped: ${YELLOW}${SKIPPED}${NC} (duplicates)"
echo -e "  Failed : ${RED}${FAILED}${NC}"
echo -e "${CYAN}==============================${NC}"
echo ""
echo -e "APKs saved to: ${CYAN}$DEST${NC}"
