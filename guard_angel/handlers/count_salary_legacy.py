#!/usr/bin/python3
import re
import os
import shutil
from datetime import datetime, timedelta
from PyPDF2 import PdfReader, PdfMerger  # Updated: use PdfMerger instead of PdfFileMerger
import PyPDF2

from telegram.ext.updater import Updater  # contains API key for the bot
from telegram.update import Update  # invoked every time the bot receives an update
from telegram.ext.callbackcontext import CallbackContext  # required for adding the dispatcher
from telegram.ext.commandhandler import CommandHandler  # to handle any command
from telegram.ext.messagehandler import MessageHandler  # to handle any message
from telegram.ext import Filters  # to filter text, commands, images, etc. from a message
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, User

import config
import sheets
# import browser_fuel  # REMOVED because we now let the user generate the statement manually

AUTHORIZED_USERS = config.AUTHORIZED_USERS

updater = Updater(config.API_count_salary, use_context=True)

# Global variables to keep state
driver = None
cell = None
card_number = None
totals = None
discount = None
start_date = None
end_date = None
insurance_payment_final = None
insurance_print_global = None

trailer_payment_final = None
trailer_print_global = None


def user_authorized(update: Update, context: CallbackContext) -> bool:
    user: User = update.effective_user
    if user.id not in AUTHORIZED_USERS:
        update.message.reply_text("You are not authorized to use this bot.")
        return False
    return True

def start(update: Update, context: CallbackContext):
    if not user_authorized(update, context):
        return
    update.message.reply_text(
        "Please choose a driver to count salary:\n"
        "/Yura or /Walter or /Nestor"
    )

def unknown(update: Update, context: CallbackContext):
    if not user_authorized(update, context):
        return
    update.message.reply_text("Sorry '%s' is not a valid command" % update.message.text)

def yura(update: Update, context: CallbackContext):
    if not user_authorized(update, context):
        return
    global driver, card_number
    card_number = "5014861179138300013"
    driver = 'Yura'
    update.message.reply_text(f"You chose {driver}. Now enter cell#")

def walter(update: Update, context: CallbackContext):
    if not user_authorized(update, context):
        return
    global driver, card_number
    card_number = "5014861179138300013"
    driver = 'Walter'
    update.message.reply_text(f"You chose {driver}. Now enter cell#")

def nestor(update: Update, context: CallbackContext):
    if not user_authorized(update, context):
        return
    global driver, card_number
    card_number = "5014861179138300070"
    driver = 'Nestor'
    update.message.reply_text(f"You chose {driver}. Now enter cell#")
#
# def Javier(update: Update, context: CallbackContext):
#     if not user_authorized(update, context):
#         return
#     global driver, card_number
#     card_number = "5014861179138300054"
#     driver = 'Javier'
#     update.message.reply_text(f"You chose {driver}. Now enter cell#")

def get_id_from_link(link):
    start = "/d/"
    end = "/view"
    return link[(link.index(start)+3):link.index(end)]

def cell(update: Update, context: CallbackContext):
    """
    Handler for cell number input.
    """
    if not user_authorized(update, context):
        return
    try:
        user_input = int(update.message.text)
    except ValueError:
        update.message.reply_text("That doesn't look like a valid cell number. Try again.")
        return

    global cell
    cell = user_input
    update.message.reply_text(f"You entered {driver} and cell {cell}.")

    if driver not in ["Walter", "Nestor"]:
        update.message.reply_text(
            f"Now enter insurance date (MM/DD/YYYY)\n\n"
            f"If you did something wrong press /start"
        )
    else:
        if driver == 'Walter':
            update.message.reply_text("Walter works as a company driver, we don't count insurance for him.")
        else:
            update.message.reply_text("Nestor works as a company driver, we don't count insurance for him.")
        update.message.reply_text(
            f"Now press /Count_salary\n\nIf you did something wrong press /start"
        )

