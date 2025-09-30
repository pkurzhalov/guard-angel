from fpdf import FPDF
from typing import Optional, Iterable

def build_invoice_pdf(org, invoice, out_path: str):
    pdf = FPDF()
    pdf.add_page()
    # Org header
    pdf.set_font("Arial", "B", 16); pdf.cell(0, 10, org.name or "Your Company", ln=1)
    pdf.set_font("Arial", "", 10)
    if org.address: pdf.multi_cell(0, 5, org.address)
    if org.email:   pdf.cell(0, 5, f"Email: {org.email}", ln=1)
    if org.phone:   pdf.cell(0, 5, f"Phone: {org.phone}", ln=1)
    if org.vat_id:  pdf.cell(0, 5, f"VAT: {org.vat_id}", ln=1)
    if org.bank:    pdf.multi_cell(0, 5, f"Bank: {org.bank}")
    pdf.ln(5)

    # Invoice header
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 8, f"INVOICE {invoice['invoice_no']}", ln=1)
    pdf.set_font("Arial", "", 11)
    pdf.cell(0, 6, f"Invoice Date: {invoice['invoice_date']}", ln=1)
    pdf.cell(0, 6, f"Due Date: {invoice['due_date']}", ln=1)
    if invoice.get("reference"):
        pdf.cell(0, 6, f"Reference: {invoice['reference']}", ln=1)
    pdf.ln(3)

    # Bill-to
    pdf.set_font("Arial", "B", 12); pdf.cell(0, 6, "Bill To:", ln=1)
    pdf.set_font("Arial", "", 11)
    pdf.cell(0, 6, invoice["bill_to_name"], ln=1)
    pdf.multi_cell(0, 5, invoice["bill_to_address"])
    if invoice.get("bill_to_email"):
        pdf.cell(0, 6, f"Email: {invoice['bill_to_email']}", ln=1)
    pdf.ln(3)

    # Simple line items table
    pdf.set_font("Arial", "B", 11)
    pdf.cell(110, 8, "Description", border=1)
    pdf.cell(25, 8, "Qty", border=1, align="R")
    pdf.cell(25, 8, "Unit", border=1, align="R")
    pdf.cell(30, 8, "Total", border=1, ln=1, align="R")
    pdf.set_font("Arial", "", 11)
    for it in invoice["items"]:
        pdf.cell(110, 8, it["description"], border=1)
        pdf.cell(25, 8, f"{it['quantity']}", border=1, align="R")
        pdf.cell(25, 8, f"{invoice['currency']} {it['unit_price']}", border=1, align="R")
        pdf.cell(30, 8, f"{invoice['currency']} {it['line_total']}", border=1, ln=1, align="R")

    # Totals
    pdf.set_font("Arial", "B", 11)
    pdf.cell(160, 8, "Total", border=1)
    pdf.cell(30, 8, f"{invoice['currency']} {invoice['total']}", border=1, ln=1, align="R")

    if invoice.get("notes"):
        pdf.ln(6); pdf.set_font("Arial", "", 10)
        pdf.multi_cell(0, 5, f"Notes: {invoice['notes']}")

    pdf.output(out_path)

def merge_pdfs(paths: Iterable[str], out_path: str):
    from PyPDF2 import PdfMerger
    merger = PdfMerger()
    for p in paths: merger.append(p)
    merger.write(out_path); merger.close()
