from fpdf import FPDF
import os
from datetime import datetime
from ..config import settings
from .core_sheets import sh, SHEET_ID

def open_invoice_load(driver, cell):
    range_name = f'{driver}!A{cell}:AA{cell}'
    return sh.spreadsheets().values().get(spreadsheetId=SHEET_ID, range=range_name).execute().get('values')

def compilate_invoice_page(loadnum, driver, cell, broker, pu, pudate, deliv, deldate, innum, gross, lumper_kolobok, lumper_broker):
    # This is the full function body from your original file
    pdf = FPDF('P', 'mm', 'A4'); pdf.add_page()
    header_text = ('Kolobok Inc.\n9063 Caloosa Rd\nFort Myers, FL 33967\n239-293-1919 or 312-535-3912\nchrisribas89@gmail.com')
    pdf.set_font('times', '', 12); pdf.multi_cell(0, 5, header_text, align='L')
    pdf.set_font('helvetica', 'B', 16); pdf.set_text_color(25, 126, 134); pdf.cell(0, 10, 'INVOICE', ln=True, align='L')
    pdf.set_font('helvetica', 'B', 12); pdf.set_text_color(0, 0, 0); pdf.cell(50, 5, 'BILL TO', ln=0); pdf.cell(0, 5, f'INVOICE # {innum}', ln=1, align='R')
    try:
        with open(f'./customers/{broker}.txt') as file: brokers_adress = file.read()
        pdf.set_font('times', '', 12); pdf.multi_cell(0, 5, brokers_adress, align='L')
    except FileNotFoundError: pdf.set_font('times', 'I', 12); pdf.multi_cell(0, 5, f"{broker}\n(Address file not found)", align='L')
    pdf.set_font('helvetica', 'B', 12); pdf.cell(160, 5, 'DATE', ln=0, align='R'); pdf.set_font('helvetica', '', 12); pdf.cell(30, 5, datetime.now().strftime("%m-%d-%Y"), ln=1, align='R')
    pdf.cell(32, 30, 'TRK#/DRIVER', ln=0); pdf.cell(63, 30, driver, ln=0); pdf.cell(35, 30, 'LOAD/ORDER #', ln=0); pdf.cell(60, 30, loadnum, ln=1)
    pdf.cell(0, 8, 'LOAD DESCRIPTION', ln=1, border=1, align='C')
    pdf.set_font('helvetica', '', 10); pdf.set_text_color(25, 126, 134); pdf.cell(10, 8, 'SO', border=1); pdf.cell(160, 8, 'ADDRESS', border=1); pdf.cell(20, 8, 'DATE', ln=1, border=1)
    pdf.set_text_color(0, 0, 0); pdf.cell(10, 10, 'PU', border=1); pdf.cell(160, 10, pu, border=1); pdf.cell(20, 10, pudate, ln=1, border=1); pdf.cell(10, 10, 'DEL', border=1); pdf.cell(160, 10, deliv, border=1); pdf.cell(20, 10, deldate, ln=1, border=1)
    final_gross = float(gross.replace(',', '')) if gross else 0.0; lumper_text = '<none>'
    if lumper_kolobok: lumper_text = f'(Kolobok Inc paid) ${lumper_kolobok}'; final_gross += float(lumper_kolobok.replace(',', ''))
    elif lumper_broker: lumper_text = f'(Broker paid) ${lumper_broker}'
    pdf.set_text_color(25, 126, 134); pdf.cell(95, 8, 'LUMPER', border=1); pdf.set_text_color(0, 0, 0); pdf.cell(95, 8, lumper_text, ln=1, border=1, align='R')
    pdf.set_text_color(25, 126, 134); pdf.cell(95, 8, 'BALANCE DUE', border=1); pdf.set_font('helvetica', 'B', 12); pdf.set_text_color(0, 0, 0); pdf.cell(95, 8, f'${final_gross:,.2f}', ln=1, border=1, align='R')
    pdf.set_text_color(25, 126, 134); pdf.set_font('helvetica', '', 10); pdf.cell(0, 15, 'PAYMENT INFO:', ln=1, border=1, align='C')
    pdf.cell(95, 8, 'Type of account:', border=1); pdf.set_text_color(0,0,0); pdf.set_font('helvetica', 'B', 10); pdf.cell(95, 8, 'Checking', ln=1, border=1)
    pdf.set_text_color(25, 126, 134); pdf.set_font('helvetica', '', 10); pdf.cell(95, 8, 'Name as it appears on Bank Account:', border=1); pdf.set_text_color(0,0,0); pdf.set_font('helvetica', 'B', 10); pdf.cell(95, 8, settings.company_payee_name or 'N/A', ln=1, border=1)
    pdf.set_text_color(25, 126, 134); pdf.set_font('helvetica', '', 10); pdf.cell(95, 8, 'Bank Name:', border=1); pdf.set_text_color(0,0,0); pdf.set_font('helvetica', 'B', 10); pdf.cell(95, 8, settings.company_bank_name or 'N/A', ln=1, border=1)
    pdf.set_text_color(25, 126, 134); pdf.set_font('helvetica', '', 10); pdf.cell(95, 8, 'Financial institution phone number:', border=1); pdf.set_text_color(0,0,0); pdf.set_font('helvetica', 'B', 10); pdf.cell(95, 8, settings.company_bank_phone or 'N/A', ln=1, border=1)
    pdf.set_text_color(25, 126, 134); pdf.set_font('helvetica', '', 10); pdf.cell(95, 8, 'Banking Routing / Transfer Number (9 digits):', border=1); pdf.set_text_color(0,0,0); pdf.set_font('helvetica', 'B', 10); pdf.cell(95, 8, settings.company_routing_number or 'N/A', ln=1, border=1)
    pdf.set_text_color(25, 126, 134); pdf.set_font('helvetica', '', 10); pdf.cell(95, 8, 'Bank Account Number:', border=1); pdf.set_text_color(0,0,0); pdf.set_font('helvetica', 'B', 10); pdf.cell(95, 8, settings.company_account_number or 'N/A', ln=1, border=1)
    pdf.set_font('helvetica', '', 10); pdf.cell(0, 15, 'PLEASE USE THIS MAIL ADDRESS FOR CHECKS:', ln=1, align='C')
    pdf.set_font('helvetica', 'B', 10); pdf.set_text_color(0, 0, 0); pdf.cell(0, 8, '9063 Caloosa Rd', ln=1, align='C'); pdf.cell(0, 8, 'Fort Myers, FL 33967', ln=1, align='C')
    pdf.set_font('helvetica', '', 8); pdf.cell(0, 10, 'Thank you!', ln=1, align='C')
    os.makedirs("./files_cash", exist_ok=True); pdf.output(f'./files_cash/Invoice_{loadnum}_MC_1294648.pdf')
