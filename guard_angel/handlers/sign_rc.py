import os
import shutil
import subprocess
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CommandHandler, ConversationHandler, MessageHandler, CallbackQueryHandler, 
    ContextTypes, filters
)
from ..config import settings
from ..services import rate_confirmation as rc_service, sheets

# States
CHOOSE_DRIVER, WAIT_RC_PDF, WAIT_FOR_SIGNING_CONFIRMATION, COLLECT_DATA, COLLECT_BROKER_EMAILS = range(5)
RC_TO_SIGN_PATH = "./files_cash/RC_TO_SIGN.pdf"
SIGNED_RC_PATH = "./files_cash/signed_RC.pdf"
FIELDS = [
    "PU Date", "PU Time", "Delivery Date", "Delivery Time", "PU Location", 
    "Delivery Location", "Broker Name", "Load Number", "Rate", "PU Number", 
    "Temperature", "Other Notes", "Broker Emails", "Estimated Empty Time"
]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # We only build the "Add New RC" flow for now
    context.user_data.clear()
    drivers = settings.owner_operators + settings.company_drivers
    kb = [[InlineKeyboardButton(d, callback_data=f"driver:{d}")] for d in drivers]
    text = "Please select a driver for the new RC:"
    if update.callback_query: await update.callback_query.answer(); await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
    else: await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))
    return CHOOSE_DRIVER

async def choose_driver(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query; await q.answer()
    driver = q.data.split(":", 1)[1]
    context.user_data['driver'] = driver
    await q.edit_message_text(f"Driver: {driver}.\n\nPlease upload the new Rate Confirmation PDF to sign.")
    return WAIT_RC_PDF

async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    file = await update.message.document.get_file()
    os.makedirs("./files_cash", exist_ok=True)
    await file.download_to_drive(RC_TO_SIGN_PATH)
    
    try:
        python_executable = os.path.join(os.getcwd(), 'venv', 'bin', 'python')
        gui_script_path = os.path.join(os.getcwd(), 'guard_angel', 'sign_rc_gui.py')
        subprocess.Popen([python_executable, gui_script_path])
        
        kb = [[InlineKeyboardButton("✅ I have finished signing", callback_data="rc:signed")]]
        await update.message.reply_text(
            "✅ RC received. The signing window should now be open on your server's desktop.\n\n"
            "After you click 'Done & Save', click the button below.",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb)
        )
        return WAIT_FOR_SIGNING_CONFIRMATION
    except Exception as e:
        await update.message.reply_text(f"Error launching the signing app: {e}")
        return ConversationHandler.END

async def signing_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query; await q.answer()
    if not os.path.exists(SIGNED_RC_PATH):
        await q.edit_message_text("❌ The signed RC was not found. Please run the desktop script and click 'Done & Save'.")
        return WAIT_FOR_SIGNING_CONFIRMATION

    context.user_data['field_index'] = 0
    context.user_data['collected_data'] = {}
    await q.edit_message_text("Great! Now, let's collect the load details.")
    await q.message.reply_text(f"Please provide: **{FIELDS[0]}**", parse_mode="Markdown")
    return COLLECT_DATA
    
async def collect_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    idx = context.user_data['field_index']
    field_name = FIELDS[idx]
    
    # **FIX**: Special handling for Broker Emails
    if field_name == "Broker Emails":
        context.user_data['collected_data']["Broker Emails"] = [] # Initialize list
        await update.message.reply_text("Please send the first broker email. When you have sent all emails, use the /done command.")
        return COLLECT_BROKER_EMAILS

    user_input = update.message.text.strip()
    context.user_data['collected_data'][field_name] = user_input
    
    idx += 1
    context.user_data['field_index'] = idx
    if idx < len(FIELDS):
        await update.message.reply_text(f"Please provide: **{FIELDS[idx]}**", parse_mode="Markdown")
        return COLLECT_DATA
    else: # Should not be reached if Broker Emails is in the list
        return await finish_collection(update, context)

async def collect_broker_emails(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Collects one email at a time."""
    email = update.message.text.strip()
    context.user_data['collected_data']["Broker Emails"].append(email)
    await update.message.reply_text(f"Email '{email}' added. Send another or use /done.")
    return COLLECT_BROKER_EMAILS

async def done_collecting_emails(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Moves to the next step after email collection is done."""
    idx = context.user_data['field_index'] + 1
    context.user_data['field_index'] = idx

    if idx < len(FIELDS):
        await update.message.reply_text(f"Please provide: **{FIELDS[idx]}**", parse_mode="Markdown")
        return COLLECT_DATA
    else:
        return await finish_collection(update, context)

async def finish_collection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Final step: write all data to the sheet."""
    await update.message.reply_text("All data collected. Writing to Google Sheet...")
    try:
        data = context.user_data['collected_data']
        rc_service.write_load_to_sheet(context.user_data['driver'], data, SIGNED_RC_PATH)
        await update.message.reply_text("✅ Success! New load added to the sheet.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error writing to sheet: {e}")
    
    if os.path.exists(RC_TO_SIGN_PATH): os.remove(RC_TO_SIGN_PATH)
    if os.path.exists(SIGNED_RC_PATH): os.remove(SIGNED_RC_PATH)
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.effective_message.reply_text("Operation cancelled.")
    return ConversationHandler.END

def handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(start, pattern="^act:sign_RC$")],
        states={
            CHOOSE_DRIVER: [CallbackQueryHandler(choose_driver)],
            WAIT_RC_PDF: [MessageHandler(filters.Document.PDF, handle_pdf)],
            WAIT_FOR_SIGNING_CONFIRMATION: [CallbackQueryHandler(signing_done, pattern="^rc:signed$")],
            COLLECT_DATA: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_data)],
            COLLECT_BROKER_EMAILS: [
                CommandHandler("done", done_collecting_emails),
                MessageHandler(filters.TEXT & ~filters.COMMAND, collect_broker_emails),
            ]
        },
        fallbacks=[CommandHandler("start", cancel), CommandHandler("cancel", cancel)],
    )
