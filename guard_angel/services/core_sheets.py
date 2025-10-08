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

def clear_row_background(driver_name: str, row: int):
    """Resets the background color for specified ranges in a given row."""
    try:
        # First, we need to get the sheetId for the given driver name
        spreadsheet_metadata = sh.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
        sheets = spreadsheet_metadata.get('sheets', [])
        sheet_id = None
        for s in sheets:
            if s.get('properties', {}).get('title', '') == driver_name:
                sheet_id = s.get('properties', {}).get('sheetId')
                break

        if sheet_id is None:
            print(f"Could not find sheetId for driver: {driver_name}")
            return

        # Define the ranges to be cleared (row index is 0-based, so subtract 1)
        row_index = row - 1
        requests = [
            {
                "updateCells": {
                    "range": {"sheetId": sheet_id, "startRowIndex": row_index, "endRowIndex": row, "startColumnIndex": 0, "endColumnIndex": 6}, # A:F
                    "rows": [{"values": [{"userEnteredFormat": {"backgroundColor": {"red": 1, "green": 1, "blue": 1}}}] * 6}],
                    "fields": "userEnteredFormat.backgroundColor"
                }
            },
            {
                "updateCells": {
                    "range": {"sheetId": sheet_id, "startRowIndex": row_index, "endRowIndex": row, "startColumnIndex": 7, "endColumnIndex": 17}, # H:Q
                    "rows": [{"values": [{"userEnteredFormat": {"backgroundColor": {"red": 1, "green": 1, "blue": 1}}}] * 10}],
                    "fields": "userEnteredFormat.backgroundColor"
                }
            },
            # --- THIS IS THE NEW BLOCK FOR S and T ---
            {
                "updateCells": {
                    "range": {"sheetId": sheet_id, "startRowIndex": row_index, "endRowIndex": row, "startColumnIndex": 18, "endColumnIndex": 20}, # S:T
                    "rows": [{"values": [{"userEnteredFormat": {"backgroundColor": {"red": 1, "green": 1, "blue": 1}}}] * 2}],
                    "fields": "userEnteredFormat.backgroundColor"
                }
            },
            # --- END OF NEW BLOCK ---
            {
                "updateCells": {
                    "range": {"sheetId": sheet_id, "startRowIndex": row_index, "endRowIndex": row, "startColumnIndex": 21, "endColumnIndex": 27}, # V:AA
                    "rows": [{"values": [{"userEnteredFormat": {"backgroundColor": {"red": 1, "green": 1, "blue": 1}}}] * 6}],
                    "fields": "userEnteredFormat.backgroundColor"
                }
            }
        ]

        body = {"requests": requests}
        sh.spreadsheets().batchUpdate(spreadsheetId=SHEET_ID, body=body).execute()
        print(f"Successfully cleared background for row {row} in sheet {driver_name}")

    except HttpError as e:
        print(f"Error clearing background color: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")


def highlight_broker_cell(driver_name: str, row: int):
    """Sets the background color of the broker cell (column G) to green."""
    try:
        # Get the sheetId for the given driver name (reusing logic from other functions)
        spreadsheet_metadata = sh.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
        sheets_props = spreadsheet_metadata.get('sheets', [])
        sheet_id = None
        for s in sheets_props:
            if s.get('properties', {}).get('title', '') == driver_name:
                sheet_id = s.get('properties', {}).get('sheetId')
                break

        if sheet_id is None:
            print(f"Could not find sheetId for driver to highlight broker: {driver_name}")
            return

        # Define the request to format just cell G in the specified row
        requests = [
            {
                "updateCells": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": row - 1, # 0-based index
                        "endRowIndex": row,
                        "startColumnIndex": 6,  # Column G
                        "endColumnIndex": 7
                    },
                    "rows": [{
                        "values": [{
                            "userEnteredFormat": {
                                "backgroundColor": {"red": 0.8, "green": 1, "blue": 0.8} # Light Green
                            }
                        }]
                    }],
                    "fields": "userEnteredFormat.backgroundColor"
                }
            }
        ]

        body = {"requests": requests}
        sh.spreadsheets().batchUpdate(spreadsheetId=SHEET_ID, body=body).execute()
        print(f"Successfully highlighted broker in row {row} for {driver_name}")

    except HttpError as e:
        print(f"Error highlighting broker cell: {e}")
    except Exception as e:
        print(f"An unexpected error occurred during broker highlight: {e}")


def add_bottom_border(driver_name: str, row: int):
    """Adds a solid bottom border to a given row from column A to AA."""
    try:
        # Get the sheetId for the given driver name
        spreadsheet_metadata = sh.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
        sheets_props = spreadsheet_metadata.get('sheets', [])
        sheet_id = None
        for s in sheets_props:
            if s.get('properties', {}).get('title', '') == driver_name:
                sheet_id = s.get('properties', {}).get('sheetId')
                break

        if sheet_id is None:
            print(f"Could not find sheetId for driver to add border: {driver_name}")
            return

        # Define the request to update the bottom border of the specified range
        requests = [
            {
                "updateBorders": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": row - 1, # The API uses a 0-based index
                        "endRowIndex": row,
                        "startColumnIndex": 0,  # Column A
                        "endColumnIndex": 27   # Through Column AA
                    },
                    "bottom": {
                        "style": "SOLID",
                        "width": 2, # This creates a solid, medium-thickness line
                        "color": {"red": 0.0, "green": 0.0, "blue": 0.0} # Black
                    }
                }
            }
        ]

        body = {"requests": requests}
        sh.spreadsheets().batchUpdate(spreadsheetId=SHEET_ID, body=body).execute()
        print(f"Successfully added bottom border to row {row} for {driver_name}")

    except Exception as e:
        print(f"An error occurred while adding border: {e}")
