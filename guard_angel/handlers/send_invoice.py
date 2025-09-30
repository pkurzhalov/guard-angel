from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CommandHandler, ConversationHandler, MessageHandler, CallbackQueryHandler, 
    ContextTypes, filters
)
import os
import shutil
import img2pdf
import io
from ..config import settings
from ..services import sheets, email as email_service
from PyPDF2 import PdfMerger

# States
STATE_CHOOSE_DRIVER, STATE_ENTER_ROW, STATE_WAIT_POD_UPLOAD, STATE_CONFIRM_EXISTING_POD, STATE_CONFIRM_EMAIL = range(5)

# --- Conversation Entry and Cancellation ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    drivers = ["Yura", "Walter", "Nestor", "Javier", "Denis"]
    kb = [[InlineKeyboardButton(d, callback_data=f"driver:{d}")] for d in drivers]
    kb.append([InlineKeyboardButton("Cancel", callback_data="action:cancel")])
    text = "Select driver/sheet for the invoice:"
    if update.message: await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))
    else: q = update.callback_query; await q.answer(); await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
    return STATE_CHOOSE_DRIVER

async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text("Operation cancelled. Send /start to see the main menu.")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    q = update.callback_query; await q.answer()
    await q.edit_message_text("Operation cancelled. Send /start to see the main menu.")
    return ConversationHandler.END

