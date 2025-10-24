from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CommandHandler, ConversationHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)
from ..config import settings
from ..services import ifta_service
import os

# States
CHOOSE_ACTION, CHOOSE_DRIVER_MILES, AWAIT_QUARTER, AWAIT_FUEL_PDF = range(4)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    kb = [
        [InlineKeyboardButton("Calculate State Miles", callback_data="ifta:miles")],
        [InlineKeyboardButton("Parse Fuel Statement", callback_data="ifta:fuel")],
        [InlineKeyboardButton("Cancel", callback_data="ifta:cancel")]
    ]
    text = "Please choose an IFTA task:"
    if update.callback_query: await update.callback_query.answer(); await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
    else: await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))
    return CHOOSE_ACTION

async def choose_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query; await q.answer()
    action = q.data.split(":", 1)[1]
    if action == 'fuel':
        await q.edit_message_text("Please upload the fuel statement PDF.")
        return AWAIT_FUEL_PDF
    else: # miles
        drivers = settings.owner_operators + settings.company_drivers
        kb = [[InlineKeyboardButton(d, callback_data=f"driver:{d}")] for d in drivers]
        kb.append([InlineKeyboardButton("Back", callback_data="ifta:back")])
        await q.edit_message_text("Please select a driver for mileage calculation:", reply_markup=InlineKeyboardMarkup(kb))
        return CHOOSE_DRIVER_MILES

async def choose_driver_miles(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query; await q.answer()
    driver = q.data.split(":", 1)[1]
    context.user_data['driver'] = driver
    kb = [
        [InlineKeyboardButton("Q1", callback_data="q:1"), InlineKeyboardButton("Q2", callback_data="q:2")],
        [InlineKeyboardButton("Q3", callback_data="q:3"), InlineKeyboardButton("Q4", callback_data="q:4")]
    ]
    await q.edit_message_text(f"Driver set to {driver}. Please select a quarter:", reply_markup=InlineKeyboardMarkup(kb))
    return AWAIT_QUARTER

async def handle_quarter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # This function must now be async
    q = update.callback_query; await q.answer()
    quarter = int(q.data.split(":", 1)[1])
    driver = context.user_data['driver']

    # Send the initial message that will be updated
    await q.edit_message_text(f"Calculating IFTA miles for {driver}, Q{quarter}. Starting...")

    # Call the updated service function, which will now handle the progress bar
    # and pass the update and context objects to it.
    result_text = await ifta_service.calculate_quarterly_miles(driver, quarter, update, context)

    # Edit the message a final time with the results
    await q.edit_message_text(result_text, parse_mode="Markdown")
    return ConversationHandler.END

async def handle_fuel_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Processing fuel statement...")
    file = await update.message.document.get_file()

    # Define the directory and filename
    cash_dir = "./files_cash"
    pdf_path = f"{cash_dir}/ifta_fuel_{update.effective_user.id}.pdf"

    # 🌟 FIX: Create the directory if it doesn't exist 🌟
    os.makedirs(cash_dir, exist_ok=True)

    context.user_data['temp_file'] = pdf_path
    await file.download_to_drive(pdf_path)

    result_text = ifta_service.parse_fuel_statement(pdf_path)
    await update.message.reply_text(result_text, parse_mode="Markdown")
    os.remove(pdf_path)
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = "Operation cancelled. Send /start to see the main menu."

    # Clean up the specific temp file created by the IFTA fuel workflow
    temp_file = context.user_data.get('temp_file')
    if temp_file and os.path.exists(temp_file):
        os.remove(temp_file)

    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text(text)
    else:
        await update.message.reply_text(text)

    return ConversationHandler.END

def handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(start, pattern="^act:count_ifta$")],
        states={
            CHOOSE_ACTION: [CallbackQueryHandler(choose_action, pattern="^ifta:(miles|fuel)$")],
            CHOOSE_DRIVER_MILES: [
                CallbackQueryHandler(choose_driver_miles, pattern="^driver:.+"),
                CallbackQueryHandler(start, pattern="^ifta:back$")
            ],
            AWAIT_QUARTER: [CallbackQueryHandler(handle_quarter, pattern="^q:\d$")],
            AWAIT_FUEL_PDF: [MessageHandler(filters.Document.PDF, handle_fuel_pdf)],
        },
        fallbacks=[CallbackQueryHandler(cancel, pattern="^ifta:cancel$")],
    )
