import os
import shutil
from datetime import datetime, timedelta
import io
import time
import ssl
from fpdf import FPDF
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
from googleapiclient.errors import HttpError
from .auth import spreadsheet_service as sh, drive_service as dr
from ..config import settings

SHEET_ID = settings.spreadsheet_id

# (All helper functions are correct and included)
def get_current_cell(driver_name: str, column: str = "A") -> int:
    range_name = f"{driver_name}!{column}:{column}"
    result = sh.spreadsheets().values().get(spreadsheetId=SHEET_ID, range=range_name).execute()
    return len(result.get("values", []))
def get_id_from_link(link):
    if not link: return None
    start = "/d/"
    try:
        if "/view" in link: return link[link.index(start)+3:link.index("/view")]
        return link[link.index(start)+3:]
    except (ValueError, TypeError): return None
def open_invoice_load(driver, cell):
    range_name = f'{driver}!A{cell}:AA{cell}'
    return sh.spreadsheets().values().get(spreadsheetId=SHEET_ID, range=range_name).execute().get('values')
def update_cell(driver, cell, letter, value):
    rangeName = f"{driver}!{letter}{cell}"; body = {'values': [[value]]}
    sh.spreadsheets().values().update(spreadsheetId=SHEET_ID, range=rangeName, valueInputOption='USER_ENTERED', body=body).execute()
def download_file(file_id, name):
    if not file_id: raise ValueError("File ID missing")
    attempts, max_attempts, wait_time = 0, 4, 5
    while attempts < max_attempts:
        try:
            request = dr.files().get_media(fileId=file_id)
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done: status, done = downloader.next_chunk()
            fh.seek(0)
            os.makedirs("./files_cash", exist_ok=True)
            with open(f'./files_cash/{name}', 'wb') as f: shutil.copyfileobj(fh, f)
            return
        except HttpError as error:
            if error.resp.status == 404 and attempts < max_attempts - 1:
                attempts += 1; time.sleep(wait_time)
            else: raise error
def _perform_upload(local_path: str):
    attempts, max_attempts, wait_time = 0, 3, 5
    while attempts < max_attempts:
        try:
            file_metadata = {'name': os.path.basename(local_path), 'parents': [settings.drive_folder_id]}
            media = MediaFileUpload(local_path, mimetype='application/pdf')
            file = dr.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
            dr.permissions().create(fileId=file.get('id'), body={'type': 'anyone', 'role': 'reader'}).execute()
            return file
        except ssl.SSLEOFError as e:
            attempts += 1
            if attempts >= max_attempts: raise e
            time.sleep(wait_time)
        except Exception as e: raise e
def upload_pod(local_path: str, driver: str, cell: int):
    file = _perform_upload(local_path)
    update_cell(driver, cell, 'N', file.get('webViewLink'))
def upload_file(file_name, driver_name, cell):
    file = _perform_upload(file_name)
    column = 'R' if 'Invoice' in file_name else 'X'
    update_cell(driver_name, cell, column, file.get('webViewLink'))
def open_prev_insurance(driver, cell):
    range_name = f'{driver}!Y1:Y{cell}'
    result = sh.spreadsheets().values().get(spreadsheetId=SHEET_ID, range=range_name).execute()
    if result.get('values'):
        for row in reversed(result.get('values')):
            if row and row[0]: return row
    raise RuntimeError(f"Could not find previous insurance date for {driver}")
