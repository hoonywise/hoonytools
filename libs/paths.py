from pathlib import Path
import sys


def _find_project_root():
    """Find the project root by looking for app markers, not by folder name.

    Start from the libs/ directory (where this file lives) and walk upward until
    we find a directory that clearly looks like the release root:
    - contains HoonyTools.pyw or HoonyTools.exe, OR
    - contains both assets/ and libs/, OR
    - contains both loaders/ and tools/

    If no markers are found, fall back to the parent of libs/ as a safe default.
    """
    p = Path(__file__).resolve().parent
    while True:
        # Launcher file (pyw) or exe indicates root
        if (p / "HoonyTools.pyw").exists() or (p / "HoonyTools.exe").exists():
            return p

        # Standard release layout indicator
        if (p / "assets").is_dir() and (p / "libs").is_dir():
            return p

        # Alternative layout indicator
        if (p / "loaders").is_dir() and (p / "tools").is_dir():
            return p

        # Stop at filesystem root
        if p.parent == p:
            # fallback: use project folder above libs/
            return Path(__file__).resolve().parent.parent

        p = p.parent


def is_frozen():
    return getattr(sys, "frozen", False)


def get_assets_path():
    """Return the path where assets live.

    - When frozen, PyInstaller exposes bundled data under sys._MEIPASS.
    - Otherwise, use the marker-based project root.
    """
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path()))
    return _find_project_root()


def get_project_path():
    """Return the project path used for writing logs/config.

    - When frozen, use the exe's parent folder.
    - Otherwise, use the marker-based project root.
    """
    if is_frozen():
        return Path(sys.executable).parent
    return _find_project_root()


# Convenience aliases that match the original config.py API
ASSETS_PATH = get_assets_path()
PROJECT_PATH = get_project_path()
