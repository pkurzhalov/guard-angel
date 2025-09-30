from dataclasses import dataclass
from decimal import Decimal
from datetime import date, timedelta
import os, re, io, tempfile, shutil

from .org_config import get_org
from .pdf_tools import build_invoice_pdf, merge_pdfs
from .auth import drive_service as dr
from .auth import spreadsheet_service as sh
from ..config import settings

# Column mapping (0-based) from env, with sensible defaults matching your legacy
COL = lambda name, default: int(os.getenv(name, default))
INV_COLS = {
    "PU_DATE":      COL("INV_COL_PU_DATE", "0"),
    "DEL_DATE":     COL("INV_COL_DEL_DATE","2"),
    "PU_CITY":      COL("INV_COL_PU_CITY","4"),
    "DEL_CITY":     COL("INV_COL_DEL_CITY","5"),
    "BROKER":       COL("INV_COL_BROKER","6"),
    "CONFIRM_LINK": COL("INV_COL_CONFIRM_LINK","8"),
    "GROSS":        COL("INV_COL_GROSS","9"),
    "POD_LINK":     COL("INV_COL_POD_LINK","13"),
    "INVOICE_NO":   COL("INV_COL_INVOICE_NO","18"),
    "INVOICE_URL":  COL("INV_COL_INVOICE_URL","17"),
}

def _extract_drive_id(link: str) -> str:
    # works for .../d/<id>/view and shared formats
    m = re.search(r'/d/([A-Za-z0-9_-]+)/', link)
    if m: return m.group(1)
    # fallback for id= param
    m = re.search(r'[?&]id=([A-Za-z0-9_-]+)', link)
    if m: return m.group(1)
    raise ValueError(f"Cannot parse file id from: {link}")

def download_drive_file(file_id: str, dest_path: str):
    req = dr.files().get_media(fileId=file_id)
    with open(dest_path, "wb") as f:
        downloader = __import__("googleapiclient.http", fromlist=['MediaIoBaseDownload']).http.MediaIoBaseDownload(f, req)
        done = False
        while not done:
            status, done = downloader.next_chunk()

def upload_drive_file(local_path: str, parent_folder_id: str|None) -> str|None:
    if not parent_folder_id: return None
    file_metadata = {"name": os.path.basename(local_path), "parents": [parent_folder_id]}
    media = __import__("googleapiclient.http", fromlist=['MediaFileUpload']).http.MediaFileUpload(local_path, mimetype="application/pdf")
    file = dr.files().create(body=file_metadata, media_body=media, fields="id, webViewLink").execute()
    return file.get("webViewLink")

def load_row(driver: str, row_idx_1based: int):
    rng = f"{driver}!A{row_idx_1based}:Z{row_idx_1based}"
    resp = sh.spreadsheets().values().get(spreadsheetId=settings.spreadsheet_id, range=rng).execute()
    vals = resp.get("values", [[]])
    return vals[0] if vals else []

def make_invoice_payload(row: list[str], currency="USD"):
    g = INV_COLS
    pu_date  = row[g["PU_DATE"]]      if len(row)>g["PU_DATE"] else ""
    del_date = row[g["DEL_DATE"]]     if len(row)>g["DEL_DATE"] else ""
    pu_city  = row[g["PU_CITY"]]      if len(row)>g["PU_CITY"] else ""
    del_city = row[g["DEL_CITY"]]     if len(row)>g["DEL_CITY"] else ""
    broker   = row[g["BROKER"]]       if len(row)>g["BROKER"] else ""
    gross    = row[g["GROSS"]]        if len(row)>g["GROSS"] else "0"
    inv_no   = row[g["INVOICE_NO"]]   if len(row)>g["INVOICE_NO"] else ""
    confirm  = row[g["CONFIRM_LINK"]] if len(row)>g["CONFIRM_LINK"] else ""
    pod      = row[g["POD_LINK"]]     if len(row)>g["POD_LINK"] else ""

    # Minimal single-line item: "Freight PU->DEL"
    desc = f"Freight {pu_city} ({pu_date}) → {del_city} ({del_date}) | Broker: {broker}"
    total = Decimal(str(gross or "0")).quantize(Decimal("0.01"))
    item = {"description": desc, "quantity": 1, "unit_price": total, "line_total": total}

    payload = {
        "bill_to_name": broker or "Client",
        "bill_to_address": "",         # can be filled via /settings later or from another column
        "bill_to_email": None,
        "invoice_no": inv_no or "INV-NA",
        "invoice_date": str(date.today()),
        "due_date": str(date.today() + timedelta(days=int(os.getenv("INVOICE_DEFAULT_NET","14")))),
        "reference": None,
        "notes": None,
        "currency": currency,
        "items": [item],
        "total": f"{total:.2f}",
        "links": {
            "confirm": confirm,
            "pod": pod
        }
    }
    return payload

def generate_and_merge_invoice(driver: str, row_idx_1based: int, out_dir: str, currency: str):
    row = load_row(driver, row_idx_1based)
    inv  = make_invoice_payload(row, currency=currency)
    org  = get_org()
    os.makedirs(out_dir, exist_ok=True)

    tmp = tempfile.mkdtemp(prefix="ga_inv_")
    try:
        inv_pdf = os.path.join(tmp, f"Invoice_{inv['invoice_no']}.pdf")
        build_invoice_pdf(org, inv, inv_pdf)

        # Download RC + POD
        parts = [inv_pdf]
        for key, fname in [("confirm","RC_for_invoice.pdf"), ("pod","POD_for_invoice.pdf")]:
            link = inv["links"].get(key)
            if link:
                try:
                    fid = _extract_drive_id(link)
                    local = os.path.join(tmp, fname)
                    download_drive_file(fid, local)
                    parts.append(local)
                except Exception as e:
                    # continue without the missing part
                    pass

        out_path = os.path.join(out_dir, f"Invoice_{inv['invoice_no']}_MC_1294648.pdf")
        merge_pdfs(parts, out_path)
        return out_path
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
