import sys
import getpass
from pathlib import Path
from configparser import ConfigParser

CONFIG_PATH = Path(__file__).parent / "config.ini"
FORCE_OVERWRITE = "--force" in sys.argv

print("🔐 Setup: DWH Connection Configuration")
print("→ Schema: dwh")
print("→ DSN: DWHDB_DB")
print()

password = getpass.getpass("Enter your DWH Oracle password: ").strip()

if not password:
    print("❌ Password is required. Exiting.")
    exit()

# If config already exists and user requested a hard overwrite, replace the file
if CONFIG_PATH.exists() and FORCE_OVERWRITE:
    config_text = f"""[dwh]
username = dwh
password = {password}
dsn = DWHDB_DB
"""
    CONFIG_PATH.write_text(config_text, encoding="utf-8")
    print(f"✅ config.ini overwritten at: {CONFIG_PATH}")
    print("📌 Use without --force to merge into existing config instead of overwriting.")
    exit()

# Merge/update existing config (safe): read existing, update [dwh], write back
cfg = ConfigParser()
if CONFIG_PATH.exists():
    try:
        cfg.read(CONFIG_PATH)
    except Exception:
        cfg = ConfigParser()

cfg["dwh"] = {
    "username": "dwh",
    "password": password,
    "dsn": "DWHDB_DB"
}

CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
with open(CONFIG_PATH, "w", encoding="utf-8") as f:
    cfg.write(f)

if CONFIG_PATH.exists():
    print(f"✅ config.ini updated at: {CONFIG_PATH}")
else:
    print(f"✅ config.ini created at: {CONFIG_PATH}")

print("📌 You can re-run this script anytime to reset your password. Use --force to overwrite the whole file.")
