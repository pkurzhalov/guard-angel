import os
import shutil
import fitz # PyMuPDF
from datetime import datetime
from pdf2image import convert_from_bytes
from geopy import distance, Nominatim

from . import sheets
from ..config import settings

geocoder = Nominatim(user_agent="guard_angel_geocoder", timeout=10)

def sign_rc_pdf(input_path: str, output_path: str, custom_text: str | None) -> bool:
    """
    Signs the RC PDF by adding a signature image, the current date, and optional custom text
    using pre-defined coordinates from the settings.
    """
    try:
        pdf_doc = fitz.open(input_path)
        page = pdf_doc[0] # Work on the first page

        # 1. Insert Signature Image
        sig_rect = fitz.Rect(
            settings.signature_coords_x, 
            settings.signature_coords_y, 
            settings.signature_coords_x + (150 / settings.signature_scale), # width
            settings.signature_coords_y + (75 / settings.signature_scale)  # height
        )
        page.insert_image(sig_rect, filename=settings.signature_img_path)

        # 2. Insert Date
        today_str = datetime.now().strftime("%m/%d/%Y")
        date_point = fitz.Point(settings.date_coords_x, settings.date_coords_y)
        page.insert_text(date_point, today_str, fontsize=11, fontname="helv")
        
        # 3. Insert Custom Text (if provided)
        if custom_text and custom_text.lower() != 'none':
            text_point = fitz.Point(settings.custom_text_coords_x, settings.custom_text_coords_y)
            page.insert_text(text_point, custom_text, fontsize=11, fontname="helv")

        pdf_doc.save(output_path)
        pdf_doc.close()
        return True
    except Exception as e:
        print(f"Error signing PDF: {e}")
        return False

# (The rest of the service functions remain the same)
def get_last_load_location(driver: str) -> str:
    try:
        last_row = sheets.get_current_cell(driver, column="C", refresh=True)
        range_name = f"{driver}!F{last_row}"
        result = sheets.sh.spreadsheets().values().get(spreadsheetId=settings.spreadsheet_id, range=range_name).execute()
        return result.get('values', [['Fort Myers, FL']])[0][0]
    except Exception: return "Fort Myers, FL"
def calculate_deadhead_miles(start_city: str, pickup_city: str) -> int:
    try:
        start_loc = geocoder.geocode(start_city); pickup_loc = geocoder.geocode(pickup_city)
        if start_loc and pickup_loc:
            return round(distance.distance((start_loc.latitude, start_loc.longitude), (pickup_loc.latitude, pickup_loc.longitude)).miles)
    except Exception as e: print(f"Could not calculate deadhead miles: {e}"); return 0
def write_load_to_sheet(driver: str, data: dict, signed_rc_path: str):
    next_row = sheets.get_current_cell(driver, column="A", refresh=True) + 1
    sheets.upload_file(signed_rc_path, driver, next_row)
    update_map = {
        'A': data.get("PU Date"), 'B': data.get("PU Time"), 'C': data.get("Delivery Date"),
        'D': data.get("Delivery Time"), 'E': data.get("PU Location"), 'F': data.get("Delivery Location"),
        'G': data.get("Broker Name"), 'H': data.get("Load Number"), 'J': data.get("Rate"),
        'M': f"{data.get('Temperature', '')}\nPU#: {data.get('PU Number', '')}\n{data.get('Other Notes', '')}",
        'Q': "\n".join(data.get("Broker Emails", [])), 'V': data.get("Estimated Empty Time")
    }
    for col, val in update_map.items():
        if val is not None: sheets.update_cell(driver, next_row, col, val)
    last_location = get_last_load_location(driver)
    dh_miles = calculate_deadhead_miles(last_location, data.get("PU Location", ""))
    loaded_miles = calculate_deadhead_miles(data.get("PU Location", ""), data.get("Delivery Location", ""))
    total_miles = dh_miles + loaded_miles
    sheets.update_cell(driver, next_row, 'K', total_miles)
    if total_miles > 0 and data.get("Rate"):
        rpm = float(str(data["Rate"]).replace(',','')) / total_miles
        sheets.update_cell(driver, next_row, 'L', f"{rpm:.2f}")
    commission_map = {"Walter": 70, "Yura": 5, "Nestor": 67, "Javier": 70, "Denis": 70}
    sheets.update_cell(driver, next_row, 'U', commission_map.get(driver, ""))
    return next_row
def view_current_load(driver: str) -> tuple[str, list]:
    last_row = sheets.get_current_cell(driver, column="C", refresh=True)
    row_data = sheets.open_invoice_load(driver, last_row)
    if not row_data or not row_data[0]: raise ValueError(f"No current load data found for {driver}.")
    data = row_data[0]
    pu_loc = data[4] if len(data) > 4 else '?'; del_loc = data[5] if len(data) > 5 else '?'
    broker = data[6] if len(data) > 6 else '?'; load_num = data[7] if len(data) > 7 else '?'
    rc_link = data[17] if len(data) > 17 else None
    summary = (f"**Current Load for {driver} (Row {last_row})**\n\n**Broker:** {broker}\n**Load #:** {load_num}\n**Route:** {pu_loc} ➡️ {del_loc}")
    if not rc_link: return summary, []
    rc_id = sheets.get_id_from_link(rc_link); rc_path = f"./files_cash/CURRENT_RC_{driver}.pdf"
    sheets.download_file(rc_id, os.path.basename(rc_path))
    with open(rc_path, "rb") as f: images = convert_from_bytes(f.read())
    image_paths = []
    for i, image in enumerate(images):
        path = f"./files_cash/RC_PAGE_{i+1}.png"; image.save(path, "PNG"); image_paths.append(path)
    return summary, image_paths
