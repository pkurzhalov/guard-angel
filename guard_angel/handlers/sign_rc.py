import os
import shutil
import asyncio
import re
import subprocess
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CommandHandler, ConversationHandler, MessageHandler, CallbackQueryHandler, 
    ContextTypes, filters
)
from ..config import settings
from ..services import rate_confirmation as rc_service, sheets

# States for the conversation
STATE_CHOOSE_ACTION, CHOOSE_DRIVER_VIEW, CHOOSE_DRIVER_ADD, WAIT_RC_PDF, ASK_SIGN, WAIT_FOR_SIGNING, COLLECT_DATA, COLLECT_BROKER_EMAILS, AWAIT_BROKER_INFO, AWAIT_ACCOUNTING_EMAIL = range(10)

RC_TO_SIGN_PATH = "./files_cash/RC_TO_SIGN.pdf"
SIGNED_RC_PATH = "./files_cash/signed_RC.pdf"
FIELDS = ["PU Date", "PU Time", "Delivery Date", "Delivery Time", "PU Location", "Delivery Location", "Broker Name", "Load Number", "Rate", "PU Number", "Temperature", "Other Notes", "Broker Emails", "Estimated Empty Time"]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    kb = [[InlineKeyboardButton("➕ Add New RC", callback_data="rc:add_new")], [InlineKeyboardButton("👀 View Current RC", callback_data="rc:view_current")], [InlineKeyboardButton("Cancel", callback_data="rc:cancel")]]
    text = "What would you like to do?"
    if update.callback_query: await update.callback_query.answer(); await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
    else: await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))
    return STATE_CHOOSE_ACTION

async def choose_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query; await q.answer()
    action = q.data.split(":", 1)[1]
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
        summary, rc_link, image_paths = rc_service.view_current_load(driver)
        kb = [[InlineKeyboardButton("👉 Click to Open RC 📋👈", url=rc_link)]] if rc_link else None
        await q.message.reply_text(summary, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb) if kb else None)
        # **FIX**: Send the images
        if image_paths:
            await q.message.reply_text("RC Pages:")
            for path in image_paths:
                with open(path, 'rb') as photo_file:
                    await q.message.reply_photo(photo=photo_file)
                os.remove(path)
    except Exception as e: await q.message.reply_text(f"❌ Error: {e}")
    return ConversationHandler.END

# (The rest of the file is correct and included below)
async def choose_driver_for_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query; await q.answer()
    driver = q.data.split(":", 1)[1]
    context.user_data['driver'] = driver
    await q.edit_message_text(f"Driver: {driver}.\n\nPlease upload the new RC PDF.")
    return WAIT_RC_PDF
async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    file = await update.message.document.get_file()
    os.makedirs("./files_cash", exist_ok=True)
    await file.download_to_drive(RC_TO_SIGN_PATH)
    kb = [[InlineKeyboardButton("✅ Yes, Sign It", callback_data="sign:yes"), InlineKeyboardButton("❌ No, Use As-Is", callback_data="sign:no")]]
    await update.message.reply_text("RC received. Does it need to be signed?", reply_markup=InlineKeyboardMarkup(kb))
    return ASK_SIGN
