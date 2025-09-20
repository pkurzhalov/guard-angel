#!/usr/bin/env bash
set -euo pipefail

echo "== Guard Angel Installer =="

# 1) Python venv & deps
if [ ! -d "venv" ]; then
  python -m venv venv
fi
# shellcheck disable=SC1091
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 2) .env
if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "Created .env from template. Please edit it now to set BOT_TOKEN, SPREADSHEET_ID, DRIVE_FOLDER_STATEMENTS, AUTHORIZED_USERS."
  ${EDITOR:-nano} .env
fi

# 3) Validate required env vars
python - <<'PY'
import os, sys
need = ["BOT_TOKEN","SPREADSHEET_ID","DRIVE_FOLDER_STATEMENTS","AUTHORIZED_USERS"]
missing = [k for k in need if not os.getenv(k)]
if missing:
    print("Missing required .env keys:", ", ".join(missing))
    sys.exit(1)
print("Env looks OK.")
PY

# 4) First-run setup wizard
python scripts/setup_wizard.py

# 5) Import smoke test
python - <<'PY'
import importlib
importlib.import_module("guard_angel.bot")
print("Bot module imports OK.")
PY

echo "Install complete. To run the bot:"
echo "  source venv/bin/activate && python -m guard_angel.bot"