def compilate_invoice_page(loadnum, driver, cell, broker, pu, pudate, deliv, deldate, innum, gross, lumper_kolobok, lumper_broker):
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
    final_gross = float(gross) if gross else 0.0; lumper_text = '<none>'
    if lumper_kolobok: lumper_text = f'(Kolobok Inc paid) ${lumper_kolobok}'; final_gross += float(lumper_kolobok)
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
def compilate_salary_company_driver(driver, start_row, start_date_ignored, end_date_ignored):
    pdf = FPDF('P', 'mm', 'A4'); pdf.add_page()
    read_range = f"{driver}!A{start_row}:AA"
    all_rows = sh.spreadsheets().values().get(spreadsheetId=SHEET_ID, range=read_range).execute().get('values', [])
    loads_data, end_date = [], ""
    start_date = all_rows[0][0] if all_rows and all_rows[0] else ""
    for row in all_rows:
        if not row or not row[0]: break
        loads_data.append(row)
        if len(row) > 2 and row[2]: end_date = row[2]
    if not end_date: end_date = start_date
    pdf.set_font('helvetica', 'B', 18)
    pdf.cell(190, 10, 'Kolobok INC', ln=1)
    pdf.cell(190, 10, f'Pay to: {settings.pay_to_map.get(driver, "Driver")}', ln=1)
    pdf.cell(190, 10, f'Statement {start_date} - {end_date}', ln=1)
    pdf.set_font('helvetica', 'B', 14); pdf.cell(15, 15, 'Loads Complete:', ln=1)
    pdf.set_font('helvetica', 'B', 8)
    pdf.cell(15, 5, 'PU date', ln=0, border=1); pdf.cell(15, 5, 'Del date', ln=0, border=1); pdf.cell(30, 5, 'From:', ln=0, border=1); pdf.cell(30, 5, 'To:', ln=0, border=1); pdf.cell(30, 5, 'Broker', ln=0, border=1); pdf.cell(15, 5, 'Gross', ln=0, border=1); pdf.cell(10, 5, 'Miles', ln=0, border=1); pdf.cell(17, 5, 'Kolobok %', ln=0, border=1); pdf.cell(15, 5, 'Gross - %', ln=1, border=1)
    total_gross = total_miles = total_commission = total_loads = 0
    extra_charges = []
    for values in loads_data:
        gross = float(values[9]) if len(values) > 9 and values[9] else 0.0
        commision_rate = float(values[20]) / 100.0 if len(values) > 20 and values[20] else 0.0
        miles = float(values[10]) if len(values) > 10 and values[10] else 0.0
        w_gets = gross - (gross * commision_rate)
        pdf.set_font('helvetica', '', 7)
        pdf.cell(15, 5, (values[0] or '')[:11], ln=0, border=1); pdf.cell(15, 5, (values[2] or '')[:11], ln=0, border=1); pdf.cell(30, 5, (values[4] or '')[:19], ln=0, border=1); pdf.cell(30, 5, (values[5] or '')[:19], ln=0, border=1); pdf.cell(30, 5, (values[6] or '')[:19], ln=0, border=1); pdf.cell(15, 5, f"{gross:.2f}"[:9], ln=0, border=1); pdf.cell(10, 5, f"{miles:.0f}"[:9], ln=0, border=1); pdf.cell(17, 5, f"{gross * commision_rate:.2f}"[:9], ln=0, border=1); pdf.cell(15, 5, f"{w_gets:.2f}"[:9], ln=1, border=1)
        total_gross += gross; total_miles += miles; total_commission += (gross * commision_rate); total_loads += w_gets
        try:
            if len(values) > 25 and values[25]:
                extra_charges.append({'label': values[26] if len(values) > 26 and values[26] else "Deduction", 'amount': float(values[25])})
        except (ValueError, IndexError): pass
    pdf.set_font('helvetica', 'B', 8)
    pdf.cell(15, 5, '', border=1); pdf.cell(15, 5, '', border=1); pdf.cell(30, 5, '', border=1); pdf.cell(30, 5, '', border=1); pdf.cell(30, 5, 'Totals:', align='R', border=1)
    pdf.cell(15, 5, f"{total_gross:.2f}"[:9], border=1); pdf.cell(10, 5, f"{total_miles:.0f}"[:9], border=1); pdf.cell(17, 5, f"{total_commission:.2f}"[:9], border=1); pdf.cell(15, 5, f"{total_loads:.2f}"[:9], ln=1, border=1)
    pdf.ln(5)
    pdf.set_font('helvetica', 'B', 14); pdf.set_fill_color(232, 253, 226)
    pdf.cell(177, 15, f'Total for loads: ${total_loads:,.2f}', ln=1, fill=True)
    pdf.ln(5)
    final_pay_str = f'Final pay: ${total_loads:.2f}'; settlement = total_loads
    for charge in reversed(extra_charges):
        amount = charge['amount']; final_pay_str += f" - ${amount:.2f}" if amount > 0 else f" + ${abs(amount):,.2f}"
        pdf.set_font('helvetica', '', 12); pdf.cell(177, 10, f"{charge['label']}: ${abs(amount):.2f}", ln=1)
        line_width = min((abs(amount) / total_loads) * 177 if total_loads > 0 else 0, 177)
        pdf.set_fill_color(252, 66, 37) if amount >= 0 else pdf.set_fill_color(85, 252, 37)
        pdf.cell(line_width, 0.5, '', ln=1, fill=True)
    settlement -= sum(c['amount'] for c in extra_charges)
    pdf.ln(5); pdf.set_font('helvetica', 'B', 14); pdf.cell(177, 15, final_pay_str, ln=1)
    pdf.set_fill_color(74, 245, 44); pdf.cell(177, 15, f'Settlement Total: ${settlement:,.2f}', ln=1, align='C', fill=True)
    os.makedirs("./files_cash", exist_ok=True)
    pdf.output('./files_cash/1st_page.pdf')