# --- Main Conversation Flow ---
async def pick_driver(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    driver = q.data.split(":", 1)[1]
    context.user_data["driver"] = driver
    await q.edit_message_text(f"Driver: {driver}\n\nPlease enter the row number:")
    return STATE_ENTER_ROW

async def handle_row_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try: row = int(update.message.text)
    except (ValueError, TypeError): return STATE_ENTER_ROW
    context.user_data["row"] = row; driver = context.user_data["driver"]
    load_data = sheets.open_invoice_load(driver, row)[0]
    pod_link = load_data[13] if len(load_data) > 13 and load_data[13] else None
    context.user_data["load_num"] = load_data[7]
    context.user_data["pod_files"] = []
    
    kb = [[InlineKeyboardButton("✅ Done Uploading", callback_data="pod:done")]]

    if pod_link and "drive.google.com" in pod_link:
        kb_existing = [[InlineKeyboardButton("Use Existing", callback_data="pod:use_existing"), InlineKeyboardButton("Upload New", callback_data="pod:upload_new")]]
        await update.message.reply_text("A POD is on file. Use it or upload a new one?", reply_markup=InlineKeyboardMarkup(kb_existing))
        return STATE_CONFIRM_EXISTING_POD
    else:
        await update.message.reply_text(f"Row {row} selected. No POD found.\n\n**Please upload POD files (PDFs or images).**\nClick 'Done Uploading' when finished.", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        return STATE_WAIT_POD_UPLOAD

async def handle_pod_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    decision = q.data.split(":", 1)[1]
    if decision == "upload_new":
        kb = [[InlineKeyboardButton("✅ Done Uploading", callback_data="pod:done")]]
        await q.edit_message_text("Okay, please upload new POD files. Click 'Done' when finished.", reply_markup=InlineKeyboardMarkup(kb))
        return STATE_WAIT_POD_UPLOAD
    else:
        await q.edit_message_text("Using existing POD. ⏳ Generating invoice...")
        return await generate_invoice(update, context)

async def handle_pod_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles receiving PDFs and Photos, storing them in memory."""
    file_id = update.message.document.file_id if update.message.document else update.message.photo[-1].file_id
    file = await context.bot.get_file(file_id)
    # **FIX**: Store as BytesIO stream, just like the old script
    file_stream = io.BytesIO(await file.download_as_bytearray())
    context.user_data["pod_files"].append(file_stream)
    await update.message.reply_text(f"File #{len(context.user_data['pod_files'])} received. Send more or click 'Done'.")
    return STATE_WAIT_POD_UPLOAD

async def merge_and_upload_pod(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Merges all collected files into a single PDF and proceeds."""
    q = update.callback_query; await q.answer()
    pod_files = context.user_data.get("pod_files", [])
    if not pod_files:
        await q.edit_message_text("No POD files were uploaded. Please upload at least one file.")
        return STATE_WAIT_POD_UPLOAD

    await q.edit_message_text(f"Merging {len(pod_files)} file(s) into one POD...")
    
    merger = PdfMerger()
    # **FIX**: Ensure the output directory exists BEFORE trying to write to it.
    os.makedirs("./files_cash", exist_ok=True)
    
    for file_stream in pod_files:
        file_stream.seek(0) # IMPORTANT: Rewind the in-memory file
        if file_stream.read(4) == b'%PDF': # Check if it's a PDF
            file_stream.seek(0)
            merger.append(file_stream)
        else: # Assume it's an image
            file_stream.seek(0)
            try:
                # **FIX**: Convert image stream to PDF bytes
                pdf_bytes = img2pdf.convert(file_stream.read())
                merger.append(io.BytesIO(pdf_bytes))
            except Exception as e:
                await update.effective_message.reply_text(f"Could not convert an image to PDF: {e}")

    load_num = context.user_data["load_num"]
    merged_pod_path = f"./files_cash/POD_{load_num}_MERGED.pdf"
    merger.write(merged_pod_path)
    merger.close()

    await update.effective_message.reply_text("✅ POD merged. Uploading...")
    sheets.upload_pod(merged_pod_path, context.user_data["driver"], context.user_data["row"])
    await update.effective_message.reply_text("✅ POD uploaded.\n\n⏳ Generating final invoice...")
    
    return await generate_invoice(update, context)

# The generate_invoice and email functions remain unchanged
async def generate_invoice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    driver = context.user_data["driver"]; row = context.user_data["row"]
    try:
        load_data = sheets.open_invoice_load(driver, row)[0]
        load_num=load_data[7]; broker=load_data[6]; pu_date=load_data[0]; del_date=load_data[2]; pu_city=load_data[4]; del_city=load_data[5]; gross=load_data[9]; lumper_k=load_data[14]; lumper_b=load_data[15]; inv_num=load_data[18]; rc_link=load_data[8]; pod_link=load_data[13]; broker_email=load_data[19]
        cc_emails = load_data[16].split() if len(load_data) > 16 and load_data[16] else []
        sheets.compilate_invoice_page(load_num, driver, row, broker, pu_city, pu_date, del_city, del_date, inv_num, gross, lumper_k, lumper_b)
        rc_id = sheets.get_id_from_link(rc_link); pod_id = sheets.get_id_from_link(pod_link)
        sheets.download_file(rc_id, "RC.pdf"); sheets.download_file(pod_id, "POD.pdf")
        merger = PdfMerger()
        final_filename = f"Invoice_{load_num}_MC_1294648.pdf"
        merger.append(f"./files_cash/Invoice_{load_num}_MC_1294648.pdf"); merger.append("./files_cash/RC.pdf"); merger.append("./files_cash/POD.pdf")
        merger.write(final_filename); merger.close()
        sheets.upload_file(final_filename, driver, row)
        context.user_data.update({"final_invoice_path": final_filename, "broker_email": broker_email, "cc_list": cc_emails, "load_num": load_num})
        kb = [[InlineKeyboardButton("✅ Yes, Send Email", callback_data="email:yes"), InlineKeyboardButton("❌ No", callback_data="email:no")]]
        reply_method = update.message.reply_document if hasattr(update, 'message') and update.message else update.callback_query.message.reply_document
        await reply_method(document=open(final_filename, 'rb'), caption=f"Invoice generated. Send to {broker_email}?", reply_markup=InlineKeyboardMarkup(kb))
        return STATE_CONFIRM_EMAIL
    except Exception as e:
        reply_method = update.message.reply_text if hasattr(update, 'message') and update.message else update.callback_query.message.reply_text
        await reply_method(f"❌ Error during generation: {e}")
        return ConversationHandler.END

async def handle_email_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    decision = q.data.split(":", 1)[1]
    ud = context.user_data
    if decision == "yes":
        await q.edit_message_caption(caption="🚀 Sending email...")
        try:
            email_service.send_invoice_email(recipient_email=ud["broker_email"], cc_list=ud["cc_list"], subject=f'POD/Invoice Order {ud["load_num"]} Carrier KOLOBOK, INC. MC 1294648', load_num=ud["load_num"], attachment_path=ud["final_invoice_path"])
            await q.edit_message_caption(caption="✅ Email sent successfully!")
        except Exception as e: await q.edit_message_caption(caption=f"❌ Failed to send email: {e}")
    else: await q.edit_message_caption(caption="✅ Invoice generated. Operation complete.")
    if os.path.exists(ud.get("final_invoice_path", "")): os.remove(ud["final_invoice_path"])
    shutil.rmtree("./files_cash", ignore_errors=True)
    return ConversationHandler.END

def handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("send_invoice", start), CallbackQueryHandler(start, pattern="^act:send_invoice$")],
        states={
            STATE_CHOOSE_DRIVER: [CallbackQueryHandler(pick_driver, pattern=r"^driver:.+")],
            STATE_ENTER_ROW: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_row_entry)],
            STATE_CONFIRM_EXISTING_POD: [CallbackQueryHandler(handle_pod_decision, pattern=r"^pod:.+")],
            STATE_WAIT_POD_UPLOAD: [
                MessageHandler(filters.Document.PDF | filters.PHOTO, handle_pod_files),
                CallbackQueryHandler(merge_and_upload_pod, pattern="^pod:done$")
            ],
            STATE_CONFIRM_EMAIL: [CallbackQueryHandler(handle_email_decision, pattern=r"^email:.+")]
        },
        fallbacks=[CommandHandler("start", restart), CallbackQueryHandler(cancel, pattern="^action:cancel$")],
    )
