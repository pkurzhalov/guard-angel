from __future__ import print_function # built-in module used to inherit new features in the new Python versions
#!/usr/bin/python3
from .cache import load_cache, save_cache
#sheets.py
import os

from .auth import spreadsheet_service as sh
from .auth import drive_service as dr
import io
from googleapiclient.http import MediaIoBaseDownload
from ..config import settings
SHEET_ID = settings.spreadsheet_id
id = SHEET_ID  # legacy alias for old code paths
SHEET_ID = settings.spreadsheet_id
import shutil
import datetime
from fpdf import FPDF
SHEET_ID = settings.spreadsheet_id
MY_SHEET_ID = SHEET_ID


_last_rows_cache = load_cache()

def _last_row_from_sheet(driver_name: str, column: str = "G") -> int:
    """
    Scan a single column (default 'G') from top to bottom and return the
    last FILLED row index (1-based). Assumes headers in row 1 are allowed.
    """
    rng = f"{driver_name}!{column}:{column}"
    result = sh.spreadsheets().values().get(spreadsheetId=SHEET_ID, range=rng).execute()
    values = result.get("values", [])
    # Google Sheets API returns only up to the last non-empty row for this column,
    # so len(values) is the last filled row number (1-based).
    return len(values)

def refresh_last_row(driver_name: str, column: str = "G") -> int:
    n = _last_row_from_sheet(driver_name, column)
    key = f"{driver_name}:{column.upper()}"
    _last_rows_cache[key] = n
    save_cache(_last_rows_cache)
    return n

def get_current_cell(driver_name: str, column: str = "G", refresh: bool = False) -> int:
    """
    Return the last filled row (1-based) in the given column for the given sheet tab.
    Uses a small on-disk cache and refreshes on demand.
    """
    key = f"{driver_name}:{column.upper()}"
    if not refresh and key in _last_rows_cache:
        try:
            return int(_last_rows_cache[key])
        except Exception:
            pass
    return refresh_last_row(driver_name, column)

def get_data_for_peter_salary(selected_drivers, start_date_str):
    try:
        start_date = datetime.datetime.strptime(start_date_str, "%m/%d/%Y")
    except ValueError:
        return []

    result_list = []

    for driver in selected_drivers:
        last_row = get_current_cell(driver)

        ae_range = f"{driver}!AE1:AE{last_row}"
        ad_range = f"{driver}!AD1:AD{last_row}"
        o_range  = f"{driver}!O1:O{last_row}"
        g_range  = f"{driver}!G1:G{last_row}"  # broker name
        c_range  = f"{driver}!C1:C{last_row}"  # delivery date

        result = sh.spreadsheets().values().batchGet(
            spreadsheetId=SHEET_ID,
            ranges=[ae_range, ad_range, o_range, g_range, c_range]
        ).execute()

        ae_values = result['valueRanges'][0].get('values', [])
        ad_values = result['valueRanges'][1].get('values', [])
        o_values  = result['valueRanges'][2].get('values', [])
        g_values  = result['valueRanges'][3].get('values', [])
        c_values  = result['valueRanges'][4].get('values', [])

        for i, row in enumerate(ae_values):
            date_str = row[0].strip() if row else ""
            if not date_str:
                continue

            try:
                date_obj = datetime.datetime.strptime(date_str, "%m/%d/%Y")
            except ValueError:
                continue

            if date_obj >= start_date:
                amount = ad_values[i][0] if i < len(ad_values) and ad_values[i] else "?"
                lumper = o_values[i][0] if i < len(o_values) and o_values[i] else None
                broker = g_values[i][0] if i < len(g_values) and g_values[i] else ""
                delivery_date = c_values[i][0] if i < len(c_values) and c_values[i] else ""
                result_list.append((driver, date_str, amount, lumper, broker, delivery_date))

    return result_list

def get_last_load_lookload(driver_name):
    last_row = get_current_cell(driver_name)
    ranges = [driver_name + '!' + f'C{last_row}:C{last_row}', driver_name + '!' + f'F{last_row}:F{last_row}', driver_name + '!' + f'V{last_row}:V{last_row}']
    result = sh.spreadsheets().values().batchGet(spreadsheetId=SHEET_ID, ranges=ranges).execute()
    values = result.get('valueRanges', [])

    if not values:
        return None
    else:
        available_since = datetime.datetime.strptime(values[0]['values'][0][0], '%m/%d/%Y')
        original_location = values[1]['values'][0][0] if values[1]['values'][0] else None
        available_when = values[2]['values'][0][0]
        return {'Available-Since': available_since.strftime('%m/%d/%Y'), 'Original-Location': original_location, 'Available-When': available_when}



def get_last_load(driver_name, row=None):
    last_row = row or get_current_cell(driver_name)
    row_to_read = last_row if row else last_row
    prev_row = row_to_read if row else last_row
    prev_row -= 1  # go one row up

    ranges = [
        f"{driver_name}!C{prev_row}:C{prev_row}",
        f"{driver_name}!F{prev_row}:F{prev_row}",
        f"{driver_name}!V{prev_row}:V{prev_row}"
    ]
    result = sh.spreadsheets().values().batchGet(
        spreadsheetId=SHEET_ID,
        ranges=ranges
    ).execute()
    values = result.get('valueRanges', [])

    print(f"🧾 DEBUG get_last_load row {prev_row} for {driver_name}:")
    for i, r in enumerate(values):
        print(f"  Range {i}: {r.get('range')}")
        print(f"    Values: {r.get('values')}")

    if not values or any('values' not in r or not r['values'] for r in values):
        raise RuntimeError(f"❌ Missing expected values in row {prev_row} of {driver_name}")

    available_since = datetime.datetime.strptime(values[0]['values'][0][0], '%m/%d/%Y')
    original_location = values[1]['values'][0][0]
    available_when = values[2]['values'][0][0]
    return {
        'Available-Since': available_since.strftime('%m/%d/%Y'),
        'Original-Location': original_location,
        'Available-When': available_when
    }





