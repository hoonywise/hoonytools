#!/usr/bin/env python3
"""
HoonyTools Build & Package Script (Cross-Platform)

Usage:
    python build_pkg.py 2.2.2              Build EXE + package source ZIP (most common)
    python build_pkg.py exe                Build PyInstaller binary only
    python build_pkg.py 2.2.2 --mode package   Package source ZIP only (skip EXE build)

Replaces the platform-specific build_exe.bat, build_exe.sh, and build_pkg.bat
with a single cross-platform Python script using only stdlib modules.
"""

import argparse
import os
import platform
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SOURCE_DIR = Path(__file__).resolve().parent

FOLDERS_TO_COPY = ["assets", "libs", "loaders", "tools"]

FILES_TO_COPY = [
    "HoonyTools.pyw",
    "README.md",
    "LICENSE.md",
    "CHANGELOG.md",
    "requirements.txt",
]

# Patterns to remove from the staging directory before zipping
CLEANUP_DIRS = ["__pycache__"]
CLEANUP_FILES = [".gitkeep", "*.pyc"]
CLEANUP_SPECIFIC = [Path("libs") / "config.ini"]

IS_WINDOWS = sys.platform.startswith("win")
IS_MACOS = sys.platform == "darwin"

PYTHON = sys.executable


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _print_header(title: str) -> None:
    print(f"\n{'=' * 50}")
    print(f"  {title}")
    print(f"{'=' * 50}\n")


def _print_step(msg: str) -> None:
    print(f"  -> {msg}")


