"""
backfill_ca_cpi.py — Fetch 12+ months of Canadian CPI from StatCan
"""

import requests
import json
from pathlib import Path
import datetime as dt

STATCAN_VECTOR = 41690973
HISTORY_FILE = Path("inflation_history.json")

def fetch_statcan_history(vector_id, months=24):
    """Fetch 24 months of StatCan data."""
    r = requests.post(
        "https://www150.statcan.gc.ca/t1/wds/rest/getDataFromVectorsAndLatestNPeriods",
        json=[{"vectorId": vector_id, "latestN": months}],
        timeout=10,
        headers={"Content-Type": "application/json"},
    )
    r.raise_for_status()
    body = r.json()
    
    if not body or body[0].get("status") != "SUCCESS":
        return []
    
    obj = body[0]["object"]
    return obj.get("vectorDataPoint", [])

# Fetch 24 months
pts = fetch_statcan_history(STATCAN_VECTOR, 24)
print(f"Fetched {len(pts)} Canadian CPI observations from StatCan")

# Load history
with open(HISTORY_FILE) as f:
    history = json.load(f)

# Add Canadian CPI observations
existing_keys = {(o["series_key"], o["obs_date"]) for o in history["observations"]}
added = 0
now = dt.datetime.utcnow().isoformat() + "Z"

for pt in pts:
    # StatCan refPer format: "2026-06" for June 2026, convert to "2026-06-01"
    ref_per = pt["refPer"]
    if len(ref_per) == 7:  # "2026-06"
        obs_date = ref_per + "-01"
    else:
        obs_date = ref_per
    
    value = float(pt["value"])
    key = ("ca.inflation.cpi", obs_date)
    
    if key not in existing_keys:
        history["observations"].append({
            "series_key": "ca.inflation.cpi",
            "obs_date": obs_date,
            "value": value,
            "fetched_at": now,
        })
        existing_keys.add(key)
        added += 1
        print(f"  {obs_date}: {value}")

# Sort
history["observations"].sort(key=lambda o: (o["series_key"], o["obs_date"]))

# Save
with open(HISTORY_FILE, "w") as f:
    json.dump(history, f, indent=2)

print(f"\n✓ Added {added} Canadian CPI observations")
