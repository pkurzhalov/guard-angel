from fpdf import FPDF
import os
from ..config import settings
from .core_sheets import sh, SHEET_ID

def open_prev_insurance(driver, cell):
    range_name = f'{driver}!Y1:Y{cell}'
    result = sh.spreadsheets().values().get(spreadsheetId=SHEET_ID, range=range_name).execute()
    if result.get('values'):
        for row in reversed(result.get('values')):
            if row and row[0]: return row
    raise RuntimeError(f"Could not find previous insurance date for {driver}")

def compilate_salary_company_driver(driver, start_row, start_date_ignored, end_date_ignored):
    # This is the full function body from your original file
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
    pdf.cell(190, 10, f'Pay to: {settings.get_pay_to_name(driver)}', ln=1)
    pdf.cell(190, 10, f'Statement {start_date} - {end_date}', ln=1)
    pdf.set_font('helvetica', 'B', 14); pdf.cell(15, 15, 'Loads Complete:', ln=1)
    pdf.set_font('helvetica', 'B', 8)
    pdf.cell(15, 5, 'PU date', ln=0, border=1); pdf.cell(15, 5, 'Del date', ln=0, border=1); pdf.cell(30, 5, 'From:', ln=0, border=1); pdf.cell(30, 5, 'To:', ln=0, border=1); pdf.cell(30, 5, 'Broker', ln=0, border=1); pdf.cell(15, 5, 'Gross', ln=0, border=1); pdf.cell(10, 5, 'Miles', ln=0, border=1); pdf.cell(17, 5, 'Kolobok %', ln=0, border=1); pdf.cell(15, 5, 'Gross - %', ln=1, border=1)
    total_gross = total_miles = total_commission = total_loads = 0
    extra_charges = []
    for values in loads_data:
        gross = float(values[9].replace(',', '')) if len(values) > 9 and values[9] else 0.0
        commision_rate = float(values[20]) / 100.0 if len(values) > 20 and values[20] else 0.0
        miles = float(values[10].replace(',', '')) if len(values) > 10 and values[10] else 0.0
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
    # This is the full function body from your original file
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
    pdf.cell(190, 10, f'Pay to: {settings.get_pay_to_name(driver)}', ln=1)
    pdf.cell(190, 10, f'Statement {start_date} - {end_date}', ln=1)
    pdf.set_font('helvetica', 'B', 14); pdf.cell(15, 15, 'Loads Complete:', ln=1)
    pdf.set_font('helvetica', 'B', 8)
    pdf.cell(15, 5, 'PU date', ln=0, border=1); pdf.cell(15, 5, 'Del date', ln=0, border=1); pdf.cell(30, 5, 'From:', ln=0, border=1); pdf.cell(30, 5, 'To:', ln=0, border=1); pdf.cell(30, 5, 'Broker', ln=0, border=1); pdf.cell(15, 5, 'Gross', ln=0, border=1); pdf.cell(10, 5, 'Miles', ln=0, border=1); pdf.cell(17, 5, 'Kolobok %', ln=0, border=1); pdf.cell(15, 5, 'Gross - %', ln=1, border=1)
    total_gross = total_miles = total_commission = total_loads = 0
    for values in loads_data:
        gross = float(values[9].replace(',', '')) if len(values) > 9 and values[9] else 0.0
        commision_rate = float(values[20]) / 100.0 if len(values) > 20 and values[20] else 0.0
        miles = float(values[10].replace(',', '')) if len(values) > 10 and values[10] else 0.0
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
        if color_override == 'yellow': pdf.set_fill_color(252, 239, 37)
        else: pdf.set_fill_color(252, 66, 37) if value >= 0 else pdf.set_fill_color(85, 252, 37)
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
