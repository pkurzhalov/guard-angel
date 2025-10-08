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

# --- NEW: Added states for the multi-load assignment workflow ---
(
    AWAIT_PDF, AWAIT_RANGES,
    AWAIT_PAYMENT_APPROVAL, AWAIT_MANUAL_ASSIGNMENT,
    AWAIT_DATE_CORRECTION, AWAIT_SCREENSHOT,
    AWAIT_SPLIT_COUNT, AWAIT_SPLIT_ASSIGNMENT, AWAIT_SPLIT_SCREENSHOT
) = range(9)


# --- CORE WORKFLOW FUNCTIONS ---
# Functions: start, handle_pdf, handle_ranges_and_terminal_io are UNCHANGED.
# For brevity, I'll skip them, but they should remain in your file.
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
            "Example: Walter 518\\-543; Nestor 54\\-74"
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
        
        # --- UNCHANGED: Create the unified review list ---
        matched_loads = ai_data.get('matched_loads', [])
        unmatched_payments = ai_data.get('unmatched_payments', [])
        all_payments_for_review = []
        
        # Add matched/suggested payments
        processed_payment_identifiers = set()
        for m in matched_loads:
            identifier = (m['paid_amount'], m['paid_date'])
            payment = next((p for p in payments if p['amount'] == m['paid_amount'] and p['date'] == m['paid_date']), None)
            if payment:
                all_payments_for_review.append({'payment': payment, 'suggested_match': m})
                processed_payment_identifiers.add(identifier)

        # Add truly unmatched payments
        for p in payments:
            if (p['amount'], p['date']) not in processed_payment_identifiers:
                 all_payments_for_review.append({'payment': p, 'suggested_match': None})
        
        context.user_data['all_payments_for_review'] = all_payments_for_review
        context.user_data['payment_review_index'] = 0
        
        await context.bot.send_message(chat_id, text="✅ AI response parsed! Starting sequential payment review...")
        return await process_next_payment(update, context)

    except Exception as e:
        error_msg = f"❌ Processing Failed in Terminal: {e}"
        print(error_msg)
        await context.bot.send_message(chat_id, text=error_msg)
        return ConversationHandler.END


# --- SEQUENTIAL REVIEW LOOP ---