def download_statement(update, context):
    """
    Instead of using browser_fuel to download the statement, this function instructs the user
    to manually generate/download the fuel statement PDF. It sends the necessary variables for
    the manual process, and then waits for the user to upload the PDF statement into the chat.

    When a PDF is uploaded, it is processed to extract totals, discount, and date range.
    """
    if not user_authorized(update, context):
        return

    # Check if a PDF document has been provided by the user
    if update.message.document and update.message.document.file_name.lower().endswith('.pdf'):
        file = update.message.document.get_file()
        destination = f"./files_cash/{driver}_Statement_{cell}.pdf"
        file.download(destination)
        update.message.reply_text("Statement received. Processing statement...")

        def extract_fuel(file_name):
            with open(file_name, 'rb') as pdf_file:
                pdfdoc_2 = PdfReader(pdf_file)
                page_one = pdfdoc_2.pages[0]
                page_text = page_one.extract_text().strip().split('\n')
                for line in page_text:
                    if re.match(r"Totals (\d[\d,\.]*)", line):
                        totals_val = line.split(' ')[1].replace(',', '')
                        return float(totals_val)

        def extract_disc(file_name):
            with open(file_name, 'rb') as pdf_file:
                pdfdoc_2 = PdfReader(pdf_file)
                page_one = pdfdoc_2.pages[0]
                page_text = page_one.extract_text().strip().split('\n')
                for line in page_text:
                    if re.match(r"Total Discount (\d[\d,\.]*)", line):
                        discount_val = line.split(' ')[2].replace(',', '')
                        return float(discount_val)

        def extract_dates(file_name):
            with open(file_name, 'rb') as pdf_file:
                pdfdoc_2 = PdfReader(pdf_file)
                page_one = pdfdoc_2.pages[0]
                page_text = page_one.extract_text().strip().split('\n')
                for line in page_text:
                    if re.match(r"Transaction Date\d{4}-\d{2}-\d{2}", line):
                        dates = re.findall(r"\d{4}-\d{2}-\d{2}", line)
                        if len(dates) >= 2:
                            start_date_pdf = dates[-1]
                            end_date_pdf = dates[0]
                            return start_date_pdf, end_date_pdf
                        return None, None

        global totals, discount, start_date, end_date
        totals = extract_fuel(destination)
        discount = extract_disc(destination)
        start_date, end_date = extract_dates(destination)
        update.message.reply_text("Statement processed. You can now press /Count_salary to continue.")
        return

    # If no PDF is uploaded, use the previous statement to extract dates and prompt the user.
    prev_statement = sheets.open_prev_fuel(driver, cell)[0]
    prev_statement_id = get_id_from_link(prev_statement)
    sheets.download_file(file_id=prev_statement_id, name=f"prev_statement_{driver}.pdf")
    path = f"./files_cash/prev_statement_{driver}.pdf"
    with open(path, 'rb') as pdf:
        pdfdoc = PdfReader(pdf)
        n = 0
        PDF_DOC_LISTS = []
        while True:
            try:
                page = pdfdoc.pages[n]
                page_text_list = page.extract_text().split('\n')
                PDF_DOC_LISTS.append(page_text_list)
                n += 1
            except IndexError:
                break

    # Extract final_date from the previous statement PDF (assuming it's on a fixed line)
    final_date = PDF_DOC_LISTS[0][2][-10:]
    WASHED_STRINGS = []
    for page in PDF_DOC_LISTS:
        for string in page:
            if string.endswith("Currency"):
                start_index = page.index(string)
                if re.match(r"^\d{5}", page[start_index + 1][:5]):
                    for s in page[start_index + 1:]:
                        if s.startswith("Page") or s.startswith("Amount"):
                            break
                        else:
                            WASHED_STRINGS.append(s)
    last_fuel_date = WASHED_STRINGS[-1].split(" ")[1]
    today = datetime.today().strftime('%Y-%m-%d')
    os.remove(path)

    if final_date != last_fuel_date:
        message = (
            f"Detected that final statement date ({final_date}) is different from the last fuel date ({last_fuel_date}).\n"
            f"Please manually generate the fuel statement with the following parameters:\n"
            f"  - Start Date: {final_date}\n"
            f"  - End Date: {today}\n"
            f"  - Driver: {driver}\n"
            f"  - Card Number: {card_number}\n\n"
            f"Then, please upload the PDF statement in this chat."
        )
        update.message.reply_text(message)
    else:
        message = (
            f"Detected that the last fuel date ({last_fuel_date}) is the same as the final statement date ({final_date}).\n"
            f"Please manually download the statement.\n"
            f"NOTE: Since the dates are the same, double-check that no previous fuels are included in this statement "
            f"and that all fuels for the current period are present to avoid any double charging.\n\n"
            f"Parameters for reference:\n"
            f"  - Start Date: {final_date}\n"
            f"  - End Date: {today}\n"
            f"  - Driver: {driver}\n"
            f"  - Card Number: {card_number}\n\n"
            f"Then, please upload the PDF statement in this chat."
        )
        update.message.reply_text(message)
    return

def parse_date(date_string):
    return datetime.strptime(date_string, '%m/%d/%Y')

def calculate_insurance_payment(diff_days, weekly_payment):
    weeks = diff_days // 7 + (diff_days % 7 > 0)
    return weekly_payment * weeks



