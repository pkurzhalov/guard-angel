import os
import shutil
import asyncio
import subprocess
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CommandHandler, ConversationHandler, MessageHandler, CallbackQueryHandler, 
    ContextTypes, filters
)
from ..config import settings
from ..services import rate_confirmation as rc_service
from . import menu

# States for the conversation
CHOOSE_ACTION, CHOOSE_DRIVER_VIEW, CHOOSE_DRIVER_ADD, WAIT_RC_PDF, WAIT_FOR_SIGNING, COLLECT_DATA, COLLECT_BROKER_EMAILS = range(7)

RC_TO_SIGN_PATH = "./files_cash/RC_TO_SIGN.pdf"
SIGNED_RC_PATH = "./files_cash/signed_RC.pdf"
FIELDS = [
    "PU Date", "PU Time", "Delivery Date", "Delivery Time", "PU Location", 
    "Delivery Location", "Broker Name", "Load Number", "Rate", "PU Number", 
    "Temperature", "Other Notes", "Broker Emails", "Estimated Empty Time"
]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    kb = [
        [InlineKeyboardButton("➕ Add & Sign New RC", callback_data="rc:add_new")],
        [InlineKeyboardButton("👀 View Current RC", callback_data="rc:view_current")],
        [InlineKeyboardButton("Cancel", callback_data="rc:cancel")]
    ]
    text = "What would you like to do with the Rate Confirmation?"
    if update.callback_query: await update.callback_query.answer(); await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
    else: await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))
    return CHOOSE_ACTION

async def choose_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query; await q.answer()
    action = q.data.split(":", 1)[1]
    context.user_data['action'] = action
    drivers = settings.owner_operators + settings.company_drivers
    kb = [[InlineKeyboardButton(d, callback_data=f"driver:{d}")] for d in drivers]
    kb.append([InlineKeyboardButton("Back", callback_data="rc:back")])
    await q.edit_message_text("Please select a driver:", reply_markup=InlineKeyboardMarkup(kb))
    return CHOOSE_DRIVER_VIEW if action == 'view_current' else CHOOSE_DRIVER_ADD

async def view_rc_for_driver(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query; await q.answer()
    driver = q.data.split(":", 1)[1]
    await q.edit_message_text(f"Fetching current RC for {driver}...")
    try:
        summary, image_paths = rc_service.view_current_load(driver)
        await q.message.reply_text(summary, parse_mode="Markdown")
        for path in image_paths:
            await q.message.reply_photo(photo=open(path, 'rb'))
            os.remove(path)
    except Exception as e: await q.message.reply_text(f"❌ Error: {e}")
    return ConversationHandler.END

async def choose_driver_for_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query; await q.answer()
    driver = q.data.split(":", 1)[1]
    context.user_data['driver'] = driver
    await q.edit_message_text(f"Driver: {driver}.\n\nPlease upload the new Rate Confirmation PDF to sign.")
    return WAIT_RC_PDF

async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("✅ RC received. Launching the signing app on your server...")
    file = await update.message.document.get_file()
    os.makedirs("./files_cash", exist_ok=True)
    await file.download_to_drive(RC_TO_SIGN_PATH)
    loop = asyncio.get_running_loop()
    success = await loop.run_in_executor(None, rc_service.launch_and_wait_for_gui)
    if not success or not os.path.exists(SIGNED_RC_PATH):
        await update.message.reply_text("❌ Signing process failed or was cancelled.")
        return ConversationHandler.END
    await update.message.reply_text("✅ Signing complete!")
    with open(SIGNED_RC_PATH, 'rb') as doc: await update.message.reply_document(document=doc, filename='signed_RC.pdf')
    driver_info = rc_service.get_driver_signature_text(context.user_data.get("driver"))
    await update.message.reply_text(f"```\n{driver_info}\n```", parse_mode='Markdown')
    context.user_data['field_index'] = 0; context.user_data['collected_data'] = {}
    await update.message.reply_text(f"Let's collect load details.\nPlease provide: **{FIELDS[0]}**", parse_mode="Markdown")
    return COLLECT_DATA
    
async def collect_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    idx = context.user_data['field_index']
    field_name = FIELDS[idx]
    if field_name == "Broker Emails":
        context.user_data['collected_data']["Broker Emails"] = []
        await update.message.reply_text("Please send the first broker email. When done, use /done.")
        return COLLECT_BROKER_EMAILS
    user_input = update.message.text.strip()
    context.user_data['collected_data'][field_name] = user_input
    idx += 1; context.user_data['field_index'] = idx
    if idx < len(FIELDS):
        await update.message.reply_text(f"Please provide: **{FIELDS[idx]}**", parse_mode="Markdown")
        return COLLECT_DATA
    else: return await finish_collection(update, context)

async def collect_broker_emails(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    email = update.message.text.strip()
    context.user_data['collected_data']["Broker Emails"].append(email)
    await update.message.reply_text(f"Email '{email}' added. Send another or use /done.")
    return COLLECT_BROKER_EMAILS

async def done_collecting_emails(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    idx = context.user_data['field_index'] + 1
    context.user_data['field_index'] = idx
    if idx < len(FIELDS):
        await update.message.reply_text(f"Please provide: **{FIELDS[idx]}**", parse_mode="Markdown")
        return COLLECT_DATA
    else: return await finish_collection(update, context)

async def finish_collection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("All data collected. Writing to Google Sheet...")
    try:
        data = context.user_data['collected_data']
        driver = context.user_data['driver']
        rc_service.write_load_to_sheet(driver, data, SIGNED_RC_PATH)
        await update.message.reply_text("✅ Success! New load added to the sheet.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error writing to sheet: {e}")
    if os.path.exists(RC_TO_SIGN_PATH): os.remove(RC_TO_SIGN_PATH)
    if os.path.exists(SIGNED_RC_PATH): os.remove(SIGNED_RC_PATH)
    return ConversationHandler.END

async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text("Operation cancelled. Send /start to see the main menu.")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    q = update.callback_query; await q.answer()
    await q.edit_message_text("Operation cancelled. Send /start to see the main menu.")
    return ConversationHandler.END

def handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(start, pattern="^act:sign_RC$")],
        states={
            CHOOSE_ACTION: [CallbackQueryHandler(choose_action, pattern="^rc:(add_new|view_current)$")],
            CHOOSE_DRIVER_VIEW: [CallbackQueryHandler(view_rc_for_driver, pattern="^driver:.+"), CallbackQueryHandler(start, pattern="^rc:back$")],
            CHOOSE_DRIVER_ADD: [CallbackQueryHandler(choose_driver_for_add, pattern="^driver:.+"), CallbackQueryHandler(start, pattern="^rc:back$")],
            WAIT_RC_PDF: [MessageHandler(filters.Document.PDF, handle_pdf)],
            COLLECT_DATA: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_data)],
            COLLECT_BROKER_EMAILS: [
                CommandHandler("done", done_collecting_emails),
                MessageHandler(filters.TEXT & ~filters.COMMAND, collect_broker_emails),
            ]
        },
        fallbacks=[CommandHandler("start", restart), CallbackQueryHandler(cancel, pattern="^rc:cancel$")],
    )
