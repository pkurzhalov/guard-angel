from __future__ import annotations
import os
import re
from datetime import datetime
from typing import Dict, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CallbackQueryHandler, CommandHandler, ConversationHandler,
    ContextTypes, MessageHandler, filters
)
from PyPDF2 import PdfReader, PdfMerger
from ..config import settings
from ..services import sheets

STATE_CHOOSE_DRIVER, STATE_ENTER_CELL, STATE_INSURANCE_DATE, STATE_WAIT_STATEMENT_PDF = range(4)
COMPANY_DRIVERS = settings.company_drivers
OWNER_OPERATORS = settings.owner_operators

def _cleanup_files(context: ContextTypes.DEFAULT_TYPE):
    for fp in context.user_data.get("temp_files", []):
        try: os.remove(fp)
        except OSError: pass

async def start_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    drivers = settings.owner_operators + settings.company_drivers
    kb = [[InlineKeyboardButton(d, callback_data=f"driver:{d}")] for d in drivers]
    kb.append([InlineKeyboardButton("Cancel", callback_data="action:cancel")])
    text = "Please choose a driver:"
    if update.message: await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))
    elif update.callback_query: await update.callback_query.answer(); await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
    return STATE_CHOOSE_DRIVER

async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    _cleanup_files(context); context.user_data.clear()
    await update.message.reply_text("Operation cancelled. Send /start to see the main menu.")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    _cleanup_files(context); context.user_data.clear()
    q = update.callback_query; await q.answer()
    await q.edit_message_text("Operation cancelled. Send /start to see the main menu.")
    return ConversationHandler.END

async def handle_driver_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query; await q.answer()
    driver = q.data.split(":", 1)[1]
    context.user_data["driver"] = driver
    await q.edit_message_text(f"Driver set to **{driver}**.\n\nPlease send the starting row number.", parse_mode="Markdown")
    return STATE_ENTER_CELL

async def handle_cell_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try: cell = int(update.message.text)
    except (ValueError, TypeError): return STATE_ENTER_CELL
    context.user_data["cell"] = cell; driver = context.user_data["driver"]
    await update.message.reply_text(f"Starting at row **{cell}** for **{driver}**.", parse_mode="Markdown")
    if driver in COMPANY_DRIVERS: return await process_company_driver_salary(update, context)
    elif driver in OWNER_OPERATORS:
        await update.message.reply_text("Owner-Operator: Provide insurance end date (`MM/DD/YYYY`)")
        return STATE_INSURANCE_DATE
    return ConversationHandler.END