def get_start_end_dateForCompanyDriversSalary(start_row, driver):
    """
    Determine the salary period for company drivers starting at `start_row`:

    - start_date := column A at `start_row`
    - end_date   := the LAST non-empty column C in the contiguous block of rows
                    starting at `start_row` until column A becomes empty.
    """
    # read a generous slab below start_row so we don't overfetch repeatedly
    slab = 300  # plenty for a pay period
    range_block = f"{driver}!A{start_row}:C{start_row+slab}"
    result = sh.spreadsheets().values().get(spreadsheetId=SHEET_ID, range=range_block).execute()
    rows = result.get('values', [])

    if not rows or not rows[0] or not rows[0][0]:
        raise RuntimeError(f"No start PU date at row {start_row} for {driver}")

    start_date = rows[0][0]

    last_c = None
    # Walk until first empty A (end of contiguous loads)
    for r in rows:
        pu = r[0] if len(r) > 0 else ''
        if not pu:
            break
        cval = r[2] if len(r) > 2 else ''
        if cval:
            last_c = cval

    end_date = last_c or start_date
    return start_date, end_date

def get_Start_Finish(quarter, driver):
    now = datetime.datetime.now()
    year = now.strftime("%Y")
    if quarter == 1:
        start_date = f'12/31/{int(year)-1}'
        end_date = f'04/1/{year}'
    elif quarter == 2:
        start_date = f'03/31/{year}'
        end_date = f'07/1/{year}'
    elif quarter == 3:
        start_date = f'06/30/{year}'
        end_date = f'10/1/{year}'
    elif quarter == 4:
        start_date = f'09/30/{int(year) - 1}'  # Adjusted to get the previous year's end date for Q4 start date.
        end_date = f'01/1/{year}'
    elif quarter == 5:

                start_date = f'07/01/2022'  # counting for florida IRP 85900 form 2025 year
                end_date = f'06/30/2023'


        # Logic to get the last day of the month prior to the previous month
#       first_day_current_month = now.replace(day=1)
#       last_day_prev_month = first_day_current_month - datetime.timedelta(days=1)
#       start_date_of_prev_month = last_day_prev_month.replace(day=1)
#       start_date = (start_date_of_prev_month - datetime.timedelta(days=1)).strftime('%m/%d/%Y')
#       end_date = first_day_current_month.strftime(
#           '%m/%d/%Y')  # Adjusted to set it as the first day of the current month
    else:
        print('❌Error')
        return 0

    start_date = datetime.datetime.strptime(start_date, "%m/%d/%Y")
    end_date = datetime.datetime.strptime(end_date, "%m/%d/%Y")
    current_cell = get_current_cell(driver)
    print(f'Start Date: {start_date}, End Date: {end_date}')
    range_dates = driver + '!' + f'C2:C{current_cell}'
    result_dates = sh.spreadsheets().values().get(spreadsheetId=SHEET_ID, range=range_dates).execute()
    dates = result_dates.get('values')

    range_PUs = driver + '!' + f'E2:E{current_cell}'
    result_PUs = sh.spreadsheets().values().get(spreadsheetId=SHEET_ID, range=range_PUs).execute()
    PUs = result_PUs.get('values')

    range_deliveries = driver + '!' + f'F2:F{current_cell}'
    result_deliveries = sh.spreadsheets().values().get(spreadsheetId=SHEET_ID, range=range_deliveries).execute()
    deliveries = result_deliveries.get('values')
    Start_Finish = []
    for (item, date, pu, delivery) in zip(range(len(dates)), dates, PUs, deliveries):
        try:
            date = date[0]
            pu = pu[0]
            delivery = delivery[0]
            date = datetime.datetime.strptime(date, "%m/%d/%Y")
            if start_date < date < end_date:
                if (';' not in pu) and (';' not in delivery):
                    print ('1 pick / 1 drop')
                    print (date, pu, delivery)
                    Start_Finish.append({pu:delivery})

                    try:
                        next_pu_cell = PUs[item+1][0]
                        if ';' in next_pu_cell:
                            next_pu = next_pu_cell.split(';')[0]
                        else:
                            next_pu = next_pu_cell
                        Start_Finish.append({delivery:next_pu})
                    except IndexError:
                        continue
                elif (';' in pu) and (';' not in delivery):
                    print ('several PUs')
                    print(date, pu, delivery)
                    pu_list = pu.split(';')
                    for i in range(len(pu_list)):
                        try:
                            Start_Finish.append({pu_list[i]:pu_list[i+1]})
                        except IndexError:
                            Start_Finish.append({pu_list[-1] : delivery})
                            break

                    try:
                        next_pu_cell = PUs[item + 1][0]
                        if ';' in next_pu_cell:
                            next_pu = next_pu_cell.split(';')[0]
                        else:
                            next_pu = next_pu_cell
                        Start_Finish.append({delivery: next_pu})
                    except IndexError:
                        continue
                elif (';' not in pu) and (';' in delivery):
                    print ('several deliveries')
                    print(date, pu, delivery)
                    delivery_list = delivery.split(';')
                    Start_Finish.append({pu:delivery_list[0]})
                    for i in range(len(delivery_list)):
                        try:
                            Start_Finish.append({delivery_list[i]:delivery_list[i+1]})
                        except IndexError:
                            break

                    try:
                        next_pu_cell = PUs[item + 1][0]
                        if ';' in next_pu_cell:
                            next_pu = next_pu_cell.split(';')[0]
                        else:
                            next_pu = next_pu_cell
                        Start_Finish.append({delivery_list[-1]: next_pu})
                    except IndexError:
                        continue
                elif (';' in pu) and (';' in delivery):
                    print ('multiple PU and delivery')
                    print(date, pu, delivery)
                    pu_list = pu.split(';')
                    delivery_list = delivery.split(';')
                    for i in range(len(pu_list)):
                        try:
                            Start_Finish.append({pu_list[i]:pu_list[i+1]})
                        except IndexError:
                            Start_Finish.append({pu_list[-1]:delivery_list[0]})
                    for i in range(len(delivery_list)):
                        try:
                            Start_Finish.append({delivery_list[i]:delivery_list[i+1]})
                        except IndexError:
                            break

                    try:
                        next_pu_cell = PUs[item + 1][0]
                        if ';' in next_pu_cell:
                            next_pu = next_pu_cell.split(';')[0]
                        else:
                            next_pu = next_pu_cell
                        Start_Finish.append({delivery_list[-1]: next_pu})
                    except IndexError:
                        continue
            else:
                continue
        except IndexError:
            continue

    return Start_Finish


