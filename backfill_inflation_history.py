"""
backfill_inflation_history.py — Fetch 12+ months of historical inflation data
"""

import os
import sqlite3
import requests
import datetime as dt
from typing import Optional

DB = "market.db"
FRED_API_KEY = os.environ.get("FRED_API_KEY")

FRED_INFLATION = [
    ("us.inflation.cpi", "CPIAUCSL"),
    ("us.inflation.cpi.core", "CPILFESL"),
    ("us.inflation.pce", "PCEPI"),
    ("us.inflation.pce.core", "PCEPILFE"),
]

def fetch_fred_series(series_id: str, api_key: str) -> Optional[dict]:
    """Fetch full historical series from FRED."""
    url = f"https://api.stlouisfed.org/fred/series/observations"
    
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
    }
    
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        
        if "observations" in data:
            return data["observations"]
        return None
    except Exception as e:
        print(f"  ERROR fetching {series_id}: {e}")
        return None

def fetch_statcan_cpi() -> Optional[dict]:
    """Fetch historical CPI from StatCan."""
    url = "https://www150.statcan.gc.ca/t1/wds/rest/getDataFromVectorsAndLatestNPeriods"
    
    headers = {"Content-Type": "application/json"}
    body = [{"vectorId": 41690973, "latestN": 150}]
    
    try:
        r = requests.post(url, json=body, headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json()
        
        observations = {}
        if data and len(data) > 0 and data[0].get("status") == "SUCCESS":
            obj = data[0].get("object", {})
            for pt in obj.get("vectorDataPoint", []):
                ref_date = pt.get("refPer")
                value = pt.get("value")
                if ref_date and value:
                    try:
                        # Convert YYYYMM to YYYY-MM-01
                        year = ref_date[:4]
                        month = ref_date[4:6]
                        formatted_date = f"{year}-{month}-01"
                        observations[formatted_date] = float(value)
                    except:
                        pass
        
        return observations if observations else None
    except Exception as e:
        print(f"  ERROR fetching StatCan CPI: {e}")
        return None

def store_observations(conn, series_key: str, observations: dict):
    """Insert observations into database."""
    cursor = conn.cursor()
    now = dt.datetime.utcnow().isoformat()
    
    count = 0
    for obs_date, value in observations.items():
        try:
            cursor.execute("""
                INSERT OR IGNORE INTO observations
                (series_key, obs_date, value, fetched_at)
                VALUES (?, ?, ?, ?)
            """, (series_key, obs_date, value, now))
            count += 1
        except Exception as e:
            print(f"  ERROR storing {series_key} {obs_date}: {e}")
    
    conn.commit()
    return count

def main():
    if not FRED_API_KEY:
        print("ERROR: FRED_API_KEY not set")
        return
    
    conn = sqlite3.connect(DB)
    
    print("Backfilling inflation history...\n")
    
    # FRED inflation series
    for series_key, fred_id in FRED_INFLATION:
        print(f"Fetching {series_key} ({fred_id})...")
        obs = fetch_fred_series(fred_id, FRED_API_KEY)
        
        if obs:
            observations = {}
            for o in obs:
                date = o.get("date")
                value = o.get("value")
                if date and value and value != ".":
                    try:
                        observations[date] = float(value)
                    except:
                        pass
            
            count = store_observations(conn, series_key, observations)
            print(f"  ✓ Stored {count} observations")
        else:
            print(f"  ✗ No data")
    
    # StatCan CPI
    print(f"Fetching ca.inflation.cpi...")
    obs = fetch_statcan_cpi()
    
    if obs:
        count = store_observations(conn, "ca.inflation.cpi", obs)
        print(f"  ✓ Stored {count} observations")
    else:
        print(f"  ✗ No data")
    
    conn.close()
    print("\n✓ Backfill complete")

if __name__ == "__main__":
    main()
