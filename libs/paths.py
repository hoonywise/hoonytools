from pathlib import Path
import sys

PROJECT_NAME = "HoonyTools"

def _find_project_root():
    p = Path(__file__).resolve()
    # Climb until we find the project folder named PROJECT_NAME
    while p.name != PROJECT_NAME and p.parent != p:
        p = p.parent
    return p

def is_frozen():
    return getattr(sys, "frozen", False)

def get_assets_path():
    # When bundled by PyInstaller, resources live under _MEIPASS
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path()))
    return _find_project_root()

def get_project_path():
    # When frozen, the exe's parent directory is the project path
    if is_frozen():
        return Path(sys.executable).parent
    return _find_project_root()

# Convenience aliases that match the original config.py API
ASSETS_PATH = get_assets_path()
PROJECT_PATH = get_project_path()