def update_cell(driver, cell, letter, value):
    spreadsheetid = id

    rangeName = f"{driver}!{letter}{cell}"
    values = [[value]]

    Body = {
    'values' : values,
    'majorDimension' : 'COLUMNS'
    }

    result = sh.spreadsheets().values().update(spreadsheetId=spreadsheetid, range=rangeName,
    valueInputOption='RAW', body=Body).execute()
    print("Cell Uploaded successfully✅")


def compilate_salary_company_driver(driver, cell, start_date, end_date):
    from fpdf import FPDF

    pdf = FPDF('P', 'mm', 'A4')
    pdf.add_page()

    pdf.set_font('helvetica', 'B', 18)
    pdf.set_text_color(0, 0, 0)
    if driver == "Walter":
        pdf.cell(190, 10, 'Kolobok INC', ln=1, border=False, align='L')
        pdf.cell(190, 10, 'Pay to: Reyes9corp', ln=1, border=False, align='L')
        pdf.cell(190, 10, f'Statement {start_date} - {end_date}', ln=1, border=False, align='L')
    elif driver == "Nestor":
        pdf.cell(190, 10, 'Kolobok INC', ln=1, border=False, align='L')
        pdf.cell(190, 10, 'Pay to: LION TRANSPORT LLC', ln=1, border=False, align='L')
        pdf.cell(190, 10, f'Statement {start_date} - {end_date}', ln=1, border=False, align='L')
    else:
        print('Error, I dont know this driver, please update the code')

    pdf.set_font('helvetica', 'B', 14)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(15, 15, 'Loads Complete:', ln=1, border=False, align='L')

    pdf.set_font('helvetica', 'B', 8)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(15, 5, 'PU date', ln=0, border=True, align='L')
    pdf.cell(15, 5, 'Del date', ln=0, border=True, align='L')
    pdf.cell(30, 5, 'From:', ln=0, border=True, align='L')
    pdf.cell(30, 5, 'To:', ln=0, border=True, align='L')
    pdf.cell(30, 5, 'Broker', ln=0, border=True, align='L')
    pdf.cell(15, 5, 'Gross', ln=0, border=True, align='L')
    pdf.cell(10, 5, 'Miles', ln=0, border=True, align='L')
    pdf.cell(17, 5, 'Kolobok %', ln=0, border=True, align='L')
    pdf.cell(15, 5, 'Gross - %', ln=1, border=True, align='L')

    # Fetch first row data
    range_data = driver + '!' + f'A{cell}:U{cell}'
    result = sh.spreadsheets().values().get(spreadsheetId=SHEET_ID, range=range_data).execute()
    values = result.get('values')[0]

    total_gross = total_miles = total_commission = total_loads = 0
    count = 0

    while True:
        pudate = values[0]
        deldate = values[2]
        pu = values[4]
        deliv = values[5]
        broker = values[6]
        gross = float(values[9])
        commision_rate = float(values[20]) / 100.0
        miles_str = values[10]

        def _f(x, n=24): return (x or '')[:n]
        pu, deliv, broker = _f(pu), _f(deliv), _f(broker)
        try: miles = float(miles_str)
        except Exception: miles = 0.0

        commision = gross * commision_rate
        w_gets = gross - commision

        pdf.set_font('helvetica', '', 7)
        pdf.set_text_color(0, 0, 0)
        def check_chars(t, n): return t[:n-1] if len(t) > n else t
        pdf.cell(15, 5, pudate, ln=0, border=True, align='L')
        pdf.cell(15, 5, deldate, ln=0, border=True, align='L')
        pdf.cell(30, 5, check_chars(pu, 20), ln=0, border=True, align='L')
        pdf.cell(30, 5, check_chars(deliv, 20), ln=0, border=True, align='L')
        pdf.cell(30, 5, check_chars(broker, 20), ln=0, border=True, align='L')
        pdf.cell(15, 5, str(round(gross, 2))[:9], ln=0, border=True, align='L')
        pdf.cell(10, 5, str(round(miles, 2)), ln=0, border=True, align='L')
        pdf.cell(17, 5, str(round(commision, 2))[:9], ln=0, border=True, align='L')
        pdf.cell(15, 5, str(round(w_gets, 2))[:9], ln=1, border=True, align='L')

        total_gross += gross
        total_miles += miles
        total_commission += commision
        total_loads += w_gets
        count += 1
        cell += 1

        range_next = driver + '!' + f'A{cell}:U{cell}'
        result = sh.spreadsheets().values().get(spreadsheetId=SHEET_ID, range=range_next).execute()
        if 'values' in result:
            values = result.get('values')[0]
        else:
            break

    # Totals row
    pdf.set_font('helvetica', 'B', 8)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(15, 5, '', ln=0, border=True, align='L')
    pdf.cell(15, 5, '', ln=0, border=True, align='L')
    pdf.cell(30, 5, '', ln=0, border=True, align='L')
    pdf.cell(30, 5, '', ln=0, border=True, align='L')
    pdf.cell(30, 5, 'Totals:', ln=0, border=True, align='R')
    pdf.cell(15, 5, str(round(total_gross, 2))[:9], ln=0, border=True, align='L')
    pdf.cell(10, 5, str(round(total_miles, 2))[:9], ln=0, border=True, align='L')
    pdf.cell(17, 5, str(round(total_commission, 2))[:9], ln=0, border=True, align='L')
    pdf.cell(15, 5, str(round(total_loads, 2))[:9], ln=1, border=True, align='L')

    total_loads_str = str(round(total_loads, 2))
    pdf.set_font('helvetica', 'B', 14)
    pdf.set_text_color(0, 0, 0)
    pdf.set_fill_color(232, 253, 226)
    pdf.cell(177, 15, f'Total for loads: ${total_loads_str}', ln=1, border=False, align='L', fill=True)

    # Extra charges (Z/AA backtracking)
    extra_charges = {}
    while count != 0:
        try:
            range_ex_charge = driver + '!' + f'Z{cell}'
            res1 = sh.spreadsheets().values().get(spreadsheetId=SHEET_ID, range=range_ex_charge).execute()
            ex_charge = float(res1.get('values')[0][0])

            range_ex_exp = driver + '!' + f'AA{cell}'
            res2 = sh.spreadsheets().values().get(spreadsheetId=SHEET_ID, range=range_ex_exp).execute()
            ex_exp = res2.get('values')[0][0]

            extra_charges[ex_exp] = ex_charge
            cell -= 1; count -= 1
        except TypeError:
            cell -= 1; count -= 1
            continue

    extra_total = 0
    extra_line = ''
    for label, val in extra_charges.items():
        v = float(val); extra_total += v
        shown = abs(v)
        extra_line += f"{'+ ' if v<0 else '- '}${shown:.2f} "
        perc = (((shown * 100) / float(total_loads_str)) / 100) * 177
        pdf.set_font('helvetica', '', 12)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(177, 10, f'{label}: ${shown:.2f}', ln=1, border=False, align='L', fill=False)
        pdf.set_font('helvetica', 'B', 14)
        pdf.set_text_color(0, 0, 0)
        if v < 0: pdf.set_fill_color(85, 252, 37)
        else:     pdf.set_fill_color(252, 66, 37)
        pdf.cell(perc, 0.5, '', ln=1, border=False, align='L', fill=True)

    pdf.set_font('helvetica', 'B', 14)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(15, 15, f'Final pay: ${total_loads_str} {extra_line.strip()}', ln=1, border=False, align='L')

    settlement = float(total_loads_str) - extra_total
    settlement = float('{:.3f}'.format(settlement))
    settlement_str = str(settlement)
    pdf.set_font('helvetica', 'B', 14)
    pdf.set_text_color(0, 0, 0)
    pdf.set_fill_color(74, 245, 44)
    pdf.cell(177, 15, f'Settlement Total: ${settlement_str}', ln=1, border=False, align='C', fill=True)

    pdf.set_font('helvetica', '', 8)
    pdf.set_text_color(0, 0, 0)
    pdf.output('./files_cash/1st_page.pdf')


