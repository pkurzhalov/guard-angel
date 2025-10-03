from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from ..config import settings

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    The main entry point. Shows the menu ONLY to authorized users.
    """
    # --- SECURITY GUARD ---
    if update.effective_user.id not in settings.authorized_users:
        await update.message.reply_text("You are not authorized to use this bot.")
        return
    # --- END GUARD ---

    kb = [
        [InlineKeyboardButton("🔎 Look for a load", callback_data="act:look_for_load")],
        [InlineKeyboardButton("💵 Count salary",   callback_data="act:count_salary")],
        [InlineKeyboardButton("🖊️ Sign RC",        callback_data="act:sign_RC")],
        [InlineKeyboardButton("📄 Send invoice",   callback_data="act:send_invoice")],
    ]
    text = "Welcome to Guard Angel. Choose an action:"
    
    # This logic handles both a new /start command and a "Back" button press
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))
