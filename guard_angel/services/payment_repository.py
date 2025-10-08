# FILE: guard_angel/services/payment_repository.py

import pytesseract
from pdf2image import convert_from_bytes
import re
from .auth import spreadsheet_service as sh
from ..config import settings
from telegram.helpers import escape_markdown
from . import core_sheets as sheets
from datetime import datetime

# NOTE: This uses the same pattern as your rate_confirmation.py service.
_sheet_id_cache = {}
def get_sheet_id(tab_name):
    if tab_name not in _sheet_id_cache:
        meta = sheets.sh.spreadsheets().get(spreadsheetId=settings.spreadsheet_id, fields="sheets(properties(sheetId,title))").execute()
        for s in meta["sheets"]:
            if s["properties"]["title"] == tab_name:
                _sheet_id_cache[tab_name] = s["properties"]["sheetId"]
                break
    return _sheet_id_cache.get(tab_name)

def _format_cells_as_green(driver: str, row: int, columns: list[str]):
    """Helper function to change the background color of specified cells to green."""
    requests = []
    # Map column letters to their zero-based index (A=0, B=1, etc.)
    col_map = {chr(ord('A') + i): i for i in range(26)}
    col_map['AD'] = 29
    col_map['AE'] = 30
    
    sheet_id = get_sheet_id(driver)
    if not sheet_id:
        print(f"Could not find sheetId for driver: {driver}")
        return

    for col_letter in columns:
        col_index = col_map.get(col_letter.upper())
        if col_index is None:
            continue
        
        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": row - 1,
                    "endRowIndex": row,
                    "startColumnIndex": col_index,
                    "endColumnIndex": col_index + 1
                },
                "cell": {"userEnteredFormat": {"backgroundColor": {"red": 0.8, "green": 1, "blue": 0.8}}},
                "fields": "userEnteredFormat.backgroundColor"
            }
        })

    if requests:
        sheets.sh.spreadsheets().batchUpdate(
            spreadsheetId=settings.spreadsheet_id,
            body={"requests": requests}
        ).execute()




def _parse_ocr_text(full_text: str) -> list:
    """
    Parses OCR text by grouping lines into transaction records.
    """
    all_payments = []
    lines = full_text.split('\n')
    
    current_date = "Unknown Date"
    current_description_lines = []
    
    line_pattern = re.compile(r'^(Pending|(?:\w{3}\s\d{1,2},\s\d{4}))?(.*?)(\$[\d,]+\.\d{2})?$')

    for line in lines:
        if not line.strip() or "chase.com" in line or "Transactions" in line:
            continue

        match = line_pattern.match(line)
        if not match:
            current_description_lines.append(line.strip())
            continue

        date_part, desc_part, amount_part = match.groups()

        if date_part:
            current_date = date_part.strip()
            current_description_lines = [desc_part.strip()]
        else:
            current_description_lines.append(desc_part.strip())

        if amount_part:
            desc_text_lower = ' '.join(current_description_lines).lower()
            if "available balance" in desc_text_lower or "present balance" in desc_text_lower or "account:" in desc_text_lower:
                current_description_lines = []
                continue

            full_description = " ".join(filter(None, current_description_lines))
            
            try:
                payment_value = float(amount_part.strip().replace("$", "").replace(",", ""))
                all_payments.append({
                    'date': current_date,
                    'description': full_description,
                    'amount': payment_value
                })
            except ValueError:
                continue
            
            current_description_lines = []

    return all_payments


def parse_payment_pdf(pdf_content: bytes) -> list:
    """
    Parses a bank statement PDF using OCR to extract transactions.
    """
    try:
        images = convert_from_bytes(pdf_content)
        full_text = "\n".join([pytesseract.image_to_string(image, config='--psm 6') for image in images])
        return _parse_ocr_text(full_text)
    except Exception as e:
        return [{"Error": f"Could not process PDF with OCR: {e}"}]


def _parse_ranges(text: str) -> dict:
    """
    Parses the driver and row range string.
    """
    ranges = {}
    parts = [p.strip() for p in text.split(';') if p.strip()]
    for part in parts:
        match = re.match(r"(\w+)\s+(\d+)-(\d+)", part)
        if match:
            driver, start, end = match.groups()
            ranges[driver.capitalize()] = (int(start), int(end))
    return ranges