async def process_next_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """The main loop function. Processes payments one by one from the statement."""
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
        # --- MODIFIED: New options for unmatched payments ---
        text += "🤖 **This payment is unmatched.**"
        keyboard = [
            [InlineKeyboardButton("✍️ Assign to Load(s)", callback_data="approve:split_manual")],
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
        
    # --- NEW: Handle the start of the split-payment flow ---
    if decision == 'split_manual':
        idx = context.user_data['payment_review_index']
        payment = context.user_data['all_payments_for_review'][idx]['payment']
        context.user_data['split_payment_info'] = {'original_payment': payment}
        await query.edit_message_text(text=f"This payment is for `${payment['amount']:,.2f}`.\n\nHow many loads does this single payment cover?")
        return AWAIT_SPLIT_COUNT

    # The rest of this function handles the 1-to-1 manual assignment and approval
    if decision == 'manual':
        await query.edit_message_text(text="OK. Please provide the driver and row number in `Driver Row` format (e.g., `Walter 543`).")
        return AWAIT_MANUAL_ASSIGNMENT

    if decision == 'suggested':
        idx = context.user_data['payment_review_index']
        item = context.user_data['all_payments_for_review'][idx]
        context.user_data['active_match'] = item['suggested_match']
        return await check_date_and_proceed(query, context)

# --- UNCHANGED FUNCTIONS for 1-to-1 flow ---
# handle_manual_assignment, check_date_and_proceed, handle_date_correction, handle_screenshot
# They should remain in your file.
async def handle_manual_assignment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    assignment = payment_repository.parse_manual_assignment(update.message.text)
    if not assignment:
        await update.message.reply_text("❌ Invalid format. Please use `Driver Row` (e.g., `Walter 543`).")
        return AWAIT_MANUAL_ASSIGNMENT
    driver, row = assignment
    idx = context.user_data['payment_review_index']
    payment = context.user_data['all_payments_for_review'][idx]['payment']
    context.user_data['active_match'] = {
        'driver': driver, 'row_num': row,
        'paid_amount': payment['amount'], 'paid_date': payment['date']
    }
    return await check_date_and_proceed(update, context)

async def check_date_and_proceed(update_or_query, context: ContextTypes.DEFAULT_TYPE) -> int:
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


# --- NEW: HANDLERS FOR THE SPLIT-PAYMENT SUB-LOOP ---

async def handle_split_count(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receives how many loads the payment covers and starts the loop."""
    try:
        count = int(update.message.text)
        if count <= 0: raise ValueError
        context.user_data['split_payment_info']['total_loads'] = count
        context.user_data['split_payment_info']['processed_loads'] = 0
        
        await update.message.reply_text(
            f"OK, we will process {count} loads for this payment.\n\n"
            f"**For load 1 of {count}**, please provide the details in `Driver Row Amount` format.\n"
            f"Example: `Walter 543 1250.50`"
        )
        return AWAIT_SPLIT_ASSIGNMENT
    except (ValueError, TypeError):
        await update.message.reply_text("Invalid number. Please enter a positive whole number (e.g., 2).")
        return AWAIT_SPLIT_COUNT

async def handle_split_assignment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Parses 'Driver Row Amount' and updates the sheet."""
    # Simple regex to get the parts. Add more robust parsing if needed.
    parts = update.message.text.strip().split()
    if len(parts) != 3:
        await update.message.reply_text("❌ Invalid format. Please use `Driver Row Amount` (e.g., `Walter 543 1250.50`).")
        return AWAIT_SPLIT_ASSIGNMENT
    
    try:
        driver, row, amount = parts[0].capitalize(), int(parts[1]), float(parts[2])
    except ValueError:
        await update.message.reply_text("❌ Invalid format. Row and Amount must be numbers.")
        return AWAIT_SPLIT_ASSIGNMENT

    split_info = context.user_data['split_payment_info']
    original_payment = split_info['original_payment']

    # We need a temporary 'active_match' for the screenshot function to use
    context.user_data['active_match'] = {'driver': driver, 'row_num': row}
    
    # Use the date from the original payment
    date_str = original_payment['date']
    try:
        final_date = datetime.strptime(date_str, "%b %d, %Y").strftime("%m/%d/%Y")
    except ValueError:
        final_date = date_str # Keep as-is if format is weird, e.g., "Pending"

    try:
        await payment_repository.update_sheet_with_payment(driver, row, amount, final_date)
        await update.message.reply_text(
            f"✅ Sheet updated for {driver} row {row}.\n\n"
            "**Now, please upload the payment screenshot for this load.**"
        )
        return AWAIT_SPLIT_SCREENSHOT
    except Exception as e:
        await update.message.reply_text(f"❌ Error updating sheet: {e}")
        # Clean up and move to the next main payment
        del context.user_data['split_payment_info']
        context.user_data['payment_review_index'] += 1
        return await process_next_payment(update, context)


async def handle_split_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the screenshot for one of the split loads and continues the sub-loop."""
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
    
    # --- Loop logic ---
    split_info = context.user_data['split_payment_info']
    split_info['processed_loads'] += 1
    
    if split_info['processed_loads'] >= split_info['total_loads']:
        # Sub-loop is finished, move to the next main payment
        await update.message.reply_text("✅ All loads for this payment have been processed.")
        del context.user_data['split_payment_info']
        context.user_data['payment_review_index'] += 1
        return await process_next_payment(update, context)
    else:
        # Continue to the next load in the sub-loop
        current = split_info['processed_loads'] + 1
        total = split_info['total_loads']
        await update.message.reply_text(
            f"**For load {current} of {total}**, please provide the details in `Driver Row Amount` format."
        )
        return AWAIT_SPLIT_ASSIGNMENT


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels and ends the conversation."""
    # --- MODIFIED: Clear potentially lingering state data on cancel ---
    for key in ['split_payment_info', 'active_match', 'all_payments_for_review']:
        if key in context.user_data:
            del context.user_data[key]
    
    await update.message.reply_text("Operation cancelled.")
    return ConversationHandler.END


def handler() -> ConversationHandler:
    # --- MODIFIED: Added the new states to the ConversationHandler ---
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(start, pattern="^act:check_payments$")],
        states={
            AWAIT_PDF: [MessageHandler(filters.Document.PDF, handle_pdf)],
            AWAIT_RANGES: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_ranges_and_terminal_io)],
            AWAIT_PAYMENT_APPROVAL: [CallbackQueryHandler(handle_approval_decision, pattern="^approve:")],
            AWAIT_MANUAL_ASSIGNMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_manual_assignment)],
            AWAIT_DATE_CORRECTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_date_correction)],
            AWAIT_SCREENSHOT: [MessageHandler(filters.PHOTO, handle_screenshot)],
            # New states for the sub-loop
            AWAIT_SPLIT_COUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_split_count)],
            AWAIT_SPLIT_ASSIGNMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_split_assignment)],
            AWAIT_SPLIT_SCREENSHOT: [MessageHandler(filters.PHOTO, handle_split_screenshot)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
