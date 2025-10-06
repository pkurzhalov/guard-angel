# FILE: guard_angel/handlers/check_payments.py

from telegram import Update
from telegram.helpers import escape_markdown
from telegram.ext import (
    ConversationHandler, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
)
from ..services import payment_repository

# Define conversation states
AWAIT_PDF, AWAIT_RANGES = range(2)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the check payments conversation."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(text="Please upload the payment statement PDF.")
    return AWAIT_PDF

async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the PDF upload using the robust MarkdownV2 parser."""
    file = await update.message.document.get_file()
    pdf_content = await file.download_as_bytearray()

    parsed_payments = payment_repository.parse_payment_pdf(bytes(pdf_content))
    context.user_data['payments'] = parsed_payments
    parse_mode_v2 = "MarkdownV2"
    
    async def send_chunk(lines_to_send):
        if len(lines_to_send) > 1:
            message_text = "```\n" + "\n".join(lines_to_send) + "\n```"
            await update.message.reply_text(message_text, parse_mode=parse_mode_v2)

    message_chunk_lines = ["Date         |      Amount | Description"]
    message_chunk_lines.append("-" * 50)
    
    if not parsed_payments or "Error" in parsed_payments[0]:
        error_message = parsed_payments[0].get("Error", "Could not parse any payments.")
        await update.message.reply_text(f"❌ *Error:* {error_message}", parse_mode=parse_mode_v2)
    else:
        for payment in parsed_payments:
            date_str = payment['date'].ljust(12)
            amount_str = f"${payment['amount']:>9,.2f}"
            description = payment.get('description', 'No description').strip()
            next_line = f"{date_str}| {amount_str} | {description[:50]}"

            if len("\n".join(message_chunk_lines)) + len(next_line) > 4000:
                await send_chunk(message_chunk_lines)
                message_chunk_lines = ["Date         |      Amount | Description", "-" * 50, next_line]
            else:
                message_chunk_lines.append(next_line)

    await send_chunk(message_chunk_lines)
    
    await update.message.reply_text(
        text=(
            "PDF parsed\. Now, please provide the load ranges\.\n\n"
            "*Format:* `Driver StartRow-EndRow; Driver2 Start-End`\n"
            "*Example:* `Walter 518-543; Nestor 54-74`"
        ),
        parse_mode=parse_mode_v2
    )
    return AWAIT_RANGES

async def handle_ranges(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the ranges using the original, lenient Markdown parser."""
    range_text = update.message.text
    await update.message.reply_text("Fetching data from Google Sheets, please wait...")
    summary_text = await payment_repository.fetch_payment_data(range_text)
    
    # --- THIS IS THE FIX: Reverting to the original "Markdown" ---
    await update.message.reply_text(text=summary_text, parse_mode="Markdown")
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels the conversation."""
    await update.message.reply_text("Operation cancelled. Send /start to see the main menu.")
    return ConversationHandler.END

def handler() -> ConversationHandler:
    """Creates the ConversationHandler for this feature."""
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(start, pattern="^act:check_payments$")],
        states={
            AWAIT_PDF: [MessageHandler(filters.Document.PDF, handle_pdf)],
            AWAIT_RANGES: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_ranges)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
