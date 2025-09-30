from telegram.ext import CallbackQueryHandler, Application, ContextTypes
from telegram import Update

async def coming_soon(update: Update, context: ContextTypes.DEFAULT_TYPE, label: str):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(f"{label} — coming soon. Use /start to pick another action.")

def register(app: Application):
    app.add_handler(CallbackQueryHandler(lambda u,c: coming_soon(u,c,"🔎 Look for a load"), pattern="^act:look_for_a_load$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: coming_soon(u,c,"🖊️ Sign RC"), pattern="^act:sign_RC$"))
