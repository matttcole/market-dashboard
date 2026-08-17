"""
ingest_fred.py — Load FRED P1 series into SQLite.

Usage:
    export FRED_API_KEY=f3be1e2ebf4f9bbbb122cfd28ee049a5
    python3 ingest_fred.py
"""

import sqlite3
import requests
import json
import os
import datetime as dt
import hashlib

FRED_KEY = os.environ.get("FRED_API_KEY", "")
if not FRED_KEY:
    raise ValueError("Set FRED_API_KEY environment variable")

DB = "market.db"

# P1 FRED series: the core
P1_SERIES = {
    # Rates & policy
    "DFEDTARU": ("us.rate.fed.upper", "percent", "d", "rates"),
    "DFEDTARL": ("us.rate.fed.lower", "percent", "d", "rates"),
    "EFFR": ("us.rate.effr", "percent", "d", "rates"),
    "SOFR": ("us.rate.sofr", "percent", "d", "rates"),
    "DGS2": ("us.rate.2y", "percent", "d", "rates"),
    "DGS5": ("us.rate.5y", "percent", "d", "rates"),
    "DGS10": ("us.rate.10y", "percent", "d", "rates"),
    "DGS30": ("us.rate.30y", "percent", "d", "rates"),
    "T10Y2Y": ("us.spread.2s10s", "percent", "d", "rates"),
    "T10Y3M": ("us.spread.3m10y", "percent", "d", "rates"),
    
    # Inflation
    "PCEPILFE": ("us.inflation.pce.core", "index", "m", "inflation"),
    "CPIAUCSL": ("us.inflation.cpi", "index", "m", "inflation"),
    "CPILFESL": ("us.inflation.cpi.core", "index", "m", "inflation"),
    "T5YIFR": ("us.inflation.5y5y_fwd", "percent", "d", "inflation"),
    
    # Labour
    "UNRATE": ("us.labour.unemployment", "percent", "m", "labour"),
    
    # Growth
    "A191RL1Q225SBEA": ("us.growth.gdp_rate", "percent", "q", "growth"),
    "GDPNOW": ("us.growth.gdp_nowcast", "percent", "d", "growth"),
}

def init_db():
    """Create database and series table."""
    conn = sqlite3.connect(DB)
    with open("schema.sql") as f:
        conn.executescript(f.read())
    conn.commit()
    
    # Populate series registry
    cursor = conn.cursor()
    for source_id, (series_key, unit, freq, cat) in P1_SERIES.items():
        cursor.execute("""
            INSERT OR REPLACE INTO series
            (series_key, source, source_id, label, unit, frequency, category, country, priority)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            series_key, "fred", source_id, source_id,
            unit, freq, cat, "US", 1
        ))
    conn.commit()
    conn.close()

def fetch_fred(source_id):
    """Get latest observation for a FRED series."""
    r = requests.get(
        "https://api.stlouisfed.org/fred/series/observations",
        params={
            "series_id": source_id,
            "api_key": FRED_KEY,
            "file_type": "json",
            "sort_order": "desc",
            "limit": 1,
        },
        timeout=10,
    )
    r.raise_for_status()
    obs = r.json().get("observations", [])
    if not obs:
        return None, None
    o = obs[0]
    return o["date"], float(o["value"]) if o["value"] != "." else None

def upsert_observation(conn, series_key, obs_date, value):
    """Insert or update an observation."""
    fetched_at = dt.datetime.now().isoformat()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO observations (series_key, obs_date, value, fetched_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(series_key, obs_date) DO UPDATE SET
            value=excluded.value,
            fetched_at=excluded.fetched_at
    """, (series_key, obs_date, value, fetched_at))
    conn.commit()

def main():
    print("Initializing database...")
    init_db()
    
    print(f"Fetching {len(P1_SERIES)} FRED series...")
    conn = sqlite3.connect(DB)
    
    for i, (source_id, (series_key, *_)) in enumerate(P1_SERIES.items(), 1):
        try:
            obs_date, value = fetch_fred(source_id)
            if obs_date and value is not None:
                upsert_observation(conn, series_key, obs_date, value)
                print(f"  [{i:2d}] {series_key:<30} {obs_date} = {value}")
            else:
                print(f"  [{i:2d}] {series_key:<30} (no data)")
        except Exception as e:
            print(f"  [{i:2d}] {series_key:<30} ERROR: {e}")
    
    conn.close()
    print(f"\n✓ Data loaded into {DB}")
    
    # Quick sanity check
    conn = sqlite3.connect(DB)
    count = conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
    print(f"✓ {count} observations in database")
    conn.close()

if __name__ == "__main__":
    main()
