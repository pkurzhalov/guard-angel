#!/usr/bin/python3

# auth.py This file reads credentials keys that we downloaded from Google dashboard
# and creates1️ (spreadsheet_service) and (drive_service) that we will be using to access 
# google sheets and google drive later 

from __future__ import print_function
from googleapiclient.discovery import build 
from google.oauth2 import service_account
SCOPES = [
'https://www.googleapis.com/auth/spreadsheets',
'https://www.googleapis.com/auth/drive'
]
credentials = service_account.Credentials.from_service_account_file('credentials.json', scopes=SCOPES)
spreadsheet_service = build('sheets', 'v4', credentials=credentials)
drive_service = build('drive', 'v3', credentials=credentials)