def compilate_salary_page(driver, cell, start_date, end_date, totals, discount, insurance, insurance_d, trailer, trailer_d):
    pdf = FPDF('P', 'mm', 'A4')  # create FPDF object
    pdf.add_page()

    pdf.set_font('helvetica', 'B', 18)
    pdf.set_text_color(0, 0, 0)
    if driver == "Walter":
        pdf.cell(190, 10, f'Kolobok INC', ln=1, border=False, align='L')
        pdf.cell(190, 10, f'Pay to: Reyes9corp', ln=1, border=False, align='L')
        pdf.cell(190, 10, f'Statement {start_date} - {end_date}', ln=1, border=False, align='L')
    elif driver == "Denis":
        pdf.cell(190, 10, f'Kolobok INC', ln=1, border=False, align='L')
        pdf.cell(190, 10, f'Pay to: Black Thunder Logistics INC', ln=1, border=False, align='L')
        pdf.cell(190, 10, f'Statement {start_date} - {end_date}', ln=1, border=False, align='L')
    elif driver == "Yura":
        pdf.cell(190, 10, f'Kolobok INC', ln=1, border=False, align='L')
        pdf.cell(190, 10, f'Pay to: Kolobok INC', ln=1, border=False, align='L')
        pdf.cell(190, 10, f'Statement {start_date} - {end_date}', ln=1, border=False, align='L')
    elif driver == "Nestor":
        pdf.cell(190, 10, f'Kolobok INC', ln=1, border=False, align='L')
        pdf.cell(190, 10, f'Pay to: LION TRANSPORT LLC', ln=1, border=False, align='L')
        pdf.cell(190, 10, f'Statement {start_date} - {end_date}', ln=1, border=False, align='L')
    else:
        print('Error, I dont know this driver, please update the code')
    pdf.set_font('helvetica', 'B', 14)
    pdf.set_text_color(0, 0, 0)

    pdf.cell(15, 15, 'Loads Complete:', ln=1, border=False, align='L')

    pdf.set_font('helvetica', 'B', 8)
    pdf.set_text_color(0, 0, 0)

    pdf.cell(15, 5, 'PU date', ln=0, border=True, align='L')
    pdf.cell(15, 5, 'Del date', ln=0, border=True, align='L')
    pdf.cell(30, 5, 'From:', ln=0, border=True, align='L')
    pdf.cell(30, 5, 'To:', ln=0, border=True, align='L')
    pdf.cell(30, 5, 'Broker', ln=0, border=True, align='L')
    pdf.cell(15, 5, 'Gross', ln=0, border=True, align='L')
    pdf.cell(10, 5, 'Miles', ln=0, border=True, align='L')
    pdf.cell(17, 5, 'Kolobok %', ln=0, border=True, align='L')
    pdf.cell(15, 5, 'Gross - %', ln=1, border=True, align='L')


    # --------------------------

    # Fetch all the required data in a single API call
    range_data = driver + '!' + f'A{cell}:U{cell}'
    result = sh.spreadsheets().values().get(spreadsheetId=SHEET_ID, range=range_data).execute()
    values = result.get('values')[0]

    total_loads = 0
    count = 0

    # New accumulative variables
    total_gross = 0
    total_miles = 0
    total_commission = 0

    while True:
        pudate = values[0]
        deldate = values[2]
        pu = values[4]
        deliv = values[5]
        broker = values[6]
        gross = float(values[9])
        commision_rate = float(values[20])
        miles_str = values[10]

        pu = pu[0:24]
        deliv = deliv[0:24]
        broker = broker[0:24]
        commision_rate = commision_rate / 100
        commision = gross * commision_rate
        w_gets = gross - commision

        # Convert miles to float if possible, else default to 0
        try:
            miles = float(miles_str)
        except ValueError:
            miles = 0

        pdf.set_font('helvetica', '', 7)
        pdf.set_text_color(0, 0, 0)

        # Check text, so it won't overlap
        def check_chars(input_text, length):
            if len(input_text) > length:
                final_text = input_text[:length - 1]
            else:
                final_text = input_text
            return final_text

        pdf.cell(15, 5, pudate, ln=0, border=True, align='L')
        pdf.cell(15, 5, deldate, ln=0, border=True, align='L')
        pdf.cell(30, 5, check_chars(pu, 20), ln=0, border=True, align='L')
        pdf.cell(30, 5, check_chars(deliv, 20), ln=0, border=True, align='L')
        pdf.cell(30, 5, check_chars(broker, 20), ln=0, border=True, align='L')
        pdf.cell(15, 5, str(round(gross, 2))[:9], ln=0, border=True, align='L')
        pdf.cell(10, 5, str(round(miles, 2)), ln=0, border=True, align='L')
        pdf.cell(17, 5, str(round(commision, 2))[:9], ln=0, border=True, align='L')
        pdf.cell(15, 5, str(round(w_gets, 2))[:9], ln=1, border=True, align='L')
        print(pudate, deldate, pu, deliv, broker, gross, miles, commision, w_gets)

        # Update accumulative totals
        total_gross += gross
        total_miles += miles
        total_commission += commision
        total_loads += w_gets
        count += 1
        cell += 1

        # Fetch the next row data
        range_data = driver + '!' + f'A{cell}:U{cell}'
        result = sh.spreadsheets().values().get(spreadsheetId=SHEET_ID, range=range_data).execute()
        if 'values' in result:
            values = result.get('values')[0]
        else:
            break

    # Print summary row after loads table
    pdf.set_font('helvetica', 'B', 8)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(15, 5, '', ln=0, border=True, align='L')  # PU date empty
    pdf.cell(15, 5, '', ln=0, border=True, align='L')  # Del date empty
    pdf.cell(30, 5, '', ln=0, border=True, align='L')  # From:
    pdf.cell(30, 5, '', ln=0, border=True, align='L')  # To:
    pdf.cell(30, 5, 'Totals:', ln=0, border=True, align='R')
    pdf.cell(15, 5, str(round(total_gross, 2))[:9], ln=0, border=True, align='L')  # Sum of Gross
    pdf.cell(10, 5, str(round(total_miles, 2))[:9], ln=0, border=True, align='L')  # Sum of Miles
    pdf.cell(17, 5, str(round(total_commission, 2))[:9], ln=0, border=True, align='L')  # sum of Kolobok %
    pdf.cell(15, 5, str(round(total_loads, 2))[:9], ln=1, border=True, align='L')  # sum of net earnings (Gross - %)

    total_loads_str = str(round(total_loads, 2))
    pdf.set_font('helvetica', 'B', 14)
    pdf.set_text_color(0, 0, 0)
    pdf.set_fill_color(232, 253, 226)
    pdf.cell(177, 15, f'Total for loads: ${total_loads_str}', ln=1, border=False, align='L', fill=True)

    total_fuel = totals + discount
    total_fuel = float('{:.3f}'.format(total_fuel))
    tot_fuel_perc = (((total_fuel * 100) / float(total_loads_str)) / 100) * 177
    total_fuel_str = str(total_fuel)
    pdf.set_font('helvetica', '', 12)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(177, 10, f'Fuel before discount: ${total_fuel_str}', ln=1, border=False, align='L', fill=False)
    pdf.set_font('helvetica', 'B', 14)
    pdf.set_text_color(0, 0, 0)
    pdf.set_fill_color(252, 239, 37)
    pdf.cell(tot_fuel_perc, 0.5, '', ln=1, border=False, align='L', fill=True)

    discount_str = str(discount)
    disc_perc = (((float(discount_str) * 100) / float(total_loads_str)) / 100) * 177
    pdf.set_font('helvetica', '', 12)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(177, 10, f'Discount: ${discount_str}', ln=1, border=False, align='L', fill=False)
    pdf.set_font('helvetica', 'B', 14)
    pdf.set_text_color(0, 0, 0)
    pdf.set_fill_color(85, 252, 37)
    pdf.cell(disc_perc, 0.5, '', ln=1, border=False, align='L', fill=True)

    totals_str = str(totals)
    fuel_after_disc_perc = (((float(totals_str) * 100) / float(total_loads_str)) / 100) * 177
    pdf.set_font('helvetica', '', 12)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(177, 10, f'Fuel after discount: ${totals_str}', ln=1, border=False, align='L', fill=False)
    pdf.set_font('helvetica', 'B', 14)
    pdf.set_text_color(0, 0, 0)
    pdf.set_fill_color(252, 66, 37)
    pdf.cell(fuel_after_disc_perc, 0.5, '', ln=1, border=False, align='L', fill=True)


    insurance_str = str(insurance)
    insurance_perc = (((float(insurance_str) * 100) / float(total_loads_str)) / 100) * 177
    pdf.set_font('helvetica', '', 12)
    pdf.set_text_color(0, 0, 0)
    if driver == 'Javier':
        pdf.cell(177, 10, f'Insurance: ({insurance_d})', ln=1, border=False, align='L', fill=False)
    else:
        pdf.cell(177, 10, f'Insurance: ${insurance_str} ({insurance_d})', ln=1, border=False, align='L', fill=False)
    pdf.set_font('helvetica', 'B', 14)
    pdf.set_text_color(0, 0, 0)
    pdf.set_fill_color(252, 66, 37)
    pdf.cell(insurance_perc, 0.5, '', ln=1, border=False, align='L', fill=True)

    # Only apply trailer payment logic for Nestor
    if driver == 'Nestor':
        trailer_txt_path = os.path.join(os.getcwd(), "trailer.txt")

        try:
            with open(trailer_txt_path, "r") as f:
                current_payment = int(f.read().strip())
        except (FileNotFoundError, ValueError):
            current_payment = 0  # default if file missing or invalid

        if current_payment < 25:
            trailer_note = f"lease-purchase payment {current_payment + 1} out of 25"
            trailer_str = str(trailer)
            trailer_perc = (((float(trailer_str) * 100) / float(total_loads_str)) / 100) * 177
            pdf.set_font('helvetica', '', 12)
            pdf.set_text_color(0, 0, 0)
            pdf.cell(177, 10, f'Trailer: ${float(trailer_str):.2f} ({trailer_note})', ln=1, border=False, align='L', fill=False)
            pdf.set_font('helvetica', 'B', 14)
            pdf.set_text_color(0, 0, 0)
            pdf.set_fill_color(252, 66, 37)
            pdf.cell(trailer_perc, 0.5, '', ln=1, border=False, align='L', fill=True)

            # Update the payment counter
            with open(trailer_txt_path, "w") as f:
                f.write(str(current_payment + 1))
        else:
            trailer = 0  # skip trailer cost from calculation
            trailer_str = "0"
    else:
        # Default logic for other drivers
        trailer_str = str(trailer)
        if float(trailer_str) > 0:
            trailer_perc = (((float(trailer_str) * 100) / float(total_loads_str)) / 100) * 177
            pdf.set_font('helvetica', '', 12)
            pdf.set_text_color(0, 0, 0)
            pdf.cell(177, 10, f'Trailer: ${float(trailer_str):.2f} ({insurance_d})', ln=1, border=False, align='L', fill=False)
            pdf.set_font('helvetica', 'B', 14)
            pdf.set_text_color(0, 0, 0)
            pdf.set_fill_color(252, 66, 37)
            pdf.cell(trailer_perc, 0.5, '', ln=1, border=False, align='L', fill=True)

    extra_charges = {}
    while count != 0:
        # counting extra charges
        try:
            range_ex_charge = driver + '!' + f'Z{cell}'
            result = sh.spreadsheets().values().get(spreadsheetId=SHEET_ID, range=range_ex_charge).execute()
            ex_charge = float(result.get('values')[0][0])
            range_ex_charge_explanation = driver + '!' + f'AA{cell}'
            result = sh.spreadsheets().values().get(spreadsheetId=SHEET_ID, range=range_ex_charge_explanation).execute()
            ex_charge_explanation = result.get('values')[0][0]
            extra_charges[ex_charge_explanation] = ex_charge
            cell -= 1
            count -= 1

        except TypeError:
            cell -= 1
            count -= 1
            continue

    extra_charges_total = 0
    extra_charges_total_string = ''

    for key, value in extra_charges.items():
        extra_charge = float(value)
        extra_charges_explanation = key
        extra_charges_total += extra_charge
        if extra_charge < 0:
            extra_charge = extra_charge * (-1)
            extra_charges_total_string += f"+ ${extra_charge:.2f}"
        else:
            extra_charges_total_string += f"- ${extra_charge:.2f}"

        extra_charge_perc = (((extra_charge * 100) / float(total_loads_str)) / 100) * 177
        pdf.set_font('helvetica', '', 12)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(177, 10, f'{extra_charges_explanation}: ${extra_charge}', ln=1, border=False, align='L', fill=False)
        pdf.set_font('helvetica', 'B', 14)
        pdf.set_text_color(0, 0, 0)
        if float(value) < 0:
            pdf.set_fill_color(85, 252, 37)
        else:
            pdf.set_fill_color(252, 66, 37)
        pdf.cell(extra_charge_perc, 0.5, '', ln=1, border=False, align='L', fill=True)

    extra_charges_total_string = extra_charges_total_string
    print ('Extra charges total: ', extra_charges_total)

    pdf.set_font('helvetica', 'B', 14)
    pdf.set_text_color(0, 0, 0)

    # Build the final pay line dynamically
    final_components = [f'${total_loads_str}', f'- ${totals_str}', f'- ${insurance_str}']
    if float(trailer_str) > 0:
        final_components.append(f'- ${trailer_str}')
    final_components.append(extra_charges_total_string)

    final_pay_line = 'Final pay: ' + ' '.join(final_components)

    pdf.set_font('helvetica', 'B', 14)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(15, 15, final_pay_line, ln=1, border=False, align='L')

    settlement = float(total_loads_str) - float(totals_str) - float(insurance_str) - float(trailer_str) - extra_charges_total
    settlement = float('{:.3f}'.format(settlement))
    settlement_str = str(settlement)
    pdf.set_font('helvetica', 'B', 14)
    pdf.set_text_color(0, 0, 0)
    pdf.set_fill_color(74, 245, 44)
    pdf.cell(177, 15, f'Settlement Total: ${settlement_str}', ln=1, border=False, align='C', fill=True)

    pdf.set_font('helvetica', '', 8)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(177, 60, f'Please see a fuel Transaction Report below...', ln=1, border=False, align='C', fill=False)

    pdf.output(f'./files_cash/1st_page.pdf')


