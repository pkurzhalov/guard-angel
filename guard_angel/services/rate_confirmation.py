import os
import io
import shutil
import fitz
import subprocess
from datetime import datetime
from pdf2image import convert_from_bytes
from . import sheets
from ..config import settings
from .rc_mileage_calculator import mileage_browser as rc_mileage_browser

_sheet_id_cache = {}

def get_sheet_id(tab_name):
    if tab_name not in _sheet_id_cache:
        meta = sheets.sh.spreadsheets().get(spreadsheetId=settings.spreadsheet_id, fields="sheets(properties(sheetId,title))").execute()
        for s in meta["sheets"]:
            if s["properties"]["title"] == tab_name: _sheet_id_cache[tab_name] = s["properties"]["sheetId"]; break
    return _sheet_id_cache.get(tab_name)

def lookup_accounting_email(broker: str) -> str | None:
    drivers_to_search = settings.email_lookup_drivers
    ranges_to_get = [f"{driver}!G2:G" for driver in drivers_to_search] + [f"{driver}!T2:T" for driver in drivers_to_search]
    all_data = sheets.sh.spreadsheets().values().batchGet(spreadsheetId=settings.spreadsheet_id, ranges=ranges_to_get).execute()['valueRanges']
    num_drivers = len(drivers_to_search)
    for i in range(num_drivers):
        brokers = all_data[i].get('values', []); emails = all_data[i + num_drivers].get('values', [])
        for j in range(len(brokers)-1, -1, -1):
            try:
                if brokers[j][0].lower() == broker.lower() and emails[j][0]: return emails[j][0]
            except IndexError: continue
    return None

def write_load_to_sheet(driver: str, data: dict, signed_rc_path: str) -> str | None:
    next_row = sheets.get_current_cell(driver, column="A") + 1
    sheets.upload_file(signed_rc_path, driver, next_row, column='I')
    update_map = {'A': data.get("PU Date"), 'B': data.get("PU Time"), 'C': data.get("Delivery Date"), 'D': data.get("Delivery Time"), 'E': data.get("PU Location"), 'F': data.get("Delivery Location"), 'G': data.get("Broker Name"), 'H': data.get("Load Number"), 'J': data.get("Rate"), 'M': f"{data.get('Temperature', '')}\nPU#: {data.get('PU Number', '')}\n{data.get('Other Notes', '')}", 'Q': "\n".join(data.get("Broker Emails", [])), 'V': data.get("Estimated Empty Time")}
    for col, val in update_map.items():
        if val is not None: sheets.update_cell(driver, next_row, col, val)
    prev_s_val = sheets.sh.spreadsheets().values().get(spreadsheetId=settings.spreadsheet_id, range=f"{driver}!S{next_row-1}").execute().get('values', [[0]])[0][0]
    next_s = int(prev_s_val) + 1 if str(prev_s_val).isdigit() else 1
    sheets.update_cell(driver, next_row, 'S', next_s)
    acc_email = lookup_accounting_email(data.get("Broker Name"))
    if acc_email: sheets.update_cell(driver, next_row, 'T', acc_email)
    last_location = get_last_load_location(driver)
    # CHANGE TO THIS:
    total_miles = rc_mileage_browser.get_miles(
        last_location,
        data.get("PU Location", ""),
        data.get("Delivery Location", "")
    )
    if total_miles is None: total_miles = 0; rpm = 0
    else: rate_str = str(data.get("Rate", "0")).replace(",", "").replace("$", ""); rpm = (float(rate_str) / total_miles) if total_miles > 0 else 0
    sheets.update_cell(driver, next_row, 'K', str(total_miles)); sheets.update_cell(driver, next_row, 'L', f"{rpm:.2f}")
    commission_map = {"Walter": 70, "Yura": 5, "Nestor": 67, "Javier": 70, "Denis": 70}
    sheets.update_cell(driver, next_row, 'U', commission_map.get(driver, ""))
    requests = [{"repeatCell": {"range": {"sheetId": get_sheet_id(driver), "startRowIndex": next_row-1, "endRowIndex": next_row, "startColumnIndex": 0, "endColumnIndex": 27}, "cell": {"userEnteredFormat": {"backgroundColor": {"red": 1, "green": 1, "blue": 0.6}}}, "fields": "userEnteredFormat.backgroundColor"}}]
    if acc_email:
        requests.append({"repeatCell": {"range": {"sheetId": get_sheet_id(driver), "startRowIndex": next_row-1, "endRowIndex": next_row, "startColumnIndex": 6, "endColumnIndex": 7}, "cell": {"userEnteredFormat": {"backgroundColor": {"red": 0.8, "green": 1, "blue": 0.8}}}, "fields": "userEnteredFormat.backgroundColor"}})
    sheets.sh.spreadsheets().batchUpdate(spreadsheetId=settings.spreadsheet_id, body={"requests": requests}).execute()
    return acc_email
