from datetime import datetime, date
FMTS = ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y")
def parse_date_flexible(s: str) -> date:
    s = s.strip()
    for f in FMTS:
        try: return datetime.strptime(s, f).date()
        except ValueError: pass
    raise ValueError(f"Unsupported date format: {s}")