def open_prev_fuel(driver, cell):
    cur_cell = cell
    range = driver+'!'+f'X{1}:X{cur_cell}'
    result = sh.spreadsheets().values().get(spreadsheetId=SHEET_ID, range=range).execute()
    cell_values = result.get('values')
    last_statement = cell_values[-1] # it just takes the last value and skips none values ahead
    return last_statement
def open_prev_insurance(driver, cell):
    cur_cell = cell
    range = driver+'!'+f'Y{1}:Y{cur_cell}'
    result = sh.spreadsheets().values().get(spreadsheetId=SHEET_ID, range=range).execute()
    cell_values = result.get('values')
    last_insurance_date = cell_values[-1] # it just takes the last value and skips none values ahead
    return last_insurance_date

def upload_file(file_name, driver_name, cell, dispatcher=None, RC=None):
    from pydrive.auth import GoogleAuth
    from pydrive.drive import GoogleDrive
    import multiprocessing as mp
    import os
    gauth = GoogleAuth()
    # Creates local webserver and auto handles authentication.
    gauth.LocalWebserverAuth()
    drive = GoogleDrive(gauth)

    folder_id = settings.drive_folder_statements
    file2 = drive.CreateFile({'title': f'{file_name}', 'mimeType':'application/pdf',
                'parents':[{"kind": "drive#fileLink", "id": folder_id}]})
    file2.SetContentFile(file_name)
    file2.Upload()
    #SET PERMISSION
    permission = file2.InsertPermission({
                            'type': 'anyone',
                            'value': 'anyone',
                            'role': 'reader'})

    #SHARABLE LINK
    link=file2['alternateLink']
    #Update cell in g_sheets
    spreadsheetid = id
    if 'Invoice' in file_name:
        column = 'R'
    elif 'POD' in file_name:
        column = 'N'
    elif 'Statement' in file_name:
        column = 'X'
    elif dispatcher == 'Peter':
        column = 'D'
    elif RC:
        column = 'I'
    rangeName = f"{driver_name}!{column}{cell}"
    values = [[link]]

    Body = {
    'values' : values,
    'majorDimension' : 'COLUMNS'
    }

    result = sh.spreadsheets().values().update(spreadsheetId=spreadsheetid, range=rangeName,
    valueInputOption='RAW', body=Body).execute()
    print("Link Uploaded successfully✅")

