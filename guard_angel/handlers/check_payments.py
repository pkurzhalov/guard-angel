# FILE: guard_angel/handlers/check_payments.py

import json
import sys
import asyncio
import os
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ConversationHandler, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
)
from ..services import payment_repository

# Define our new, more detailed states
(
    AWAIT_PDF, AWAIT_RANGES,
    AWAIT_PAYMENT_APPROVAL, AWAIT_MANUAL_ASSIGNMENT,
    AWAIT_DATE_CORRECTION, AWAIT_SCREENSHOT
) = range(6)


# --- CORE WORKFLOW FUNCTIONS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(text="Please upload the payment statement PDF.")
    return AWAIT_PDF

async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    file = await update.message.document.get_file()
    pdf_content = await file.download_as_bytearray()
    parsed_payments = payment_repository.parse_payment_pdf(bytes(pdf_content))
    context.user_data['payments'] = parsed_payments
    
    if not parsed_payments or "Error" in parsed_payments[0]:
        error_message = parsed_payments[0].get("Error", "Could not parse any payments.")
        await update.message.reply_text(f"❌ *Error:* {error_message}", parse_mode="MarkdownV2")
        return ConversationHandler.END
    
    await update.message.reply_text(
        text=(
            f"✅ PDF parsed successfully, found {len(parsed_payments)} transactions\\.\n\n"
            "Now, please provide the load ranges\\."
        ),
        parse_mode="MarkdownV2"
    )
    return AWAIT_RANGES

