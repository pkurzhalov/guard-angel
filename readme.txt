Guard Angel Bot

Telegram bot that compiles salary statements from Google Sheets and uploads PDFs to Drive.

Setup
1) Create venv and install deps:
   python -m venv venv && source venv/bin/activate && pip install -r requirements.txt

2) Copy env and fill values:
   cp .env.example .env
   # edit .env with your BOT_TOKEN, SPREADSHEET_ID, DRIVE_FOLDER_STATEMENTS, etc.

3) Run the bot:
   source venv/bin/activate
   python -m guard_angel.bot

Environment variables (see .env.example)
- BOT_TOKEN
- ADMIN_IDS
- AUTHORIZED_USERS
- SPREADSHEET_ID
- DRIVE_FOLDER_STATEMENTS
- TRAILER_PAYMENT
- INSURANCE_CUTOFF
- CELL_YURA / CELL_WALTER / CELL_DENIS / CELL_TEST / CELL_JAVIER / CELL_NESTOR
