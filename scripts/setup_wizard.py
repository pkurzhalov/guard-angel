from __future__ import annotations
import os, sys
from pathlib import Path

# Ensure project root on sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in map(str, sys.path):
    sys.path.insert(0, str(ROOT))

from guard_angel.services import org_config

def prompt(label, default=""):
    v = input(f"{label} [{default}]: ").strip()
    return v or default

def prompt_list(label, example="Yura, Walter, Denis"):
    while True:
        val = input(f"{label}\nExample:  {example}\n> ").strip()
        if val:
            return [t.strip() for t in val.split(",") if t.strip()]
        print("Please provide at least one item.\n")

def mask_tail(x, keep=4):
    x = (x or "").strip()
    return ("*"*(max(0, len(x)-keep)) + x[-keep:]) if x else ""

def main():
    print("== Guard Angel Setup Wizard ==")
    print("These values are stored locally in .cache/org_config.json (ignored by git).")

    # --- Org ---
    print("\n-- Your Organization (used on statements) --")
    org = org_config.get_org()
    name = prompt("Company name", org.get("name",""))
    street = prompt("Street", org.get("street",""))
    csz = prompt("City, State ZIP", org.get("city_state_zip",""))
    bank = prompt("Bank name (optional)", org.get("bank_name",""))
    routing = prompt("Routing (optional)", org.get("routing_number",""))
    acct = prompt("Account # (optional)", org.get("account_number",""))

    org_config.set_org(
        name=name, street=street, city_state_zip=csz,
        bank_name=bank, routing_number=routing, account_number=acct
    )

    # --- Drivers ---
    print("\n-- Drivers (sheet tab -> driver company) --")
    print("Enter the NAMES of the sheet tabs for drivers, comma-separated.")
    print("⚠️  Do NOT paste the Spreadsheet ID here. We already read it from .env (SPREADSHEET_ID).")
    tabs = prompt_list("Driver sheet tabs", "Yura, Walter, Denis, Javier, Nestor")

    for t in tabs:
        cur = org_config.get_driver(t)
        dname = prompt(f"[{t}] driver company name", cur.get("company_name",""))
        daddr = prompt(f"[{t}] driver company address (optional)", cur.get("address",""))
        org_config.set_driver(t, company_name=dname, address=daddr)

    cfg = org_config.load()
    org = cfg["org"]
    print("\nSaved to .cache/org_config.json\n")
    print("Summary:")
    print(f"  Org: {org.get('name','')}")
    print(f"       {org.get('street','')}")
    print(f"       {org.get('city_state_zip','')}")
    if org.get("bank_name") or org.get("routing_number") or org.get("account_number"):
        print(f"  Bank: {org.get('bank_name','')}  Routing: {mask_tail(org.get('routing_number'))}  Acct: {mask_tail(org.get('account_number'))}")
    print("  Drivers:")
    for k, v in (cfg.get("drivers") or {}).items():
        print(f"    - {k}: {v.get('company_name','')}  {v.get('address','')}")
    print("\nDone.")
