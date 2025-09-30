Guard Angel Bot

Telegram bot that compiles salary statements from Google Sheets and uploads PDFs to Drive.

Prereqs (Ubuntu/Debian)
- git, python3, python3-venv, python3-pip
  sudo apt update && sudo apt install -y git python3 python3-venv python3-pip

Clone
# HTTPS (easiest)
git clone https://github.com/pkurzhalov/guard-angel.git
cd guard-angel

# (Optional) SSH – set up an SSH key with GitHub first
# git clone git@github.com:pkurzhalov/guard-angel.git

Install
./scripts/install.sh
- This will:
  * create a venv and install dependencies,
  * prompt you to edit .env (BOT_TOKEN, AUTHORIZED_USERS, SPREADSHEET_ID, DRIVE_FOLDER_STATEMENTS),
  * optionally copy your Google credentials.json if you provide its path,
  * run a first-run wizard to store your org + driver company info in .cache/org_config.json.

Google Setup (once)
1) Create a Service Account in Google Cloud and download its key JSON as credentials.json.
2) Enable APIs: Google Sheets API and Google Drive API.
3) Share your Google Spreadsheet with the service account’s client_email (read/write).
4) Place credentials.json in the project root (next to .env).

Run
source venv/bin/activate
python -m guard_angel.bot

Notes
- Driver starting rows are auto-detected by scanning column G; results cached at .cache/last_rows.json.
- Org/driver private info: .cache/org_config.json (git-ignored).
- Keep client_secrets.json / credentials.json out of git (already in .gitignore).