def create_master_prompt(payments: list, loads_data: dict) -> str:
    """Creates a detailed prompt for an LLM to match payments to loads."""
    
    prompt_lines = [
        "Hello. I need you to act as an expert logistics accountant. Your task is to match bank statement payments to a list of unpaid loads. Here is the data:",
        "\n--- BANK PAYMENTS RECEIVED ---"
    ]
    # --- NEW: Sort payments by date to help the AI process them chronologically ---
    sorted_payments = sorted(payments, key=lambda p: datetime.strptime(p['date'], "%b %d, %Y") if 'Pending' not in p['date'] else datetime.max)
    for p in sorted_payments:
        prompt_lines.append(f"Amount: ${p['amount']:.2f}, Date: {p['date']}, Description: {p['description']}")

    prompt_lines.append("\n--- UNPAID LOADS ---")
    for driver, loads in loads_data.items():
        prompt_lines.append(f"\n## Driver: {driver}")
        for load in loads:
            total_due = float(load['gross'].replace(',', '')) + float(load['lumper'].replace(',', ''))
            prompt_lines.append(
                f"Row: {load['row_num']}, Broker: {load['broker']}, Delivery Date: {load['del_date']}, Gross: {load['gross']}, Lumper: {load['lumper']}, Total Due: ${total_due:.2f}"
            )

    prompt_lines.extend([
        "\n--- YOUR TASK ---",
        "1. Analyze both lists. Match each bank payment to the most likely unpaid load.",
        "2. A match is likely if the payment amount is very close to the load's 'Total Due' and the payment description contains the broker's name.",
        # --- MODIFIED: Added a crucial new rule for FIFO logic ---
        "3. **IMPORTANT RULE:** If you find multiple loads with the same 'Total Due' that could match a payment, you **must** assign the payment with the earliest date to the load with the earliest 'Delivery Date'. Follow a 'First-In, First-Out' logic.",
        "4. Provide your response *ONLY* in the following JSON format. Do not add any other text, explanations, or code block markers.",
        "5. CRITICAL: Ensure any backslash characters (`\\`) inside the JSON strings are correctly escaped as double backslashes (`\\\\`).",
        """
{
  "matched_loads": [
    {
      "row_num": <row_number_from_unpaid_loads>,
      "driver": "<Driver's Name>",
      "paid_amount": <payment_amount_float>,
      "paid_date": "<payment_date_string>"
    }
  ],
  "unmatched_payments": [
    {
      "amount": <payment_amount_float>,
      "date": "<payment_date_string>",
      "description": "<payment_description_string>"
    }
  ]
}
""",
        "Example of a single entry in 'matched_loads':",
        '{"row_num": 531, "driver": "Walter", "paid_amount": 1700.00, "paid_date": "Sep 30, 2025"}',
        "Ensure every payment from the bank list appears in either 'matched_loads' (by its amount and date) or 'unmatched_payments'. Do not fabricate matches."
    ])
    
    return "\n".join(prompt_lines)




async def fetch_loads_data(range_text: str) -> dict | str:
    """
    Fetches raw load data from Google Sheets based on driver ranges.
    """
    parsed_ranges = _parse_ranges(range_text)
    if not parsed_ranges:
        return "Invalid format. Please use the format: `Driver Start-End; ...`"

    sheet_ranges = [f"{driver}!C{start}:O{end}" for driver, (start, end) in parsed_ranges.items()]

    try:
        result = sh.spreadsheets().values().batchGet(
            spreadsheetId=settings.spreadsheet_id,
            ranges=sheet_ranges
        ).execute()
    except Exception as e:
        return f"❌ Error fetching data from Google Sheets: {e}"

    loads_by_driver = {}
    value_ranges = result.get('valueRanges', [])

    for i, driver in enumerate(parsed_ranges.keys()):
        loads_by_driver[driver] = []
        if i < len(value_ranges):
            rows = value_ranges[i].get('values', [])
            start_row_num = parsed_ranges[driver][0]

            for row_index, row in enumerate(rows):
                gross_str = (row[7] if len(row) > 7 else "0").replace('$', '').strip()
                lumper_str = (row[12] if len(row) > 12 else "0").replace('$', '').strip()
                
                loads_by_driver[driver].append({
                    "row_num": start_row_num + row_index,
                    "del_date": row[0] if len(row) > 0 else "N/A",
                    "broker": row[4] if len(row) > 4 else "N/A",
                    "gross": gross_str,
                    "lumper": lumper_str,
                })
    return loads_by_driver



async def update_sheet_with_payment(driver: str, row: int, amount: float, date: str):
    """Updates the sheet with payment amount and date, then colors the date cell."""
    try:
        # FIX: Upload amount as a plain number, not a formatted string.
        sheets.update_cell(driver, row, 'AD', amount) 
        sheets.update_cell(driver, row, 'AE', date)
        
        # NEW: Color the date cell green.
        _format_cells_as_green(driver, row, ['AE'])
        
    except Exception as e:
        print(f"Error updating sheet for {driver}, row {row}: {e}")
        raise e


async def upload_payment_screenshot(local_path: str, driver: str, row: int):
    """Uploads the payment screenshot, updates the sheet link, and colors the cell."""
    try:
        sheets.upload_file(local_path, driver, row, column='W')
        
        # NEW: Color the screenshot link cell green.
        _format_cells_as_green(driver, row, ['W'])
        
    except Exception as e:
        print(f"Error uploading screenshot for {driver}, row {row}: {e}")
        raise e

def parse_manual_assignment(text: str) -> tuple[str, int] | None:
    """Parses a 'Driver Row' string into a tuple."""
    match = re.match(r"(\w+)\s+(\d+)", text.strip())
    if match:
        driver, row = match.groups()
        return driver.capitalize(), int(row)
    return None

