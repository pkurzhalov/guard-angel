from datetime import datetime
from .core_sheets import sh, SHEET_ID, get_current_cell

def get_start_finish_for_ifta(quarter: int, driver: str) -> list:
    # This is the full function body from your original file
    now = datetime.now(); year = now.strftime("%Y")
    if quarter == 1: start_date_str = f'12/31/{int(year)-1}'; end_date_str = f'04/1/{year}'
    elif quarter == 2: start_date_str = f'03/31/{year}'; end_date_str = f'07/1/{year}'
    elif quarter == 3: start_date_str = f'06/30/{year}'; end_date_str = f'10/1/{year}'
    elif quarter == 4: start_date_str = f'09/30/{year}'; end_date_str = f'01/1/{int(year)+1}'
    else: return []

    start_date = datetime.strptime(start_date_str, "%m/%d/%Y")
    end_date = datetime.strptime(end_date_str, "%m/%d/%Y")
    
    last_row = get_current_cell(driver)
    ranges = [f"{driver}!C2:C{last_row}", f"{driver}!E2:E{last_row}", f"{driver}!F2:F{last_row}"]
    result = sh.spreadsheets().values().batchGet(spreadsheetId=SHEET_ID, ranges=ranges).execute()
    
    dates = result['valueRanges'][0].get('values', [])
    pus = result['valueRanges'][1].get('values', [])
    dels = result['valueRanges'][2].get('values', [])

    trip_segments = []
    for i in range(len(dates)):
        try:
            date_str = dates[i][0]; pu_str = pus[i][0]; del_str = dels[i][0]
            date_obj = datetime.strptime(date_str, "%m/%d/%Y")
            if start_date < date_obj < end_date:
                pu_list = [p.strip() for p in pu_str.split(';')]
                del_list = [d.strip() for d in del_str.split(';')]
                for j in range(len(pu_list) - 1): trip_segments.append((pu_list[j], pu_list[j+1]))
                trip_segments.append((pu_list[-1], del_list[0]))
                for j in range(len(del_list) - 1): trip_segments.append((del_list[j], del_list[j+1]))
                if (i + 1) < len(pus) and pus[i+1]:
                    next_pu = pus[i+1][0].split(';')[0].strip()
                    trip_segments.append((del_list[-1], next_pu))
        except (ValueError, IndexError):
            continue
    return trip_segments
