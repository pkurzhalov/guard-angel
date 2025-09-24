from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Optional, Tuple

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from PyPDF2 import PdfReader, PdfMerger

from ..config import settings
from ..services import sheets

# Conversation states
CHOOSE_DRIVER, ENTER_CELL, INSURANCE_DATE, WAIT_STATEMENT_PDF = range(4)


# -------------------------
# Guards & helpers
# -------------------------
async def _guard(update: Update) -> bool:
    uid = update.effective_user.id if update.effective_user else None
    if uid not in settings.authorized_users:
        if update.message:
            await update.message.reply_text("You are not authorized to use this bot.")
        elif update.callback_query:
            await update.callback_query.answer("Not authorized", show_alert=True)
        return False
    return True

def _parse_mmddyyyy(s: str) -> datetime:
    return datetime.strptime(s.strip(), "%m/%d/%Y")

# -------------------------
# PDF helpers (owner-ops)
# -------------------------
def _extract_totals(p: str) -> Optional[float]:
    with open(p, "rb") as f:
        page = PdfReader(f).pages[0]
        for line in (page.extract_text() or "").splitlines():
            if re.match(r"Totals (\d[\d,\.]*)", line):
                return float(line.split()[1].replace(",", ""))
    return None

def _extract_discount(p: str) -> Optional[float]:
    with open(p, "rb") as f:
        page = PdfReader(f).pages[0]
        for line in (page.extract_text() or "").splitlines():
            if re.match(r"Total Discount (\d[\d,\.]*)", line):
                return float(line.split()[2].replace(",", ""))
    return None

def _extract_dates(p: str) -> Tuple[Optional[str], Optional[str]]:
    with open(p, "rb") as f:
        page = PdfReader(f).pages[0]
        for line in (page.extract_text() or "").splitlines():
            if re.match(r"Transaction Date\d{4}-\d{2}-\d{2}", line):
                dates = re.findall(r"\d{4}-\d{2}-\d{2}", line)
                if len(dates) >= 2:
                    # old logic: last as start, first as end
                    return dates[-1], dates[0]
    return None, None

# -------------------------
# Conversation handlers
# -------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        return ConversationHandler.END

    kb = [
        [
            InlineKeyboardButton("Yura", callback_data="driver:Yura"),
            InlineKeyboardButton("Walter", callback_data="driver:Walter"),
            InlineKeyboardButton("Nestor", callback_data="driver:Nestor"),
        ],
        [
            InlineKeyboardButton("Javier", callback_data="driver:Javier"),
            InlineKeyboardButton("Peter", callback_data="driver:Peter"),
        ],
    ]
    text = "Choose a driver/tab to count salary:"
    if update.message:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))
    else:
        q = update.callback_query; await q.answer()
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
    return CHOOSE_DRIVER

async def pick_driver(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    driver = q.data.split(":", 1)[1]
    context.user_data["driver"] = driver
    await q.edit_message_text(f"Driver: {driver}\n\nSend row number (cell) to process:")
    return ENTER_CELL


async def enter_cell(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        return ConversationHandler.END

    txt = (update.message.text or '').strip()
    try:
        row = int(txt)
        if row <= 0:
            raise ValueError
    except Exception:
        return await update.message.reply_text('Enter a positive row number (e.g., 215).')

    driver = context.user_data.get('driver')
    await update.message.reply_text(f'Processing salary for {driver} row {row}…')

    # Try to detect period from sheet (works for company drivers)
    start_date = end_date = None
    try:
        start_date, end_date = sheets.get_start_end_dateForCompanyDriversSalary(row, driver)
        await update.message.reply_text(f'🗓 Period detected:\nStart: {start_date}\nEnd:   {end_date}')
    except Exception as e:
        await update.message.reply_text(f'⚠️ Could not detect start/end dates: {e}')

    # Company drivers -> build/upload statement natively (ported from legacy)
    if driver in ('Walter', 'Nestor'):
        try:
            from pathlib import Path
            Path('./files_cash').mkdir(exist_ok=True)

            start_val = (start_date or '').replace('/', '-')
            end_val   = (end_date or '').replace('/', '-')

            # Build first page
            sheets.compilate_salary_company_driver(driver, row, start_date=start_val, end_date=end_val)

            # Merge single page to final filename (keeps legacy naming)
            from PyPDF2 import PdfMerger
            merger = PdfMerger()
            merger.append('./files_cash/1st_page.pdf')
            out_name = f'Statement_{driver}_{end_val or "period"}.pdf'
            merger.write(out_name)
            merger.close()

            # Cleanup temp pages
            import os
            for f in os.listdir('./files_cash'):
                try: os.remove(f'./files_cash/' + f)
                except Exception: pass

            # Upload to Drive + update sheet like legacy
            sheets.upload_file(file_name=out_name, driver_name=driver, cell=row)
            sheets.update_cell(driver=driver, cell=row, letter='Y', value='no insurance')

            # Pull the link from the row and send a button + attach PDF
            Load = sheets.open_invoice_load(driver, row)
            statement_url = Load[0][23] if Load and Load[0] and len(Load[0]) > 23 else None
            if statement_url:
                kb = [[InlineKeyboardButton('👉 Statement🔍👈', url=statement_url)]]
                await update.message.reply_text('Please check the Statement\n\n/start', reply_markup=InlineKeyboardMarkup(kb))

            try:
                with open(out_name, 'rb') as doc:
                    await update.message.reply_document(document=doc)
            except Exception as e:
                await update.message.reply_text(f'Could not attach PDF: {e}')
            try:
                os.remove(out_name)
            except Exception:
                pass
        except Exception as e:
            await update.message.reply_text(f'❌ Salary build/upload failed: {e}')
    else:
        # Owner-operator path still uses uploaded fuel PDF; we can wire it next.
        await update.message.reply_text('Owner-operator flow (fuel PDF) not wired yet in this step.')

    await update.message.reply_text('✅ Done.')
    return ConversationHandler.END


def handler() -> ConversationHandler:
    return ConversationHandler(
        
        entry_points=[CommandHandler("count_salary", start), CallbackQueryHandler(start, pattern="^act:count_salary$")],
        states={
            CHOOSE_DRIVER: [CallbackQueryHandler(pick_driver, pattern=r"^driver:.+")],
            ENTER_CELL: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_cell)],
            INSURANCE_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_cell)],  # keep placeholder
            WAIT_STATEMENT_PDF: [MessageHandler(filters.Document.PDF, enter_cell)],         # keep placeholder
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)],
    )