def kill_running_processes() -> None:
    """Best-effort kill of any running HoonyTools processes."""
    _print_step("Terminating any running HoonyTools processes...")
    try:
        if IS_WINDOWS:
            subprocess.run(
                ["taskkill", "/f", "/im", "HoonyTools.exe"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        else:
            subprocess.run(
                ["pkill", "-f", "HoonyTools"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
    except FileNotFoundError:
        pass  # taskkill/pkill not available — skip silently


def clean_build_dirs() -> None:
    """Remove previous build artifacts."""
    _print_step("Cleaning previous build folders...")
    for name in ["build", "dist"]:
        d = SOURCE_DIR / name
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
    spec = SOURCE_DIR / "HoonyTools.spec"
    if spec.exists():
        spec.unlink()


def find_pyinstaller() -> list[str]:
    """Return the command list to invoke PyInstaller."""
    if shutil.which("pyinstaller"):
        return ["pyinstaller"]
    _print_step("PyInstaller not on PATH — using 'python -m PyInstaller'")
    return [PYTHON, "-m", "PyInstaller"]


def get_add_data_sep() -> str:
    """Return the --add-data separator for the current platform."""
    # PyInstaller uses ; on Windows and : on macOS/Linux
    return ";" if IS_WINDOWS else ":"


def get_icon_arg() -> list[str]:
    """Return the --icon argument for PyInstaller, or [] if no icon found."""
    if IS_MACOS:
        icns = SOURCE_DIR / "assets" / "hoonywise_gui.icns"
        if icns.exists():
            return [f"--icon={icns}"]
        _print_step("No .icns icon found — building without embedded icon")
        return []

    # Windows and Linux both accept .ico
    ico = SOURCE_DIR / "assets" / "hoonywise_gui.ico"
    if ico.exists():
        return [f"--icon={ico}"]
    _print_step("No .ico icon found — building without embedded icon")
    return []


def sanitize_version(raw: str) -> str:
    """
    Validate and normalize a version string.
    Strips leading 'v'/'V' and whitespace, then validates X.Y.Z format.
    """
    cleaned = raw.strip().lstrip("vV").strip()
    if not re.match(r"^\d+\.\d+\.\d+", cleaned):
        print(f"\n  ERROR: Invalid version format: '{raw}'")
        print("  Expected format: X.Y.Z (e.g., 2.2.2)")
        sys.exit(1)
    return cleaned


def prompt_version() -> str:
    """Interactively prompt for a version number."""
    try:
        raw = input("  Enter version number (e.g., 2.2.2): ")
    except (EOFError, KeyboardInterrupt):
        print("\n  Cancelled.")
        sys.exit(1)
    if not raw.strip():
        print("  No version entered. Exiting.")
        sys.exit(1)
    return sanitize_version(raw)


def _clean_staging_dir(staging: Path) -> None:
    """Remove __pycache__, .gitkeep, *.pyc, and config.ini from staging."""
    # Remove directories
    for dirpath, dirnames, _ in os.walk(staging, topdown=False):
        for dname in dirnames:
            if dname in CLEANUP_DIRS:
                shutil.rmtree(Path(dirpath) / dname, ignore_errors=True)

    # Remove file patterns
    for dirpath, _, filenames in os.walk(staging):
        for fname in filenames:
            fpath = Path(dirpath) / fname
            if fname in CLEANUP_FILES or fpath.suffix == ".pyc":
                fpath.unlink(missing_ok=True)

    # Remove specific files
    for rel in CLEANUP_SPECIFIC:
        target = staging / rel
        if target.exists():
            target.unlink()


def _create_zip(source_dir: Path, zip_path: Path, arc_prefix: str) -> None:
    """Create a ZIP archive from source_dir with arc_prefix as the root folder."""
    _print_step(f"Creating ZIP: {zip_path.name}")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for dirpath, _, filenames in os.walk(source_dir):
            for fname in filenames:
                file_path = Path(dirpath) / fname
                arcname = Path(arc_prefix) / file_path.relative_to(source_dir)
                zf.write(file_path, arcname)
    size_mb = zip_path.stat().st_size / (1024 * 1024)
    _print_step(f"ZIP created: {zip_path} ({size_mb:.1f} MB)")


# ---------------------------------------------------------------------------
# Build commands
# ---------------------------------------------------------------------------

def cmd_exe() -> bool:
    """Build the PyInstaller binary. Returns True on success."""
    _print_header("HoonyTools — Build EXE")

    print(f"  Platform:  {platform.system()} {platform.machine()}")
    print(f"  Python:    {sys.version.split()[0]}")
    print()

    # Verify launcher exists
    launcher = SOURCE_DIR / "HoonyTools.pyw"
    if not launcher.exists():
        print("  ERROR: HoonyTools.pyw not found in source directory.")
        return False

    kill_running_processes()
    clean_build_dirs()

    # Build the command
    pyinst = find_pyinstaller()
    sep = get_add_data_sep()
    icon = get_icon_arg()

    add_data = []
    for folder in FOLDERS_TO_COPY:
        folder_path = SOURCE_DIR / folder
        if folder_path.is_dir():
            add_data.extend(["--add-data", f"{folder}{sep}{folder}"])

    cmd = [
        *pyinst,
        "--noconfirm",
        "--windowed",
        "--onefile",
        "--name", "HoonyTools",
        *icon,
        *add_data,
        str(launcher),
    ]

    _print_step("Running PyInstaller...")
    print(f"  Command: {' '.join(cmd)}\n")

    result = subprocess.run(cmd, cwd=str(SOURCE_DIR))

    if result.returncode != 0:
        print("\n  ERROR: PyInstaller failed.")
        return False

    # Check for output
    if IS_WINDOWS:
        exe_path = SOURCE_DIR / "dist" / "HoonyTools.exe"
    elif IS_MACOS:
        exe_path = SOURCE_DIR / "dist" / "HoonyTools.app"
        if not exe_path.exists():
            exe_path = SOURCE_DIR / "dist" / "HoonyTools"
    else:
        exe_path = SOURCE_DIR / "dist" / "HoonyTools"

    if exe_path.exists():
        # Clean up .spec file on success
        spec = SOURCE_DIR / "HoonyTools.spec"
        if spec.exists():
            spec.unlink()
            _print_step("Removed HoonyTools.spec")
        size_mb = exe_path.stat().st_size / (1024 * 1024) if exe_path.is_file() else 0
        _print_step(f"Build succeeded: {exe_path}" + (f" ({size_mb:.1f} MB)" if size_mb else ""))
    else:
        print("  WARNING: Binary not found in dist/ — leaving HoonyTools.spec for inspection.")

    return True


def cmd_package(version: str) -> bool:
    """Package source files into a release ZIP. Returns True on success."""
    _print_header(f"HoonyTools — Package Source (v{version})")

    # Paths
    release_base = SOURCE_DIR / "build" / f"v{version}"
    staging = release_base / "HoonyTools"
    dist_dir = SOURCE_DIR / "dist"
    zip_name = f"HoonyTools_v{version}_python.zip"
    zip_path = dist_dir / zip_name

    # Prepare staging directory
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)
    dist_dir.mkdir(parents=True, exist_ok=True)

    # Copy folders
    _print_step("Copying source folders...")
    for folder in FOLDERS_TO_COPY:
        src = SOURCE_DIR / folder
        dst = staging / folder
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)

    # Copy root files
    _print_step("Copying root files...")
    for fname in FILES_TO_COPY:
        src = SOURCE_DIR / fname
        if src.is_file():
            shutil.copy2(src, staging / fname)

    # Clean staging
    _print_step("Cleaning staging directory...")
    _clean_staging_dir(staging)

    # Remove old ZIP if exists
    if zip_path.exists():
        zip_path.unlink()

    # Create ZIP
    _create_zip(staging, zip_path, arc_prefix="HoonyTools")

    print(f"\n  Packaging complete: {zip_path}")
    return True


def cmd_all(version: str) -> bool:
    """Build EXE then package source ZIP."""
    success = cmd_exe()
    if not success:
        print("\n  EXE build failed — skipping packaging step.")
        return False
    return cmd_package(version)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="HoonyTools Build & Package Script (Cross-Platform)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  python build_pkg.py 2.2.2                    Build EXE + package source ZIP
  python build_pkg.py exe                      Build PyInstaller binary only
  python build_pkg.py 2.2.2 --mode package     Package source ZIP only
  python build_pkg.py 2.2.2 --mode exe         Build EXE only (version ignored)
""",
    )
    parser.add_argument(
        "target",
        help="Version number (e.g., 2.2.2) to build & package, or 'exe' to only build the binary",
    )
    parser.add_argument(
        "--mode",
        choices=["exe", "package", "all"],
        default=None,
        help="Override build mode (default: 'all' when version given, 'exe' when target is 'exe')",
    )

    args = parser.parse_args()

    # Determine mode and version from the positional argument
    if args.target.lower() == "exe":
        # python build_pkg.py exe
        mode = args.mode or "exe"
        version = None
    else:
        # python build_pkg.py 2.2.2 [--mode ...]
        version = sanitize_version(args.target)
        mode = args.mode or "all"

    # Execute
    if mode == "exe":
        success = cmd_exe()
    elif mode == "package":
        if not version:
            version = prompt_version()
        success = cmd_package(version)
    elif mode == "all":
        if not version:
            version = prompt_version()
        success = cmd_all(version)
    else:
        parser.print_help()
        success = False

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
