"""
ingest_boc_statcan.py — Load BoC and StatCan data into the same database.

Usage:
    python3 ingest_boc_statcan.py
"""

import sqlite3
import requests
import json
import datetime as dt

DB = "market.db"

# BoC Valet series
BOC_SERIES = {
    "FXUSDCAD": ("ca.fx.usdcad", "ratio", "d", "fx"),
    "BD.CDN.2YR.DQ.YLD": ("ca.rate.2y", "percent", "d", "rates"),
    "BD.CDN.5YR.DQ.YLD": ("ca.rate.5y", "percent", "d", "rates"),
    "BD.CDN.10YR.DQ.YLD": ("ca.rate.10y", "percent", "d", "rates"),
    "AVG.INTWO": ("ca.rate.corra", "percent", "d", "rates"),
    "V39079": ("ca.rate.policy", "percent", "d", "rates"),
}

def fetch_boc(series_id):
    """Get latest observation from BoC Valet."""
    r = requests.get(
        f"https://www.bankofcanada.ca/valet/observations/{series_id}/json",
        params={"recent": 1},
        timeout=10,
    )
    r.raise_for_status()
    obs = r.json().get("observations", [])
    if not obs:
        return None, None
    
    latest = obs[-1]  # Most recent
    obs_date = latest.get("d")
    
    # Value is in a key matching the series_id
    value = None
    for k, v in latest.items():
        if k != "d" and isinstance(v, dict) and "v" in v:
            value = float(v["v"])
            break
    
    return obs_date, value

def fetch_statcan(vector_id, table_label):
    """Get latest observation from StatCan WDS."""
    r = requests.post(
        "https://www150.statcan.gc.ca/t1/wds/rest/getDataFromVectorsAndLatestNPeriods",
        json=[{"vectorId": vector_id, "latestN": 1}],
        timeout=10,
        headers={"Content-Type": "application/json"},
    )
    r.raise_for_status()
    body = r.json()
    
    if not body or body[0].get("status") != "SUCCESS":
        return None, None
    
    obj = body[0]["object"]
    pts = obj.get("vectorDataPoint", [])
    if not pts:
        return None, None
    
    pt = pts[0]
    obs_date = pt["refPer"]
    value = float(pt["value"])
    return obs_date, value

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

def init_series(conn):
    """Add new series to registry."""
    cursor = conn.cursor()
    
    # BoC
    for source_id, (series_key, unit, freq, cat) in BOC_SERIES.items():
        cursor.execute("""
            INSERT OR IGNORE INTO series
            (series_key, source, source_id, label, unit, frequency, category, country, priority)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (series_key, "boc", source_id, source_id, unit, freq, cat, "CA", 1))
    
    # StatCan (manually curated vector IDs from verify_sources.py output)
    statcan_series = {
        "ca.inflation.cpi": (41690973, "18-10-0004-01", "percent", "m", "inflation"),
    }
    for series_key, (vector_id, table_id, unit, freq, cat) in statcan_series.items():
        cursor.execute("""
            INSERT OR IGNORE INTO series
            (series_key, source, source_id, label, unit, frequency, category, country, priority)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (series_key, "statcan", table_id, f"StatCan {table_id}", unit, freq, cat, "CA", 1))
    
    conn.commit()

def main():
    conn = sqlite3.connect(DB)
    
    print("Registering BoC and StatCan series...")
    init_series(conn)
    
    print(f"\nFetching {len(BOC_SERIES)} BoC series...")
    for source_id, (series_key, *_) in BOC_SERIES.items():
        try:
            obs_date, value = fetch_boc(source_id)
            if obs_date and value is not None:
                upsert_observation(conn, series_key, obs_date, value)
                print(f"  {series_key:<30} {obs_date} = {value}")
            else:
                print(f"  {series_key:<30} (no data)")
        except Exception as e:
            print(f"  {series_key:<30} ERROR: {e}")
    
    print(f"\nFetching StatCan CPI...")
    try:
        obs_date, value = fetch_statcan(41690973, "18-10-0004-01")
        if obs_date and value is not None:
            upsert_observation(conn, "ca.inflation.cpi", obs_date, value)
            print(f"  ca.inflation.cpi{' ' * 16} {obs_date} = {value}")
        else:
            print(f"  ca.inflation.cpi{' ' * 16} (no data)")
    except Exception as e:
        print(f"  ca.inflation.cpi{' ' * 16} ERROR: {e}")
    
    conn.close()
    print(f"\n✓ Data loaded into {DB}")
    
    # Verify
    conn = sqlite3.connect(DB)
    count = conn.execute("SELECT COUNT(DISTINCT series_key) FROM series").fetchone()[0]
    print(f"✓ {count} unique series registered")
    conn.close()

if __name__ == "__main__":
    main()
