# FILE: guard_angel/services/payment_repository.py

import pytesseract
from pdf2image import convert_from_bytes
import re
from .auth import spreadsheet_service as sh
from ..config import settings
from telegram.helpers import escape_markdown

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


async def fetch_payment_data(range_text: str) -> str:
    """
    Fetches and formats payment data from Google Sheets based on driver ranges.
    """
    parsed_ranges = _parse_ranges(range_text)
    if not parsed_ranges:
        return "Invalid format. Please use the format: `Driver Start-End; ...`"

    sheet_ranges = []
    for driver, (start, end) in parsed_ranges.items():
        sheet_ranges.append(f"{driver}!C{start}:O{end}")

    try:
        result = sh.spreadsheets().values().batchGet(
            spreadsheetId=settings.spreadsheet_id,
            ranges=sheet_ranges
        ).execute()
    except Exception as e:
        return f"❌ Error fetching data from Google Sheets: {e}"

    output_lines = ["📄 **Payment Check Summary**\n"]

    for i, driver in enumerate(parsed_ranges.keys()):
        output_lines.append(f"\n--- **Driver: {driver}** ---")
        value_range = result['valueRanges'][i]
        rows = value_range.get('values', [])

        if not rows:
            output_lines.append("No data found for this range.")
            continue

        start_row_num = parsed_ranges[driver][0]
        for row_index, row in enumerate(rows):
            current_row_num = start_row_num + row_index

            del_date = row[0] if len(row) > 0 else "N/A"
            broker = row[4] if len(row) > 4 else "N/A"
            gross = row[7] if len(row) > 7 else "$0"
            lumper = row[12] if len(row) > 12 else "$0"

            output_lines.append(
                f"`{current_row_num}` | {del_date} | **{broker}** | Gross: {gross}, Lumper: {lumper}"
            )

    return "\n".join(output_lines)