async def handle_ranges_and_terminal_io(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    range_text = update.message.text
    payments = context.user_data.get('payments', [])
    chat_id = update.effective_chat.id
    await context.bot.send_message(chat_id, text="Got it. Generating the master prompt now...")
    loads_data = await payment_repository.fetch_loads_data(range_text)
    if isinstance(loads_data, str):
        await context.bot.send_message(chat_id, text=loads_data)
        return AWAIT_RANGES
    prompt = payment_repository.create_master_prompt(payments, loads_data)
    
    # ... (Terminal interaction: printing prompt and asking for JSON) ...
    print("\n" + "="*50 + "\n--- 🤖 AI PROMPT READY ---\nSTEP 1: Copy and paste into AI.\n" + "="*50 + "\n\n" + prompt)
    await context.bot.send_message(chat_id, text="✅ **Prompt generated!** Check your server terminal.")
    print("\n" + "="*50 + "\nSTEP 2: Paste the AI's JSON response here, then press Ctrl+D.\n--- WAITING FOR JSON INPUT ---\n")
    
    try:
        raw_text = await asyncio.to_thread(sys.stdin.read)
        print("--- JSON RECEIVED, PROCESSING... ---")
        start_index, end_index = raw_text.find('{'), raw_text.rfind('}')
        if start_index == -1 or end_index == -1: raise ValueError("JSON object not found.")
        json_text = raw_text[start_index : end_index + 1]
        ai_data = json.loads(json_text)
        
        # --- NEW: Create the unified review list ---
        matched_loads = ai_data.get('matched_loads', [])
        all_payments_for_review = []
        for p in payments:
            found_match = next((m for m in matched_loads if m['paid_amount'] == p['amount'] and m['paid_date'] == p['date']), None)
            all_payments_for_review.append({'payment': p, 'suggested_match': found_match})
        
        context.user_data['all_payments_for_review'] = all_payments_for_review
        context.user_data['payment_review_index'] = 0
        
        await context.bot.send_message(chat_id, text="✅ AI response parsed! Starting sequential payment review...")
        return await process_next_payment(update, context)

    except Exception as e:
        error_msg = f"❌ Processing Failed in Terminal: {e}"
        print(error_msg)
        await context.bot.send_message(chat_id, text=error_msg)
        return ConversationHandler.END

# --- NEW SEQUENTIAL REVIEW LOOP ---

async def process_next_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """The new main loop function. Processes payments one by one from the statement."""
    idx = context.user_data.get('payment_review_index', 0)
    review_list = context.user_data.get('all_payments_for_review', [])
    chat_id = update.effective_chat.id

    if idx >= len(review_list):
        await context.bot.send_message(chat_id, text="🎉 All payments from the statement have been reviewed!")
        return ConversationHandler.END

    item = review_list[idx]
    payment = item['payment']
    match = item['suggested_match']
    
    text = (
        f"**Processing Payment #{idx + 1} / {len(review_list)}**\n\n"
        f"Date: `{payment['date']}`\n"
        f"Amount: `${payment['amount']:,.2f}`\n"
        f"Description: `{payment['description']}`\n\n"
    )

    keyboard = []
    if match:
        text += (
            f"🤖 **AI Suggests Match:**\n"
            f"Driver: `{match['driver']}`, Row: `{match['row_num']}`"
        )
        keyboard = [
            [InlineKeyboardButton("✅ Approve", callback_data="approve:suggested")],
            [InlineKeyboardButton("❌ Incorrect (Assign Manually)", callback_data="approve:manual")],
            [InlineKeyboardButton("⏭️ Skip Payment", callback_data="approve:skip")]
        ]
    else:
        text += "🤖 **This payment is unmatched.**"
        keyboard = [
            [InlineKeyboardButton("✍️ Assign Manually", callback_data="approve:manual")],
            [InlineKeyboardButton("⏭️ Skip Payment", callback_data="approve:skip")]
        ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await context.bot.send_message(chat_id, text, reply_markup=reply_markup, parse_mode='Markdown')
        
    return AWAIT_PAYMENT_APPROVAL

# --- HANDLERS FOR THE REVIEW LOOP ---

async def handle_approval_decision(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the user's choice: Approve, Assign Manually, or Skip."""
    query = update.callback_query
    await query.answer()
    decision = query.data.split(':')[1]

    if decision == 'skip':
        context.user_data['payment_review_index'] += 1
        return await process_next_payment(update, context)

    if decision == 'manual':
        await query.edit_message_text(text="OK. Please provide the driver and row number in `Driver Row` format (e.g., `Walter 543`).")
        return AWAIT_MANUAL_ASSIGNMENT

    if decision == 'suggested':
        idx = context.user_data['payment_review_index']
        item = context.user_data['all_payments_for_review'][idx]
        context.user_data['active_match'] = item['suggested_match']
        return await check_date_and_proceed(query, context)

async def handle_manual_assignment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Parses user input for manual assignment and proceeds."""
    assignment = payment_repository.parse_manual_assignment(update.message.text)
    if not assignment:
        await update.message.reply_text("❌ Invalid format. Please use `Driver Row` (e.g., `Walter 543`).")
        return AWAIT_MANUAL_ASSIGNMENT
        
    driver, row = assignment
    idx = context.user_data['payment_review_index']
    payment = context.user_data['all_payments_for_review'][idx]['payment']
    
    # Construct a 'match_info' object for the manual assignment
    context.user_data['active_match'] = {
        'driver': driver,
        'row_num': row,
        'paid_amount': payment['amount'],
        'paid_date': payment['date']
    }
    
    return await check_date_and_proceed(update, context)

async def check_date_and_proceed(update_or_query, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Central function to validate a date and then ask for a screenshot."""
    match_info = context.user_data['active_match']
    paid_date_str = match_info['paid_date']
    
    final_date_to_upload = None
    if 'pending' in paid_date_str.lower(): pass
    else:
        try:
            date_obj = datetime.strptime(paid_date_str, "%b %d, %Y")
            final_date_to_upload = date_obj.strftime("%m/%d/%Y")
        except ValueError: pass

    message_sender = update_or_query.edit_message_text if hasattr(update_or_query, 'edit_message_text') else update_or_query.message.reply_text

    if not final_date_to_upload:
        await message_sender(
            f"⚠️ **Invalid Date!** The date is `'{paid_date_str}'`.\nPlease reply with the correct date in **MM/DD/YYYY** format."
        )
        return AWAIT_DATE_CORRECTION

    match_info['paid_date'] = final_date_to_upload
    try:
        await payment_repository.update_sheet_with_payment(
            driver=match_info['driver'], row=match_info['row_num'],
            amount=match_info['paid_amount'], date=final_date_to_upload
        )
        await message_sender(
            f"✅ Sheet Updated!\nRow `{match_info['row_num']}` is marked as paid.\n\n**Now, please upload the payment screenshot.**"
        )
        return AWAIT_SCREENSHOT
    except Exception as e:
        await message_sender(f"❌ Error updating sheet: {e}")
        return ConversationHandler.END

async def handle_date_correction(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Logic for this is the same, but now it proceeds to the screenshot step
    corrected_date_str = update.message.text.strip()
    try:
        datetime.strptime(corrected_date_str, "%m/%d/%Y")
    except ValueError:
        await update.message.reply_text("❌ Invalid format. Use **MM/DD/YYYY**.")
        return AWAIT_DATE_CORRECTION

    match_info = context.user_data['active_match']
    match_info['paid_date'] = corrected_date_str
    
    return await check_date_and_proceed(update, context)


async def handle_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Screenshot received, uploading...")
    match_info = context.user_data['active_match']
    
    photo_file = await update.message.photo[-1].get_file()
    os.makedirs("./files_cash", exist_ok=True)
    local_path = f"./files_cash/payment_{match_info['driver']}_{match_info['row_num']}.jpg"
    await photo_file.download_to_drive(local_path)

    try:
        await payment_repository.upload_payment_screenshot(
            local_path=local_path, driver=match_info['driver'], row=match_info['row_num']
        )
        await update.message.reply_text("✅ Screenshot uploaded and linked!")
    except Exception as e:
        await update.message.reply_text(f"❌ Could not upload screenshot: {e}")
    finally:
        if os.path.exists(local_path): os.remove(local_path)

    del context.user_data['active_match']
    context.user_data['payment_review_index'] += 1
    return await process_next_payment(update, context)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Operation cancelled.")
    return ConversationHandler.END

def handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(start, pattern="^act:check_payments$")],
        states={
            AWAIT_PDF: [MessageHandler(filters.Document.PDF, handle_pdf)],
            AWAIT_RANGES: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_ranges_and_terminal_io)],
            AWAIT_PAYMENT_APPROVAL: [CallbackQueryHandler(handle_approval_decision, pattern="^approve:")],
            AWAIT_MANUAL_ASSIGNMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_manual_assignment)],
            AWAIT_DATE_CORRECTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_date_correction)],
            AWAIT_SCREENSHOT: [MessageHandler(filters.PHOTO, handle_screenshot)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
