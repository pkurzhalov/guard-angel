from telegram.ext import Application, CommandHandler
from .config import settings
from .handlers import count_salary
from .handlers import common  # keep your existing common.py handlers if any

def build_app() -> Application:
    app = Application.builder().token(settings.bot_token).build()
    # basic commands from common.py (adjust if names differ)
    try:
        app.add_handler(CommandHandler("help", common.help_))
        app.add_handler(CommandHandler("ping", common.ping))
    except Exception:
        pass
    # salary conversation
    app.add_handler(count_salary.handler())
    return app

if __name__ == "__main__":
    app = build_app()
    app.run_polling()