def get_last_load_location(driver: str) -> str:
    try:
        last_row = sheets.get_current_cell(driver, column="C")
        result = sheets.sh.spreadsheets().values().get(spreadsheetId=settings.spreadsheet_id, range=f"{driver}!F{last_row}").execute()
        return result.get('values', [['Fort Myers, FL']])[0][0]
    except Exception: return "Fort Myers, FL"
def launch_and_wait_for_gui() -> bool:
    try:
        python_executable = os.path.join(os.getcwd(), 'venv', 'bin', 'python')
        gui_script_path = os.path.join(os.getcwd(), 'guard_angel', 'sign_rc_gui.py')
        result = subprocess.run([python_executable, gui_script_path], check=True, capture_output=True, text=True)
        return True
    except Exception as e:
        print(f"Failed to launch GUI: {e}"); return False
def get_driver_signature_text(driver_name: str) -> str:
    signatures = {"Walter": "Driver:\nWalter\n321-368-0207\ntrk#708\ntrlr # 2102","Yura": "Driver:\nYury Dereviankin\nph# 239-293-1919\ntrk# 1511\ntrlr# 55","Nestor": "Driver:\nNestor\n786-226-5816\ntrk#1511\ntrlr # 570260",}
    dispatcher_info = "\nDispatcher:\nChris Ribas\nph# 312-535-3912\nchrisribas89@gmail.com"
    return signatures.get(driver_name, "Driver info not found.") + dispatcher_info
def view_current_load(driver: str) -> tuple[str, str | None, list]:
    last_row = sheets.get_current_cell(driver, column="A")
    row_data = sheets.sh.spreadsheets().values().get(spreadsheetId=settings.spreadsheet_id, range=f"{driver}!A{last_row}:R{last_row}").execute().get('values', [[]])[0]
    if not row_data: raise ValueError(f"No current load data found for {driver}.")

    def get_col(idx, default=''): return row_data[idx] if len(row_data) > idx and row_data[idx] else default

    pu_time = get_col(1); del_time = get_col(3)
    pu_loc = get_col(4); del_loc = get_col(5)
    gross = get_col(9); miles = get_col(10); rpm = get_col(11)
    dispatch_notes = get_col(12); rc_link = get_col(8)

    summary = (f"🚚{pu_loc}➡️{del_loc}\nDispatch notes: {dispatch_notes}\n\nPU in 🚚{pu_loc}: {pu_time}\nDEL in ➡️{del_loc}: {del_time}\n\nTotal Miles(DH included): {miles}\nGross: {gross}💵\nRPM: ${rpm} per mile")

    image_paths = []
    if rc_link:
        rc_id = sheets.get_id_from_link(rc_link)
        rc_path = f"./files_cash/CURRENT_RC_{driver}.pdf"
        sheets.download_file(rc_id, os.path.basename(rc_path))
        with open(rc_path, "rb") as f: images = convert_from_bytes(f.read())
        for i, image in enumerate(images):
            path = f"./files_cash/RC_PAGE_{i+1}.png"
            image.save(path, "PNG")
            image_paths.append(path)

    return summary, rc_link, image_paths
