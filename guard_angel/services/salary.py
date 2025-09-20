from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Iterable
@dataclass
class SalaryRow:
    date: str
    amount: Decimal
    lumper: Decimal = Decimal("0")
def _to_dec(x) -> Decimal:
    if x in (None, ""): return Decimal("0")
    try:
        return Decimal(str(x).replace(",", "").replace("$", "").strip())
    except InvalidOperation:
        return Decimal("0")
# TODO: wire to your sheets later
def fetch_salary_rows(driver: str, start_date: str, end_date: str) -> Iterable[SalaryRow]:
    return []
def compute_salary_preview(driver: str, start_date: str, end_date: str) -> str:
    rows = list(fetch_salary_rows(driver, start_date, end_date))
    if not rows:
        return (f"🧾 Salary preview\nDriver: {driver}\nPeriod: {start_date} → {end_date}\n— No rows found.")
    gross = sum((r.amount for r in rows), Decimal("0"))
    lump  = sum((r.lumper for r in rows), Decimal("0"))
    net   = gross - lump
    lines = [
        "🧾 Salary preview",
        f"Driver: {driver}",
        f"Period: {start_date} → {end_date}",
        f"— Loads: {len(rows)}",
        f"— Gross: ${gross:.2f}",
        f"— Lumpers: ${lump:.2f}",
        f"— Net: ${net:.2f}",
        "", "Details:",
    ]
    for r in rows:
        suffix = f" (lumper ${r.lumper:.2f})" if r.lumper else ""
        lines.append(f"• {r.date}: ${r.amount:.2f}{suffix}")
    return "\n".join(lines)