def compilate_invoice_page(loadnum, driver, cell, broker, pu, pudate, deliv, deldate, innum, gross, lumper_kolobok, lumper_broker):
    now = datetime.datetime.now()
    today = now.strftime("%m-%d-%Y")
    date = today
    gross = float(gross)
    gross = float('{:.3f}'.format(gross))
    gross = str(gross)
    Driver = driver
    def lumper():
        nonlocal gross
        global Lumper
        if lumper_kolobok == '' and lumper_broker != '':
            Lumper = f'(Broker paid, receipt attached) ${lumper_broker}'
        elif lumper_kolobok != '':
            Lumper = f'(Kolobok Inc paid, receipt attached) ${lumper_kolobok}'
            gross = float(gross)+float(lumper_kolobok)
            gross = float('{:.3f}'.format(gross))
            gross = str(gross)
        else:
            Lumper = '<none>'
        return Lumper

    pdf = FPDF('P', 'mm', 'A4')                                              # create FPDF object
    pdf.add_page()                                                           # Add a page
    # specify font
    # fonts ('times', 'courier', 'helvetica', 'symbol', 'zpfdingbats')
    # 'B' (bold), 'U' (underline), 'I' (italics), '' (regular), combination (i.e., ('BU'))

    # ----------------

    txt = 'Kolobok Inc. \n' \
          '9063 Caloosa Rd \n' \
          'Fort Myers, FL 33967 \n' \
          '239-293-1919 or 312-535-3912 \n' \
          'chrisribas89@gmail.com'
    pdf.set_font('times', '', 12)
    pdf.set_text_color(0, 0, 0)
    pdf.multi_cell(0, 5, txt, align='L')

    pdf.set_font('helvetica', 'B', 16)
    pdf.set_text_color(25, 126, 134)
    pdf.cell(0, 10, 'INVOICE', ln=True, align='L')

    pdf.set_font('helvetica', 'B', 12)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(50, 5, 'BILL TO', ln=0, align='L')

    pdf.set_font('helvetica', 'B', 12)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 5, f'INVOICE # {innum}', ln=1, align='R')
    broker_name = f'./customers/{broker}.txt'
    with open(broker_name) as file:
        brokers_adress = file.read()
    pdf.set_font('times', '', 12)
    pdf.set_text_color(0, 0, 0)
    pdf.multi_cell(0, 5, brokers_adress, align='L')

    pdf.set_font('helvetica', 'B', 12)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(160, 5, 'DATE', ln=0, align='R')
    pdf.set_font('helvetica', '', 12)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(30, 5, date, ln=1, align='R')

    pdf.set_font('helvetica', 'B', 12)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(32, 30, 'TRK#/DRIVER', ln=0, align='L')
    pdf.set_font('helvetica', '', 12)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(63, 30, Driver, ln=0, align='L')

    pdf.set_font('helvetica', 'B', 12)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(35, 30, 'LOAD/ORDER #', ln=0, align='L')
    pdf.set_font('helvetica', '', 12)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(60, 30, loadnum, ln=1, align='L')

    # ------------------------
    pdf.set_font('helvetica', '', 12)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 8, 'LOAD DESCRIPTION', ln=1, border=True, align='C')

    pdf.set_font('helvetica', '', 10)
    pdf.set_text_color(25, 126, 134)
    pdf.cell(10, 8, 'SO', ln=0, border=True, align='L')
    pdf.cell(160, 8, 'ADDRESS', ln=0, border=True, align='L')
    pdf.cell(20, 8, 'DATE', ln=1, border=True, align='L')

    pdf.set_text_color(0, 0, 0)
    pdf.cell(10, 10, 'PU', ln=0, border=True, align='L')
    pdf.cell(160, 10, pu, ln=0, border=True, align='L')
    pdf.cell(20, 10, pudate, ln=1, border=True, align='L')

    pdf.cell(10, 10, 'DEL', ln=0, border=True, align='L')
    pdf.cell(160, 10, deliv, ln=0, border=True, align='L')
    pdf.cell(20, 10, deldate, ln=1, border=True, align='L')

    # pdf.set_text_color(25, 126, 134)
    # pdf.cell(95, 8, 'DETENTION', ln=0, border=True, align='L')
    # pdf.set_font('helvetica', '', 12)
    # pdf.set_text_color(0, 0, 0)
    # pdf.cell(95, 8, '<none>', ln=1, border=True, align='R')

    pdf.set_text_color(25, 126, 134)
    pdf.set_font('helvetica', '', 10)
    pdf.cell(95, 8, 'LUMPER', ln=0, border=True, align='L')
    pdf.set_font('helvetica', '', 12)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(95, 8, lumper(), ln=1, border=True, align='R')

    pdf.set_text_color(25, 126, 134)
    pdf.cell(95, 8, 'BALANCE DUE', ln=0, border=True, align='L')
    pdf.set_font('helvetica', 'B', 12)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(95, 8, f'${gross}', ln=1, border=True, align='R')

    pdf.set_text_color(25, 126, 134)
    pdf.set_font('helvetica', '', 10)
    pdf.cell(0, 15, 'PAYMENT INFO:', ln=1, border=True, align='C')

    pdf.cell(95, 8, 'Type of account:', ln=0, border=True, align='L')
    pdf.set_text_color(0, 0, 0)
    pdf.set_font('helvetica', 'B', 10)
    pdf.cell(95, 8, 'Checking', ln=1, border=True, align='L')
    pdf.set_text_color(25, 126, 134)
    pdf.set_font('helvetica', '', 10)

    pdf.cell(95, 8, 'Name as it appears on Bank Account:', ln=0, border=True, align='L')
    pdf.set_text_color(0, 0, 0)
    pdf.set_font('helvetica', 'B', 10)
    pdf.cell(95, 8, 'Kolobok INC.', ln=1, border=True, align='L')
    pdf.set_text_color(25, 126, 134)
    pdf.set_font('helvetica', '', 10)

    pdf.cell(95, 8, 'Bank Name:', ln=0, border=True, align='L')
    pdf.set_text_color(0, 0, 0)
    pdf.set_font('helvetica', 'B', 10)
    pdf.cell(95, 8, 'Chase', ln=1, border=True, align='L')
    pdf.set_text_color(25, 126, 134)
    pdf.set_font('helvetica', '', 10)

    pdf.cell(95, 8, 'Financial institution phone number:', ln=0, border=True, align='L')
    pdf.set_text_color(0, 0, 0)
    pdf.set_font('helvetica', 'B', 10)
    pdf.cell(95, 8, '800-935-9935', ln=1, border=True, align='L')
    pdf.set_text_color(25, 126, 134)
    pdf.set_font('helvetica', '', 10)

    pdf.cell(95, 8, 'Banking Routing / Transfer Number (9 digits):', ln=0, border=True, align='L')
    pdf.set_text_color(0, 0, 0)
    pdf.set_font('helvetica', 'B', 10)
    pdf.cell(95, 8, '267 084 131', ln=1, border=True, align='L')
    pdf.set_text_color(25, 126, 134)
    pdf.set_font('helvetica', '', 10)

    pdf.cell(95, 8, 'Bank Account Number:', ln=0, border=True, align='L')
    pdf.set_text_color(0, 0, 0)
    pdf.set_font('helvetica', 'B', 10)
    pdf.cell(95, 8, '697 061 971', ln=1, border=True, align='L')
    pdf.set_text_color(25, 126, 134)

    # ------------------------

    pdf.set_font('helvetica', '', 10)
    pdf.cell(0, 15, 'PLEASE USE THIS MAIL ADDRESS FOR CHECKS:', ln=1, align='C')
    pdf.set_font('helvetica', 'B', 10)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 8, '9063 Caloosa Rd', ln=1, align='C')
    pdf.cell(0, 8, 'Fort Myers, FL 33967', ln=1, align='C')

    pdf.set_font('helvetica', '', 8)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 10, 'Thank you!', ln=1, align='C')
    pdf.output(f'./files_cash/Invoice_{loadnum}_MC_1294648''.pdf')

