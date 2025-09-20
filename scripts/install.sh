#!/usr/bin/env bash
set -euo pipefail

echo "== Guard Angel Installer =="

# ---- Pick Python ----
if command -v python >/dev/null 2>&1; then
  PY=python
elif command -v python3 >/dev/null 2>&1; then
  PY=python3
else
  echo "Python not found. Install python3 first (e.g., sudo apt install -y python3 python3-venv python3-pip)"
  exit 1
fi

# ---- Venv & deps ----
if [ ! -d "venv" ]; then
  "$PY" -m venv venv
fi
# shellcheck disable=SC1091
source venv/bin/activate
"$PY" -m pip install --upgrade pip
"$PY" -m pip install -r requirements.txt

# ---- .env ----
if [ ! -f ".env" ]; then
  cp .env.example .env
  echo
  echo "Created .env from template. Please edit the following keys:"
  echo "  BOT_TOKEN, AUTHORIZED_USERS, SPREADSHEET_ID, DRIVE_FOLDER_STATEMENTS"
  "${EDITOR:-nano}" .env
fi

# ---- Google credentials.json (service account key) ----
if [ ! -f "credentials.json" ]; then
  echo
  echo "I don't see credentials.json in the project root."
  echo "This is your Google service account key (JSON) used for Sheets/Drive."
  echo "• If you have it on disk, type its path now and I will copy it here."
  echo "• Otherwise, press Enter to skip and place it later as ./credentials.json"
  read -r -p "Path to credentials.json (blank to skip): " CREDS_PATH || true
  if [ -n "${CREDS_PATH:-}" ]; then
    cp -v "$CREDS_PATH" credentials.json
  fi
fi

# ---- Quick env check (non-fatal if credentials.json is missing) ----
"$PY" - <<'PY'
import os, sys
from pathlib import Path
need = ["BOT_TOKEN","SPREADSHEET_ID","DRIVE_FOLDER_STATEMENTS","AUTHORIZED_USERS"]
missing = [k for k in need if not os.getenv(k)]
if missing:
    print("ERROR: Missing required .env keys:", ", ".join(missing))
    sys.exit(1)
if not Path("credentials.json").exists():
    print("WARNING: credentials.json is missing. Sheets/Drive will fail until you add it.")
print("Env looks OK.")
PY

# ---- First-run setup wizard ----
"$PY" scripts/setup_wizard.py || true

# ---- Import smoke test ----
set +e
"$PY" - <<'PY'
try:
    import importlib
    importlib.import_module("guard_angel.bot")
    print("Bot module imports OK.")
except Exception as e:
    print("Bot import warning:", e)
PY
set -e

echo
echo "Install complete."
echo "To run the bot:"
echo "  source venv/bin/activate && $PY -m guard_angel.bot"
