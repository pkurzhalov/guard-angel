import os
import shutil
import time
import io
import ssl
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
from googleapiclient.errors import HttpError
from .auth import spreadsheet_service as sh, drive_service as dr
from ..config import settings

SHEET_ID = settings.spreadsheet_id

def get_current_cell(driver_name: str, column: str = "A") -> int:
    range_name = f"{driver_name}!{column}:{column}"
    result = sh.spreadsheets().values().get(spreadsheetId=SHEET_ID, range=range_name).execute()
    return len(result.get("values", []))

def get_id_from_link(link):
    if not link: return None
    start = "/d/"
    try:
        if "/view" in link: return link[link.index(start)+3:link.index("/view")]
        return link[link.index(start)+3:]
    except (ValueError, TypeError): return None

def update_cell(driver, cell, letter, value):
    rangeName = f"{driver}!{letter}{cell}"; body = {'values': [[value]]}
    sh.spreadsheets().values().update(spreadsheetId=SHEET_ID, range=rangeName, valueInputOption='RAW', body=body).execute()

def download_file(file_id, name):
    if not file_id: raise ValueError("File ID missing")
    request = dr.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done: status, done = downloader.next_chunk()
    fh.seek(0)
    os.makedirs("./files_cash", exist_ok=True)
    with open(f'./files_cash/{name}', 'wb') as f: shutil.copyfileobj(fh, f)

def _perform_upload(local_path: str):
    file_metadata = {'name': os.path.basename(local_path), 'parents': [settings.drive_folder_id]}
    media = MediaFileUpload(local_path, mimetype='application/pdf')
    file = dr.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
    dr.permissions().create(fileId=file.get('id'), body={'type': 'anyone', 'role': 'reader'}).execute()
    return file

def upload_pod(local_path: str, driver: str, cell: int):
    file = _perform_upload(local_path)
    update_cell(driver, cell, 'N', file.get('webViewLink'))

def upload_file(file_name, driver_name, cell, column: str):
    file = _perform_upload(file_name)
    update_cell(driver_name, cell, column, file.get('webViewLink'))
