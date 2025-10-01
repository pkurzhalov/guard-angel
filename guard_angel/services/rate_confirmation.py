import os
import io
import shutil
import json
import fitz
import subprocess
from datetime import datetime
from pdf2image import convert_from_bytes
from . import sheets
from ..config import settings
from .mileage_calculator import mileage_browser

_sheet_id_cache = {}

def get_sheet_id(tab_name):
    if tab_name not in _sheet_id_cache:
        meta = sheets.sh.spreadsheets().get(spreadsheetId=settings.spreadsheet_id, fields="sheets(properties(sheetId,title))").execute()
        for s in meta["sheets"]:
            if s["properties"]["title"] == tab_name:
                _sheet_id_cache[tab_name] = s["properties"]["sheetId"]; break
    return _sheet_id_cache.get(tab_name)

def lookup_accounting_email(driver, broker):
    last_row = sheets.get_current_cell(driver, column="G")
    res = sheets.sh.spreadsheets().values().batchGet(spreadsheetId=settings.spreadsheet_id, ranges=[f"{driver}!G2:G{last_row}", f"{driver}!T2:T{last_row}"]).execute()['valueRanges']
    brokers = res[0].get('values', []); emails = res[1].get('values', [])
    for i in range(len(brokers)-1, -1, -1):
        try:
            if brokers[i][0] == broker and emails[i][0]: return emails[i][0]
        except IndexError: continue
    return None

def get_last_load_location(driver: str) -> str:
    try:
        last_row = sheets.get_current_cell(driver, column="C")
        result = sheets.sh.spreadsheets().values().get(spreadsheetId=settings.spreadsheet_id, range=f"{driver}!F{last_row}").execute()
        return result.get('values', [['Fort Myers, FL']])[0][0]
    except Exception: return "Fort Myers, FL"

def write_load_to_sheet(driver: str, data: dict, signed_rc_path: str):
    next_row = sheets.get_current_cell(driver, column="A") + 1
    sheets.upload_file(signed_rc_path, driver, next_row, column='I')
    update_map = {
        'A': data.get("PU Date"), 'B': data.get("PU Time"), 'C': data.get("Delivery Date"),
        'D': data.get("Delivery Time"), 'E': data.get("PU Location"), 'F': data.get("Delivery Location"),
        'G': data.get("Broker Name"), 'H': data.get("Load Number"), 'J': data.get("Rate"),
        'M': f"{data.get('Temperature', '')}\nPU#: {data.get('PU Number', '')}\n{data.get('Other Notes', '')}",
        'Q': "\n".join(data.get("Broker Emails", [])), 'V': data.get("Estimated Empty Time")
    }
    for col, val in update_map.items():
        if val is not None: sheets.update_cell(driver, next_row, col, val)
    
    prev_s_val = sheets.sh.spreadsheets().values().get(spreadsheetId=settings.spreadsheet_id, range=f"{driver}!S{next_row-1}").execute().get('values', [[0]])[0][0]
    next_s = int(prev_s_val) + 1 if str(prev_s_val).isdigit() else 1
    sheets.update_cell(driver, next_row, 'S', next_s)
    
    acc_email = lookup_accounting_email(driver, data.get("Broker Name"))
    if acc_email: sheets.update_cell(driver, next_row, 'T', acc_email)
    
    last_location = get_last_load_location(driver)
    total_miles = mileage_browser.get_miles(last_location, data.get("PU Location", ""), data.get("Delivery Location", ""))
    
    # **FIX**: Gracefully handle mileage lookup failure
    if total_miles is None:
        total_miles = 0
        rpm = 0
    else:
        rate_str = str(data.get("Rate", "0")).replace(",", "").replace("$", "")
        rpm = (float(rate_str) / total_miles) if total_miles > 0 else 0

    sheets.update_cell(driver, next_row, 'K', total_miles)
    sheets.update_cell(driver, next_row, 'L', f"{rpm:.2f}")

    commission_map = {"Walter": 70, "Yura": 5, "Nestor": 67, "Javier": 70, "Denis": 70}
    sheets.update_cell(driver, next_row, 'U', commission_map.get(driver, ""))
    
    paint_request = {"repeatCell": {"range": {"sheetId": get_sheet_id(driver), "startRowIndex": next_row-1, "endRowIndex": next_row},"cell": {"userEnteredFormat": {"backgroundColor": {"red": 1, "green": 1, "blue": 0.6}}},"fields": "userEnteredFormat.backgroundColor"}}
    sheets.sh.spreadsheets().batchUpdate(spreadsheetId=settings.spreadsheet_id, body={"requests": [paint_request]}).execute()
    return next_row
    
def launch_and_wait_for_gui() -> bool:
    try:
        python_executable = os.path.join(os.getcwd(), 'venv', 'bin', 'python')
        gui_script_path = os.path.join(os.getcwd(), 'guard_angel', 'sign_rc_gui.py')
        result = subprocess.run([python_executable, gui_script_path], check=True, capture_output=True, text=True)
        return True
    except Exception as e:
        print(f"Failed to launch GUI: {e}"); return False
def get_driver_signature_text(driver_name: str) -> str:
    signatures = {
        "Walter": "Driver:\nWalter\n321-368-0207\ntrk#708\ntrlr # 2102",
        "Yura": "Driver:\nYury Dereviankin\nph# 239-293-1919\ntrk# 1511\ntrlr# 55",
        "Nestor": "Driver:\nNestor\n786-226-5816\ntrk#1511\ntrlr # 570260",
    }
    dispatcher_info = "\nDispatcher:\nChris Ribas\nph# 312-535-3912\nchrisribas89@gmail.com"
    return signatures.get(driver_name, "Driver info not found.") + dispatcher_info
def view_current_load(driver: str) -> tuple[str, list]:
    last_row = sheets.get_current_cell(driver, column="C")
    row_data = sheets.open_invoice_load(driver, last_row)
    if not row_data or not row_data[0]: raise ValueError(f"No current load data found for {driver}.")
    data = row_data[0]
    pu_loc = data[4] if len(data) > 4 else '?'; del_loc = data[5] if len(data) > 5 else '?'
    broker = data[6] if len(data) > 6 else '?'; load_num = data[7] if len(data) > 7 else '?'
    rc_link = data[8] if len(data) > 8 else None
    summary = (f"**Current Load for {driver} (Row {last_row})**\n\n**Broker:** {broker}\n**Load #:** {load_num}\n**Route:** {pu_loc} ➡️ {del_loc}")
    if not rc_link: return summary, []
    rc_id = sheets.get_id_from_link(rc_link); rc_path = f"./files_cash/CURRENT_RC_{driver}.pdf"
    sheets.download_file(rc_id, os.path.basename(rc_path))
    with open(rc_path, "rb") as f: images = convert_from_bytes(f.read())
    image_paths = []
    for i, image in enumerate(images):
        path = f"./files_cash/RC_PAGE_{i+1}.png"; image.save(path, "PNG"); image_paths.append(path)
    return summary, image_paths
