from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram import Update

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("🔎 Look for a load", callback_data="act:look_for_a_load")],
        [InlineKeyboardButton("💵 Count salary",    callback_data="act:count_salary")],
        [InlineKeyboardButton("🖊️ Sign RC",        callback_data="act:sign_RC")],
        [InlineKeyboardButton("📄 Send invoice",    callback_data="act:send_invoice")],
    ]
    text = "Welcome to Guard Angel. Choose an action:"
    if update.message:
        return await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))
    elif update.callback_query:
        q = update.callback_query
        await q.answer()
        return await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
