Guard Angel Bot

Telegram bot that compiles salary statements from Google Sheets and uploads PDFs to Drive.

Quick Start
1) Clone and enter the project:
   git clone git@github.com:YOUR_GH_USER/guard-angel.git
   cd guard-angel

2) Create venv and install deps:
   python -m venv venv && source venv/bin/activate
   pip install -r requirements.txt

3) Create .env from template and fill it:
   cp .env.example .env
   # Edit .env and set:
   # - BOT_TOKEN (Telegram bot token)
   # - AUTHORIZED_USERS (comma-separated Telegram user IDs)
   # - SPREADSHEET_ID (Google Sheet ID)
   # - DRIVE_FOLDER_STATEMENTS (Google Drive folder ID for PDFs)

4) First-run config (local only, ignored by git):
   # Enter YOUR company name + address (street, city/state/zip) and
   # a mapping of Google Sheet tab name -> driver's company info.
   python scripts/setup_wizard.py

5) Run the bot:
   source venv/bin/activate
   python -m guard_angel.bot

Notes
- Driver starting rows are auto-detected by scanning column G; results are cached in .cache/last_rows.json.
- Sensitive org/driver data lives in .cache/org_config.json (git-ignored).
- Keep client_secrets/credentials tokens out of git (see .gitignore).
