import logging
from telegram.ext import Application, CommandHandler
from .config import settings
from .handlers import menu, count_salary, send_invoice, sign_rc, count_ifta # Import new handler

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

def build_app() -> Application:
    app = Application.builder().token(settings.bot_token).build()
    
    app.add_handler(count_salary.handler())
    app.add_handler(send_invoice.handler())
    app.add_handler(sign_rc.handler())
    app.add_handler(count_ifta.handler()) # Add new handler
    
    app.add_handler(CommandHandler("start", menu.start))
    
    return app

def main():
    app = build_app()
    logger.info("Bot is running... Press Ctrl+C to stop.")
    app.run_polling()

if __name__ == "__main__":
    main()
