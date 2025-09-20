from telegram import Update
from telegram.ext import ContextTypes
WELCOME = (
    "Welcome to guard-angel.\n\n"
    "Commands:\n"
    "• /count_salary – calculate driver salary\n"
    "• /help – show help"
)
async def start(update: Update, _: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(WELCOME)
async def help_(update: Update, _: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Try /count_salary to start a salary calculation.")