def open_invoice_load(driver, cell):
    cur_cell = cell
    range = driver+'!'+f'A{cur_cell}:AA{cur_cell}'
    result = sh.spreadsheets().values().get(spreadsheetId=SHEET_ID, range=range).execute()
    invoice_load = result.get('values')
    return invoice_load

def open_current_load(driver_name):

    cur_cell = get_current_cell(driver_name)
    range = driver_name+'!'+f'A{cur_cell}:V{cur_cell}'
    result = sh.spreadsheets().values().get(spreadsheetId=SHEET_ID, range=range).execute()
    last_load_row = result.get('values')
    return last_load_row

def download_file(file_id, name):
    request = dr.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        status, done = downloader.next_chunk()
        print("Download %d%%" % int(status.progress() * 100))

    # The file has been downloaded into RAM, now save it in a file
    fh.seek(0)
    with open(f'./files_cash/{name}', 'wb') as f:
        shutil.copyfileobj(fh, f)


def passive_dispatch_info(driver):
    cur_cell = get_current_cell(driver)
    range = driver+'!'+f'V{cur_cell}'
    result = sh.spreadsheets().values().get(spreadsheetId=SHEET_ID, range=range).execute()
    empty_time = result.get('values')
    empty_time = empty_time[0][0]
    #--
    range = driver + '!' + f'F{cur_cell}'
    result = sh.spreadsheets().values().get(spreadsheetId=SHEET_ID, range=range).execute()
    origin_loc = result.get('values')
    origin_loc = origin_loc[0][0]
    #--
    range = driver + '!' + f'AB{cur_cell}'
    result = sh.spreadsheets().values().get(spreadsheetId=SHEET_ID, range=range).execute()
    destin_loc = result.get('values')
    destin_loc = destin_loc[0][0]
    #--
    range = driver + '!' + f'AC{cur_cell}'
    result = sh.spreadsheets().values().get(spreadsheetId=SHEET_ID, range=range).execute()
    available_from = result.get('values')
    available_from = available_from[0][0]
    # --
    range = driver + '!' + f'AD{cur_cell}'
    result = sh.spreadsheets().values().get(spreadsheetId=SHEET_ID, range=range).execute()
    available_to = result.get('values')
    available_to = available_to[0][0]

    return empty_time, origin_loc, destin_loc, available_from, available_to

def pu_del_array(driver):

    range_pu = driver + '!' + f'A20:A87'
    result = sh.spreadsheets().values().get(spreadsheetId=SHEET_ID, range=range_pu).execute()
    pu_date = result.get('values')

    range_del = driver + '!' + f'C20:C87'
    result = sh.spreadsheets().values().get(spreadsheetId=SHEET_ID, range=range_del).execute()
    del_date = result.get('values')

    return pu_date, del_date