def insurance_date(update, context):
    if not user_authorized(update, context):
        return
    global insurance_payment_final, insurance_print_global, trailer_payment_final, trailer_print_global
    insurance_date_input = update.message.text
    input_date = parse_date(insurance_date_input)

    # Calculate insurance payment
    prev_insurance_str = sheets.open_prev_insurance(driver, cell)[0].split('-')[1]
    prev_insurance_date = parse_date(prev_insurance_str)
    cut_off_date = datetime(2023, 6, 30)

    if prev_insurance_date > cut_off_date:
        diff = (input_date - prev_insurance_date).days
        insurance_payment_final = calculate_insurance_payment(
            diff,
            config.get_insurance_pay(driver, input_date)
        )
        trailer_payment_final = calculate_insurance_payment(
            diff,
            config.trailer_payment
        )
    else:
        if input_date <= cut_off_date:
            diff = (input_date - prev_insurance_date).days
            insurance_payment_final = calculate_insurance_payment(
                diff,
                config.get_insurance_pay(driver, prev_insurance_date)
            )
            trailer_payment_final = calculate_insurance_payment(
                diff,
                config.trailer_payment
            )
        else:
            diff1 = (cut_off_date - prev_insurance_date).days
            diff2 = (input_date - cut_off_date - timedelta(days=1)).days
            insurance_payment_final = (
                calculate_insurance_payment(diff1, config.get_insurance_pay(driver, prev_insurance_date)) +
                calculate_insurance_payment(diff2, config.get_insurance_pay(driver, input_date))
            )
            trailer_payment_final = (
                calculate_insurance_payment(diff1, config.trailer_payment) +
                calculate_insurance_payment(diff2, config.trailer_payment)
            )

    insurance_print_global = f'{prev_insurance_date.strftime("%m/%d/%Y")}-{insurance_date_input}'
    trailer_print_global = f'Trailer payment for {driver}'

    update.message.reply_text(f"You entered {driver}, cell {cell} and insurance date {insurance_print_global}")
    update.message.reply_text(f"Insurance will be {insurance_payment_final}")
    update.message.reply_text(f"Trailer payment will be {trailer_payment_final}")
    update.message.reply_text("Now, please provide the fuel statement PDF (upload it as a document) so we can continue.")
    # The next step will be triggered once the user uploads the PDF which is handled by download_statement.




def count_salary(update: Update, context: CallbackContext):
    if not user_authorized(update, context):
        return

    if driver in ['Walter', 'Nestor']:
        start_val, end_val = sheets.get_start_end_dateForCompanyDriversSalary(start_row=cell, driver=driver)
        start_val = start_val.replace('/', '-')
        end_val = end_val.replace('/', '-')

        sheets.compilate_salary_company_driver(driver, cell, start_date=start_val, end_date=end_val)
        print('Company driver page counted.')

        merger = PdfMerger()  # Using PdfMerger here as well
        merger.append("./files_cash/1st_page.pdf")
        merged_file_name = f"Statement_{driver}_{end_val}.pdf"
        merger.write(merged_file_name)
        merger.close()

        pdf_files = os.listdir('./files_cash')
        for pdf_file in pdf_files:
            os.remove(f"./files_cash/{pdf_file}")

        sheets.upload_file(file_name=merged_file_name, driver_name=driver, cell=cell)
        sheets.update_cell(driver=driver, cell=cell, letter='Y', value='no insurance')

        Load = sheets.open_invoice_load(driver, cell)
        statement_url = Load[0][23]
        keyboard = [[InlineKeyboardButton("👉 Statement🔍👈", url=statement_url)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        update.message.reply_text("Please check the Statement\n\n/start", reply_markup=reply_markup)

        with open(merged_file_name, 'rb') as document:
            update.message.reply_document(document=document)

        os.remove(merged_file_name)

    else:
        sheets.compilate_salary_page(
            driver, cell, start_date, end_date, totals, discount,
            insurance_payment_final, insurance_print_global,
            trailer_payment_final, trailer_print_global
        )
        print('Owner-operator 1st page counted.')

        merged_file_name = f"Statement_{driver}_{end_date}.pdf"
        merger = PdfMerger()  # Updated here: replaced PdfFileMerger with PdfMerger
        merger.append("./files_cash/1st_page.pdf")
        merger.append(f"./files_cash/{driver}_Statement_{cell}.pdf")
        merger.write(merged_file_name)
        merger.close()

        pdf_files = os.listdir('./files_cash')
        for pdf_file in pdf_files:
            os.remove(f"./files_cash/{pdf_file}")

        sheets.upload_file(file_name=merged_file_name, driver_name=driver, cell=cell)
        sheets.update_cell(driver=driver, cell=cell, letter='Y', value=insurance_print_global)

        Load = sheets.open_invoice_load(driver, cell)
        statement_url = Load[0][23]
        keyboard = [[InlineKeyboardButton("👉 Statement🔍👈", url=statement_url)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        update.message.reply_text("Please check the Statement\n\n/start", reply_markup=reply_markup)

        with open(merged_file_name, 'rb') as document:
            update.message.reply_document(document=document)

        os.remove(merged_file_name)

# Telegram handlers
updater.dispatcher.add_handler(CommandHandler('start', start))
updater.dispatcher.add_handler(CommandHandler('Yura', yura))
updater.dispatcher.add_handler(CommandHandler('Walter', walter))
updater.dispatcher.add_handler(CommandHandler('Nestor', nestor))
# updater.dispatcher.add_handler(CommandHandler('Javier', Javier))
updater.dispatcher.add_handler(CommandHandler('Count_salary', count_salary))

# This regex catches dates in mm/dd/yyyy or similar formats for insurance date input.
updater.dispatcher.add_handler(MessageHandler(
    Filters.regex(r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})'), insurance_date
))

# Fallback handler for cell number input
updater.dispatcher.add_handler(MessageHandler(Filters.text, cell))

# Handle PDF document uploads – this will now trigger download_statement to process the uploaded file
updater.dispatcher.add_handler(MessageHandler(Filters.document.file_extension("pdf"), download_statement))

updater.dispatcher.add_handler(MessageHandler(Filters.command, unknown))

updater.start_polling()