def compilate_salary_page(driver, cell, fuel_start_date, fuel_end_date, totals, discount, insurance, insurance_d, trailer, trailer_d):
    pdf = FPDF('P', 'mm', 'A4'); pdf.add_page()
    read_range = f"{driver}!A{cell}:AA"
    all_rows = sh.spreadsheets().values().get(spreadsheetId=SHEET_ID, range=read_range).execute().get('values', [])
    loads_data, extra_charges = [], []
    for values in all_rows:
        if not values or not values[0]: break
        loads_data.append(values)
        try:
            if len(values) > 25 and values[25]:
                extra_charges.append({'label': values[26] if len(values) > 26 and values[26] else "Deduction", 'amount': float(values[25])})
        except (ValueError, IndexError): pass
    
    start_date = loads_data[0][0] if loads_data and loads_data[0] else fuel_start_date
    end_date = loads_data[-1][2] if loads_data and len(loads_data[-1]) > 2 and loads_data[-1][2] else fuel_end_date
    
    pdf.set_font('helvetica', 'B', 18)
    pdf.cell(190, 10, 'Kolobok INC', ln=1)
    pdf.cell(190, 10, f'Pay to: {settings.pay_to_map.get(driver, "Driver")}', ln=1)
    pdf.cell(190, 10, f'Statement {start_date} - {end_date}', ln=1)
    pdf.set_font('helvetica', 'B', 14); pdf.cell(15, 15, 'Loads Complete:', ln=1)
    pdf.set_font('helvetica', 'B', 8)
    pdf.cell(15, 5, 'PU date', ln=0, border=1); pdf.cell(15, 5, 'Del date', ln=0, border=1); pdf.cell(30, 5, 'From:', ln=0, border=1); pdf.cell(30, 5, 'To:', ln=0, border=1); pdf.cell(30, 5, 'Broker', ln=0, border=1); pdf.cell(15, 5, 'Gross', ln=0, border=1); pdf.cell(10, 5, 'Miles', ln=0, border=1); pdf.cell(17, 5, 'Kolobok %', ln=0, border=1); pdf.cell(15, 5, 'Gross - %', ln=1, border=1)
    
    total_gross = total_miles = total_commission = total_loads = 0
    for values in loads_data:
        gross = float(values[9]) if len(values) > 9 and values[9] else 0.0
        commision_rate = float(values[20]) / 100.0 if len(values) > 20 and values[20] else 0.0
        miles = float(values[10]) if len(values) > 10 and values[10] else 0.0
        w_gets = gross - (gross * commision_rate)
        pdf.set_font('helvetica', '', 7)
        pdf.cell(15, 5, (values[0] or '')[:11], ln=0, border=1); pdf.cell(15, 5, (values[2] or '')[:11], ln=0, border=1); pdf.cell(30, 5, (values[4] or '')[:19], ln=0, border=1); pdf.cell(30, 5, (values[5] or '')[:19], ln=0, border=1); pdf.cell(30, 5, (values[6] or '')[:19], ln=0, border=1); pdf.cell(15, 5, f"{gross:.2f}"[:9], ln=0, border=1); pdf.cell(10, 5, f"{miles:.0f}"[:9], ln=0, border=1); pdf.cell(17, 5, f"{gross * commision_rate:.2f}"[:9], ln=0, border=1); pdf.cell(15, 5, f"{w_gets:.2f}"[:9], ln=1, border=1)
        total_gross += gross; total_miles += miles; total_commission += (gross * commision_rate); total_loads += w_gets

    pdf.set_font('helvetica', 'B', 8)
    pdf.cell(15, 5, '', border=1); pdf.cell(15, 5, '', border=1); pdf.cell(30, 5, '', border=1); pdf.cell(30, 5, '', border=1); pdf.cell(30, 5, 'Totals:', align='R', border=1)
    pdf.cell(15, 5, f"{total_gross:.2f}"[:9], border=1); pdf.cell(10, 5, f"{total_miles:.0f}"[:9], border=1); pdf.cell(17, 5, f"{total_commission:.2f}"[:9], border=1); pdf.cell(15, 5, f"{total_loads:.2f}"[:9], ln=1, border=1)
    pdf.ln(2)

    pdf.set_font('helvetica', 'B', 14); pdf.set_fill_color(232, 253, 226)
    pdf.cell(177, 10, f'Total for loads: ${total_loads:,.2f}', ln=1, fill=True)

    def draw_deduction(label, value, total_base, color_override=None):
        pdf.set_font('helvetica', '', 12); pdf.cell(177, 8, f'{label}: ${abs(value):,.2f}', ln=1)
        line_width = min((abs(value) / total_base) * 177 if total_base > 0 else 0, 177)
        if color_override == 'yellow':
            pdf.set_fill_color(252, 239, 37)
        else:
            pdf.set_fill_color(252, 66, 37) if value >= 0 else pdf.set_fill_color(85, 252, 37)
        pdf.cell(line_width, 0.5, '', ln=1, fill=True)
    
    total_fuel = totals + discount
    draw_deduction('Fuel before discount', total_fuel, total_loads, color_override='yellow')
    draw_deduction('Discount', -discount, total_loads)
    draw_deduction('Fuel after discount', totals, total_loads)
    draw_deduction(f'Insurance ({insurance_d})', insurance, total_loads)
    if trailer > 0: draw_deduction(f'Trailer ({trailer_d})', trailer, total_loads)
    
    settlement = total_loads - totals - insurance - trailer
    final_pay_str = f'Final pay: ${total_loads:,.2f} - ${totals:,.2f} - ${insurance:,.2f}'
    if trailer > 0: final_pay_str += f' - ${trailer:,.2f}'
    
    for charge in extra_charges:
        amount = charge['amount']
        final_pay_str += f" - ${amount:.2f}" if amount > 0 else f" + ${abs(amount):,.2f}"
        draw_deduction(charge['label'], amount, total_loads)
        settlement -= amount

    pdf.ln(5); pdf.set_font('helvetica', 'B', 14); pdf.cell(177, 10, final_pay_str, ln=1)
    pdf.set_fill_color(74, 245, 44); pdf.cell(177, 15, f'Settlement Total: ${settlement:,.2f}', ln=1, align='C', fill=True)
    pdf.set_font('helvetica', '', 8); pdf.cell(177, 10, 'Please see a fuel Transaction Report below...', ln=1, align='C')
    os.makedirs("./files_cash", exist_ok=True)
    pdf.output('./files_cash/1st_page.pdf')