async def handle_insurance_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try: insurance_end_date = datetime.strptime(update.message.text, "%m/%d/%Y")
    except ValueError:
        await update.message.reply_text("Invalid date format. Please use `MM/DD/YYYY`.")
        return STATE_INSURANCE_DATE
    driver = context.user_data["driver"]; cell = context.user_data["cell"]
    try:
        prev_insurance_date = datetime.strptime(sheets.open_prev_insurance(driver, cell)[0].split('-')[1], "%m/%d/%Y")
        diff_days = (insurance_end_date - prev_insurance_date).days
        if diff_days < 0:
            await update.message.reply_text("End date cannot be before the previous period's end date.")
            return STATE_INSURANCE_DATE
        weeks = (diff_days // 7) + (1 if diff_days % 7 > 0 else 0)
        context.user_data["insurance_payment"] = weeks * settings.get_insurance_pay(driver)
        context.user_data["trailer_payment"] = weeks * settings.get_trailer_pay(driver)
        context.user_data["insurance_period_str"] = f"{prev_insurance_date.strftime('%m/%d/%Y')}-{insurance_end_date.strftime('%m/%d/%Y')}"
        await update.message.reply_text(f"Calculated **{weeks}** week(s) of deductions.\n\n**Please upload the fuel statement PDF**.", parse_mode="Markdown")
        return STATE_WAIT_STATEMENT_PDF
    except Exception as e:
        await update.message.reply_text(f"Error calculating insurance: {e}.\nCancelling.")
        return ConversationHandler.END

def extract_from_fuel_pdf(pdf_path: str) -> Dict[str, Any]:
    results = {"totals": 0.0, "discount": 0.0, "start_date": None, "end_date": None}
    try:
        with open(pdf_path, "rb") as f:
            reader = PdfReader(f)
            page_text = reader.pages[0].extract_text() or ""
            for line in page_text.splitlines():
                if match := re.match(r"Totals (\d[\d,\.]*)", line): results["totals"] = float(match.group(1).replace(",", ""))
                elif match := re.match(r"Total Discount (\d[\d,\.]*)", line): results["discount"] = float(match.group(1).replace(",", ""))
                elif re.match(r"Transaction Date\d{4}-\d{2}-\d{2}", line):
                    dates = re.findall(r"\d{4}-\d{2}-\d{2}", line)
                    if len(dates) >= 2: results["start_date"], results["end_date"] = dates[-1], dates[0]
    except Exception as e: print(f"Error extracting from fuel PDF: {e}")
    return results

async def handle_fuel_statement(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    pdf_file = await update.message.document.get_file()
    fuel_pdf_path = f"./files_cash/fuel_statement_{update.effective_user.id}.pdf"
    context.user_data.setdefault("temp_files", []).append(fuel_pdf_path)
    os.makedirs(os.path.dirname(fuel_pdf_path), exist_ok=True)
    await pdf_file.download_to_drive(fuel_pdf_path)
    await update.message.reply_text("Fuel statement received, processing...")
    fuel_data = extract_from_fuel_pdf(fuel_pdf_path)
    context.user_data.update(fuel_data)
    return await process_owner_operator_salary(update, context, fuel_pdf_path)

async def process_company_driver_salary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    driver = context.user_data["driver"]; cell = context.user_data["cell"]
    try:
        final_pdf_name = f"Statement_{driver}_{datetime.now().strftime('%m-%d-%Y')}.pdf"
        context.user_data.setdefault("temp_files", []).extend(["./files_cash/1st_page.pdf", final_pdf_name])
        sheets.compilate_salary_company_driver(driver, cell, "", "")
        os.rename("./files_cash/1st_page.pdf", final_pdf_name)
        await update.message.reply_text("Uploading to Google Drive...")
        sheets.upload_file(final_pdf_name, driver, cell)
        sheets.update_cell(driver, cell, 'Y', 'no insurance')
        with open(final_pdf_name, 'rb') as doc: await update.message.reply_document(document=doc)
        await update.message.reply_text("✅ Statement created!")
    except Exception as e: await update.message.reply_text(f"❌ An error occurred: {e}")
    finally: _cleanup_files(context); return ConversationHandler.END

async def process_owner_operator_salary(update: Update, context: ContextTypes.DEFAULT_TYPE, fuel_pdf_path: str) -> int:
    ud = context.user_data
    driver, cell = ud["driver"], ud["cell"]
    try:
        await update.message.reply_text("Generating final statement PDF...")
        sheets.compilate_salary_page(
            driver=driver, cell=cell, 
            fuel_start_date=ud.get("start_date"), fuel_end_date=ud.get("end_date"),
            totals=ud.get("totals", 0), discount=ud.get("discount", 0),
            insurance=ud.get("insurance_payment", 0), insurance_d=ud.get("insurance_period_str", ""),
            trailer=ud.get("trailer_payment", 0), trailer_d=f"Trailer Payment for {driver}"
        )
        first_page_path = "./files_cash/1st_page.pdf"
        final_pdf_name = f"Statement_{driver}_{datetime.now().strftime('%m-%d-%Y')}.pdf"
        ud.setdefault("temp_files", []).extend([first_page_path, final_pdf_name])
        merger = PdfMerger()
        merger.append(first_page_path)
        merger.append(fuel_pdf_path)
        merger.write(final_pdf_name)
        merger.close()
        
        await update.message.reply_text("Uploading to Google Drive...")
        sheets.upload_file(final_pdf_name, driver, cell)
        sheets.update_cell(driver, cell, 'Y', ud["insurance_period_str"])
        
        with open(final_pdf_name, 'rb') as doc: await update.message.reply_document(document=doc)
        await update.message.reply_text("✅ Owner-Operator Statement created!")
    except Exception as e:
        await update.message.reply_text(f"❌ An error occurred during final processing: {e}")
    finally:
        _cleanup_files(context)
        return ConversationHandler.END

def handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("count_salary", start_conversation), CallbackQueryHandler(start_conversation, pattern="^act:count_salary$")],
        states={
            STATE_CHOOSE_DRIVER: [CallbackQueryHandler(handle_driver_choice, pattern=r"^driver:.+")],
            STATE_ENTER_CELL: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_cell_entry)],
            STATE_INSURANCE_DATE: [MessageHandler(filters.Regex(r'^\d{1,2}/\d{1,2}/\d{4}$'), handle_insurance_date)],
            STATE_WAIT_STATEMENT_PDF: [MessageHandler(filters.Document.PDF, handle_fuel_statement)],
        },
        fallbacks=[CommandHandler("start", restart), CallbackQueryHandler(cancel, pattern="^action:cancel$")],
    )
