from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from ..config import settings

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in settings.authorized_users:
        await update.message.reply_text("You are not authorized to use this bot.")
        return

    kb = [
        [InlineKeyboardButton("💵 Count salary",   callback_data="act:count_salary")],
        [InlineKeyboardButton("📄 Send invoice",   callback_data="act:send_invoice")],
        [InlineKeyboardButton("🖊️ Sign RC",        callback_data="act:sign_RC")],
        [InlineKeyboardButton("⛽ Count IFTA",     callback_data="act:count_ifta")],
        [InlineKeyboardButton("💰 Check Payments",  callback_data="act:check_payments")], # Add this line
    ]
    text = "Welcome to Guard Angel. Choose an action:"

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))
