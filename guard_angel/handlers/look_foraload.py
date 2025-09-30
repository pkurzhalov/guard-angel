from __future__ import annotations
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes
import guard_angel.services.legacy as legacy
from ..config import settings

def _auth(uid: int) -> bool:
    try:
        if hasattr(settings, "authorized_users") and isinstance(settings.authorized_users, set):
            if uid in settings.authorized_users:
                return True
        raw = getattr(settings, "authorized_users_raw", "")
        if raw:
            if uid in {int(x) for x in raw.split(",") if x.strip().isdigit()}:
                return True
        for a in getattr(settings, "admin_ids", []):
            if uid == a:
                return True
    except Exception:
        pass
    return False

def handler() -> CommandHandler:
    return CommandHandler("look_foraload", run)

async def run(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not _auth(user_id):
        await update.message.reply_text("Unauthorized.")
        return
    await update.message.reply_text("⏳ Running legacy look_foraload (kolobok.py)…")
    result = legacy.run_look_for_load()
    tail = result[-3500:] if len(result) > 3500 else result
    await update.message.reply_text(f"✅ Done.\\n\\n```\\n{tail}\\n```", parse_mode="Markdown")
