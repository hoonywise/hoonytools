#!/usr/bin/env bash
set -euo pipefail

echo ""
echo "HoonyTools Build Script (macOS/Linux)"
echo "--------------------------------------"
echo "Python version in use:"
python3 --version

SOURCE_DIR="$(cd "$(dirname "$0")" && pwd)/"

echo "Terminating any running HoonyTools processes..."
pkill -f HoonyTools 2>/dev/null || true

echo "Cleaning previous build folders..."
rm -f HoonyTools.spec 2>/dev/null || true
rm -rf build 2>/dev/null || true
rm -rf dist 2>/dev/null || true

# Use HoonyTools.pyw as the launcher
LAUNCHER="${SOURCE_DIR}HoonyTools.pyw"
if [ ! -f "$LAUNCHER" ]; then
    echo "Launcher script not found: HoonyTools.pyw"
    exit 1
fi

# Build add-data options dynamically (only include folders that exist)
# macOS/Linux uses : as separator (Windows uses ;)
ADDS=""
[ -d "${SOURCE_DIR}assets" ]  && ADDS="$ADDS --add-data assets:assets"
[ -d "${SOURCE_DIR}libs" ]    && ADDS="$ADDS --add-data libs:libs"
[ -d "${SOURCE_DIR}loaders" ] && ADDS="$ADDS --add-data loaders:loaders"
[ -d "${SOURCE_DIR}tools" ]   && ADDS="$ADDS --add-data tools:tools"

# Locate PyInstaller (prefer installed CLI then python -m)
if command -v pyinstaller &>/dev/null; then
    PYINST_CMD="pyinstaller"
else
    echo "PyInstaller not on PATH, will use 'python3 -m PyInstaller'"
    PYINST_CMD="python3 -m PyInstaller"
fi

# Resolve icon path — .ico is Windows-only; use .png on macOS/Linux if available
ICON_ARG=""
if [ "$(uname)" = "Darwin" ]; then
    # macOS: use .icns if available, otherwise skip
    ICON_PATH="${SOURCE_DIR}assets/hoonywise_gui.icns"
    if [ -f "$ICON_PATH" ]; then
        ICON_ARG="--icon=$ICON_PATH"
    else
        echo "Note: No .icns icon found — building without embedded icon"
    fi
else
    # Linux: .ico works with PyInstaller on Linux too
    ICON_PATH="${SOURCE_DIR}assets/hoonywise_gui.ico"
    if [ -f "$ICON_PATH" ]; then
        ICON_ARG="--icon=$ICON_PATH"
    else
        echo "Note: No .ico icon found — building without embedded icon"
    fi
fi

echo "Building with $PYINST_CMD ..."
echo "Command: $PYINST_CMD --noconfirm --windowed --onefile --name HoonyTools $ICON_ARG $ADDS \"$LAUNCHER\""
$PYINST_CMD --noconfirm --windowed --onefile --name HoonyTools $ICON_ARG $ADDS "$LAUNCHER"

echo ""
# Clean up spec file if build succeeded
if [ -f "${SOURCE_DIR}dist/HoonyTools" ] || [ -f "${SOURCE_DIR}dist/HoonyTools.app" ]; then
    if [ -f "${SOURCE_DIR}HoonyTools.spec" ]; then
        rm -f "${SOURCE_DIR}HoonyTools.spec"
        echo "Removed HoonyTools.spec"
    fi
else
    echo "Warning: HoonyTools binary not found in dist/ — leaving HoonyTools.spec for inspection."
fi

echo "Build finished. Check dist/ for HoonyTools (if created)."