async def handle_sign_decision(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query; await q.answer()
    decision = q.data.split(":", 1)[1]
    if decision == 'yes':
        await q.edit_message_text("Launching signing app... please wait for it to close.")
        loop = asyncio.get_running_loop()
        success = await loop.run_in_executor(None, rc_service.launch_and_wait_for_gui)
        if not success or not os.path.exists(SIGNED_RC_PATH):
            await q.message.reply_text("❌ Signing process failed or was cancelled."); return ConversationHandler.END
    else: # No signing needed
        await q.edit_message_text("Okay, using original RC.")
        shutil.copy(RC_TO_SIGN_PATH, SIGNED_RC_PATH)
    await q.message.reply_text("✅ RC is ready!")
    with open(SIGNED_RC_PATH, 'rb') as doc: await q.message.reply_document(document=doc, filename='signed_RC.pdf')
    driver_info = rc_service.get_driver_signature_text(context.user_data.get("driver"))
    await q.message.reply_text(f"```\n{driver_info}\n```", parse_mode='Markdown')
    context.user_data['field_index'] = 0; context.user_data['collected_data'] = {}
    await q.message.reply_text(f"Now, let's collect the load details.\nPlease provide: **{FIELDS[0]}**", parse_mode="Markdown")
    return COLLECT_DATA
async def collect_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    idx = context.user_data['field_index']; field_name = FIELDS[idx]
    user_input = update.message.text.strip()
    if field_name in ["PU Date", "Delivery Date"] and not re.match(r'^\d{1,2}/\d{1,2}/\d{4}$', user_input):
        await update.message.reply_text("❌ Invalid date. Use `MM/DD/YYYY`.", parse_mode="Markdown"); return COLLECT_DATA
    if field_name in ["PU Location", "Delivery Location"] and not re.match(r"^[A-Za-z\s\.]+,[\s]*[A-Z]{2}$", user_input):
        await update.message.reply_text("❌ Invalid location. Use `City, ST`.", parse_mode="Markdown"); return COLLECT_DATA
    if field_name == "Broker Emails":
        if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", user_input):
            await update.message.reply_text("❌ Invalid email format. Please try again."); return COLLECT_DATA
        context.user_data['collected_data']["Broker Emails"] = [user_input]
        await update.message.reply_text(f"Email '{user_input}' added. Send another or use /done.")
        return COLLECT_BROKER_EMAILS
    context.user_data['collected_data'][field_name] = user_input
    idx += 1; context.user_data['field_index'] = idx
    if idx < len(FIELDS):
        await update.message.reply_text(f"Please provide: **{FIELDS[idx]}**", parse_mode="Markdown")
        return COLLECT_DATA
    else: return await finish_collection(update, context)
async def collect_broker_emails(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    email = update.message.text.strip()
    if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
        await update.message.reply_text("❌ Invalid email format. Please try again."); return COLLECT_BROKER_EMAILS
    context.user_data['collected_data']["Broker Emails"].append(email)
    await update.message.reply_text(f"Email '{email}' added. Send another or use /done.")
    return COLLECT_BROKER_EMAILS
async def done_collecting_emails(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    idx = context.user_data['field_index'] + 1; context.user_data['field_index'] = idx
    if idx < len(FIELDS):
        await update.message.reply_text(f"Please provide: **{FIELDS[idx]}**", parse_mode="Markdown")
        return COLLECT_DATA
    else: return await finish_collection(update, context)
async def finish_collection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("All data collected. Writing to Google Sheet...")
    try:
        data = context.user_data['collected_data']; driver = context.user_data['driver']
        acc_email_found = rc_service.write_load_to_sheet(driver, data, SIGNED_RC_PATH)
        if not acc_email_found:
            await update.message.reply_text(f"⚠️ **New Broker!**\nPlease provide the **accounting email**.", parse_mode="Markdown")
            return AWAIT_ACCOUNTING_EMAIL
        else:
            await update.message.reply_text("✅ Success! New load added to the sheet.")
            if os.path.exists(RC_TO_SIGN_PATH): os.remove(RC_TO_SIGN_PATH)
            if os.path.exists(SIGNED_RC_PATH): os.remove(SIGNED_RC_PATH)
            return ConversationHandler.END
    except Exception as e: await update.message.reply_text(f"❌ Error writing to sheet: {e}"); return ConversationHandler.END
async def handle_accounting_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    acc_email = update.message.text.strip()
    if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", acc_email):
        await update.message.reply_text("❌ Invalid email. Try again."); return AWAIT_ACCOUNTING_EMAIL
    driver = context.user_data['driver']
    current_row = sheets.get_current_cell(driver, column="A")
    sheets.update_cell(driver, current_row, 'T', acc_email)
    await update.message.reply_text(f"✅ Email saved.\n\nNow, paste broker's **full company info** to create a customer file.", parse_mode="Markdown")
    return AWAIT_BROKER_INFO
async def handle_broker_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    broker_name = context.user_data['collected_data'].get("Broker Name")
    if not broker_name: await update.message.reply_text("Error: Broker name missing."); return ConversationHandler.END
    try:
        with open(f"./customers/{broker_name}.txt", "w") as f: f.write(update.message.text)
        await update.message.reply_text(f"✅ New customer file for **{broker_name}** created.", parse_mode="Markdown")
    except Exception as e: await update.message.reply_text(f"❌ Failed to save customer file: {e}")
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
            STATE_CHOOSE_ACTION: [CallbackQueryHandler(choose_action, pattern="^rc:(add_new|view_current)$")],
            CHOOSE_DRIVER_VIEW: [CallbackQueryHandler(view_rc_for_driver, pattern="^driver:.+")],
            CHOOSE_DRIVER_ADD: [CallbackQueryHandler(choose_driver_for_add, pattern="^driver:.+")],
            WAIT_RC_PDF: [MessageHandler(filters.Document.PDF, handle_pdf)],
            ASK_SIGN: [CallbackQueryHandler(handle_sign_decision, pattern="^sign:(yes|no)$")],
            COLLECT_DATA: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_data)],
            COLLECT_BROKER_EMAILS: [CommandHandler("done", done_collecting_emails), MessageHandler(filters.TEXT & ~filters.COMMAND, collect_broker_emails)],
            AWAIT_ACCOUNTING_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_accounting_email)],
            AWAIT_BROKER_INFO: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_broker_info)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
