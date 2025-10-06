import os
import re
import pytesseract
from pdf2image import convert_from_path
import textwrap # Used for formatting the long description text

# Define the name of the PDF file we want to test.
PDF_FILE = "payment.pdf"

def parse_ocr_text(full_text: str) -> list:
    """
    Parses OCR text by grouping lines into transaction records.
    Each record contains a date, the full description, and an amount.
    This approach is more robust as it doesn't try to guess the company name.
    """
    all_payments = []
    lines = full_text.split('\n')
    
    current_date = "Unknown Date"
    current_description_lines = []
    
    # This regex now finds BOTH dates and amounts on the same line.
    # It helps identify the end of a description block.
    line_pattern = re.compile(r'^(Pending|(?:\w{3}\s\d{1,2},\s\d{4}))?(.*?)(\$[\d,]+\.\d{2})?$')

    for line in lines:
        if not line.strip():
            continue

        match = line_pattern.match(line)
        if not match:
            current_description_lines.append(line.strip())
            continue

        date_part, desc_part, amount_part = match.groups()

        # A new date marks the end of the previous transaction.
        if date_part:
            # If we have a pending description, save it before moving on.
            if current_description_lines:
                # This transaction didn't have an amount on its last line, which is rare but possible.
                # We'll assign it amount 0.0 or you could implement a look-ahead search.
                # For this parser, we assume the amount is on the same line or the transaction is invalid.
                pass # Discarding incomplete previous entry

            current_date = date_part.strip()
            # Reset description for the new date group
            current_description_lines = [desc_part.strip()]
        else:
            # If not a new date, just add the text to the current description
            current_description_lines.append(desc_part.strip())

        # An amount ALWAYS signifies the end of a transaction record.
        if amount_part:
            full_description = " ".join(filter(None, current_description_lines))
            
            try:
                payment_value = float(amount_part.strip().replace("$", "").replace(",", ""))
                all_payments.append({
                    'date': current_date,
                    'description': full_description,
                    'amount': payment_value
                })
            except ValueError:
                # This can happen if the amount regex fails for some reason.
                print(f"Warning: Could not parse amount: {amount_part}")

            # Reset for the next transaction
            current_description_lines = []

    return all_payments

def process_pdf_with_ocr(file_path: str):
    if not os.path.exists(file_path):
        print(f"--- ERROR: File not found: '{file_path}' ---")
        return

    print(f"--- Reading text from {file_path} using OCR ---")
    
    try:
        images = convert_from_path(file_path)
        # Use a more layout-aware Page Segmentation Mode (PSM) if available, like 4 or 6.
        # PSM 6: Assume a single uniform block of text.
        full_text = "\n".join([pytesseract.image_to_string(image, config='--psm 6') for image in images])
        
        print("\n--- OCR Text Extraction Complete. Now Parsing... ---\n")
        
        parsed_data = parse_ocr_text(full_text)

        if not parsed_data:
            print("--- Could not parse any structured payment data. ---")
            return

        print("--- Parsed Payment Data ---")
        
        # Sorting is complex with 'Pending' dates, handle it carefully
        from datetime import datetime
        def date_key(p):
            if p['date'] == 'Pending': return datetime.max
            try:
                return datetime.strptime(p['date'], '%b %d, %Y')
            except ValueError:
                return datetime.min # Or some other default for malformed dates
        
        sorted_data = sorted(parsed_data, key=date_key, reverse=True)

        # Pretty print the output
        header = f"{'Date':<12} | {'Amount':>12} | {'Full Description'}"
        print(header)
        print("-" * (len(header) + 20)) # Dynamic separator line

        for payment in sorted_data:
            # Wrap the long description text to a max width of 80 characters
            wrapped_desc = textwrap.wrap(payment['description'], width=80)
            
            # Print the first line of the description aligned with the headers
            print(f"{payment['date']:<12} | ${payment['amount']:>10,.2f} | {wrapped_desc[0] if wrapped_desc else ''}")
            
            # Print subsequent lines of the wrapped description, indented for clarity
            if len(wrapped_desc) > 1:
                for line in wrapped_desc[1:]:
                    print(f"{'':<12} | {'':>12} | {line}")

    except Exception as e:
        print(f"\n--- An error occurred during the OCR/parsing process ---")
        print(e)

if __name__ == "__main__":
    process_pdf_with_ocr(PDF_FILE)
