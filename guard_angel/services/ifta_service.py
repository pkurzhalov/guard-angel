import os
import re
import pandas as pd
import requests
import geopandas as gpd
from collections import defaultdict
from math import radians, sin, cos, atan2, sqrt
from shapely.geometry import LineString, MultiLineString
from PyPDF2 import PdfReader
from geopy.geocoders import Nominatim
from telegram import Update
from telegram.ext import ContextTypes

from . import sheets
from ..config import settings
from .mileage_calculator import mileage_browser

# Add this helper function
def create_progress_bar(current: int, total: int, length: int = 20) -> str:
    """Creates a text-based progress bar string."""
    percent = current / total
    filled_length = int(length * percent)
    bar = '█' * filled_length + '─' * (length - filled_length)
    return f"Processing routes... {current}/{total}\n`[{bar}] {percent:.0%}`"

# --- FUEL PARSING LOGIC (This part is correct) ---
def parse_fuel_statement(pdf_path: str) -> str:
    try:
        pdf_reader = PdfReader(pdf_path)
        full_text = "".join(page.extract_text() + "\n" for page in pdf_reader.pages)
        lines = full_text.split('\n')
        transactions = []
        current_state = "XX"
        parsing_active = True
        VALID_STATES = ["AL", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY"]
        state_pattern = re.compile(r'.*?([A-Z]{2})\s*[\d\s.]*?(?:ULSD|ULSR|FUEL|RFR)')
        quantity_pattern = re.compile(r'\s(0\.\d{2,3}?)(\d*\.\d{2})')
        for line in lines:
            if "Amount Quantity Avg PPU" in line or line.startswith("Total Fuel"):
                parsing_active = False; continue
            if not parsing_active: continue
            state_match = state_pattern.search(line)
            if state_match and state_match.group(1) in VALID_STATES:
                current_state = state_match.group(1)
            if re.search(r'(ULSD|ULSR|FUEL|RFR)', line):
                qty_match = quantity_pattern.search(line)
                if qty_match:
                    try:
                        quantity = float(qty_match.group(2))
                        if quantity > 0: transactions.append({'State': current_state, 'Qty': quantity})
                    except (ValueError, TypeError): continue
        if not transactions: return "Parsing complete. No transactions were found."
        df = pd.DataFrame(transactions)
        state_totals = df.groupby('State')['Qty'].sum().sort_index()
        calculated_total = df['Qty'].sum()
        result_text = "⛽ **Gallons per State:**\n------------------\n"
        for state, total in state_totals.items():
            result_text += f"**{state}:** {total:.2f}\n"
        result_text += f"------------------\n**Total Gallons:** {calculated_total:.2f}\n"
        return result_text
    except Exception as e:
        return f"❌ An unexpected error occurred during fuel parsing: {e}"

# --- MILEAGE CALCULATION LOGIC (Replicated from your state_miles.py) ---
OSRM_URL = "https://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=full&geometries=geojson"
STATE_ABBR = {"Alabama":"AL","Alaska":"AK","Arizona":"AZ","Arkansas":"AR","California":"CA","Colorado":"CO","Connecticut":"CT","Delaware":"DE","Florida":"FL","Georgia":"GA","Hawaii":"HI","Idaho":"ID","Illinois":"IL","Indiana":"IN","Iowa":"IA","Kansas":"KS","Kentucky":"KY","Louisiana":"LA","Maine":"ME","Maryland":"MD","Massachusetts":"MA","Michigan":"MI","Minnesota":"MN","Mississippi":"MS","Missouri":"MO","Montana":"MT","Nebraska":"NE","Nevada":"NV","New Hampshire":"NH","New Jersey":"NJ","New Mexico":"NM","New York":"NY","North Carolina":"NC","North Dakota":"ND","Ohio":"OH","Oklahoma":"OK","Oregon":"OR","Pennsylvania":"PA","Rhode Island":"RI","South Carolina":"SC","South Dakota":"SD","Tennessee":"TN","Texas":"TX","Utah":"UT","Vermont":"VT","Virginia":"VA","Washington":"WA","West Virginia":"WV","Wisconsin":"WI","Wyoming":"WY"}

def _haversine_mi(p1, p2):
    R = 3958.8; lon1, lat1, lon2, lat2 = map(radians, (*p1, *p2))
    dlon, dlat = lon2 - lon1, lat2 - lat1
    a = sin(dlat / 2)**2 + cos(lat1)*cos(lat2)*sin(dlon / 2)**2
    return 2 * R * atan2(sqrt(a), sqrt(1 - a))

def _calculate_state_miles_for_route(origin: str, dest: str, states_gdf) -> dict[str, float]:
    from geopy.geocoders import Nominatim
    geocoder = Nominatim(user_agent="guard_angel_ifta", timeout=10)
    try:
        if origin.strip().lower() == dest.strip().lower(): return {}

        google_total = mileage_browser.get_miles(origin, dest)
        if google_total is None: google_total = 0

        state1_abbr = origin.split(',')[-1].strip()
        state2_abbr = dest.split(',')[-1].strip()

        if state1_abbr == state2_abbr:
            return {state1_abbr: float(google_total)}

        orig_loc = geocoder.geocode(f"{origin}, USA")
        dest_loc = geocoder.geocode(f"{dest}, USA")
        if not orig_loc or not dest_loc: return {}

        url = OSRM_URL.format(lon1=orig_loc.longitude, lat1=orig_loc.latitude, lon2=dest_loc.longitude, lat2=dest_loc.latitude)
        data = requests.get(url, timeout=20).json()
        line = LineString(data["routes"][0]["geometry"]["coordinates"])

        per_state_miles = {}
        for _, row in states_gdf.iterrows():
            inter = line.intersection(row.geometry)
            if inter.is_empty: continue
            segs = list(inter.geoms) if isinstance(inter, MultiLineString) else [inter]
            length = sum(_haversine_mi(p, q) for seg in segs for p, q in zip(seg.coords[:-1], seg.coords[1:]))
            if length:
                abbr = STATE_ABBR.get(row["name"], row["name"])
                per_state_miles[abbr] = per_state_miles.get(abbr, 0) + length

        geometry_total = sum(per_state_miles.values())
        if geometry_total > 0 and google_total > geometry_total:
            coeff = google_total / geometry_total
            return {abbr: mi * coeff for abbr, mi in per_state_miles.items()}
        else:
            return per_state_miles
    except Exception as e:
        print(f"Error calculating state miles for {origin}->{dest}: {e}")
        return {}

# Make sure to add the helper function create_progress_bar from above!

async def calculate_quarterly_miles(driver: str, quarter: int, update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    # This function must now be async
    try:
        routes = sheets.get_start_finish_for_ifta(quarter, driver)
        if not routes: return f"No routes found for driver {driver}, Q{quarter}."

        total_routes = len(routes)
        states_gdf = gpd.read_file(settings.states_geojson_path)
        grand_total = defaultdict(float)

        # This will hold the message we are editing
        q = update.callback_query

        # Loop through the routes and update the progress bar
        for i, (origin, destination) in enumerate(routes):
            # Only edit the message every 5 routes or on the first/last to avoid hitting API limits
            if i % 5 == 0 or i == 0 or i == total_routes - 1:
                progress_text = create_progress_bar(current=i, total=total_routes)
                try:
                    # Edit the message with the new progress bar
                    await q.edit_message_text(progress_text, parse_mode="Markdown")
                except Exception as e:
                    # Ignore minor errors like "message is not modified"
                    print(f"Could not edit message: {e}")

            print(f"Processing route {i+1}/{total_routes}: {origin} -> {destination}")
            per_route = _calculate_state_miles_for_route(origin, destination, states_gdf)
            for st, mi in per_route.items():
                grand_total[st] += mi

        if not grand_total: return "Could not calculate any mileage."

        result_text = f"🚚 **IFTA Miles for {driver} (Q{quarter}):**\n------------------\n"
        total = 0
        for state, miles in sorted(grand_total.items(), key=lambda item: item[1], reverse=True):
            result_text += f"**{state}:** {miles:,.0f} mi\n"
            total += miles
        result_text += f"------------------\n**Total Miles:** {total:,.0f}\n"
        return result_text
    except Exception as e:
        return f"❌ An unexpected error occurred during mileage calculation: {e}"
