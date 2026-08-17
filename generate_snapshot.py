"""
generate_snapshot.py — Export database to snapshot.json for the frontend.

Reads YoY inflation rates from inflation_history.json (persistent historical data)
"""

import sqlite3
import json
import datetime as dt
from pathlib import Path

DB = "market.db"
SNAPSHOT = "snapshot.json"
HISTORY_FILE = Path("inflation_history.json")

INFLATION_SERIES = [
    "ca.inflation.cpi",
    "us.inflation.cpi",
    "us.inflation.cpi.core",
    "us.inflation.pce.core",
]

def calculate_yoy_from_history() -> dict:
    """Calculate YoY rates from inflation_history.json"""
    if not HISTORY_FILE.exists():
        return {}
    
    with open(HISTORY_FILE) as f:
        history = json.load(f)
    
    by_series = {}
    for obs in history.get("observations", []):
        series_key = obs["series_key"]
        if series_key not in INFLATION_SERIES:
            continue
        if series_key not in by_series:
            by_series[series_key] = []
        by_series[series_key].append(obs)
    
    rates = {}
    for series_key, obs_list in by_series.items():
        if len(obs_list) < 2:
            continue
        
        latest = obs_list[-1]
        latest_date = dt.datetime.strptime(latest["obs_date"], "%Y-%m-%d")
        
        target_date = latest_date - dt.timedelta(days=365)
        
        prior = None
        for obs in reversed(obs_list[:-1]):
            obs_dt = dt.datetime.strptime(obs["obs_date"], "%Y-%m-%d")
            if abs((obs_dt - target_date).days) <= 30:
                prior = obs
                break
        
        if prior and prior["value"] > 0:
            yoy = ((latest["value"] / prior["value"]) - 1) * 100
            rates[series_key] = {
                "rate": round(yoy, 2),
                "current_date": latest["obs_date"],
                "prior_date": prior["obs_date"],
            }
    
    return rates

def main():
    conn = sqlite3.connect(DB)
    cursor = conn.cursor()
    
    snapshot = {}
    
    for inflation_series in INFLATION_SERIES:
        cursor.execute("""
            SELECT obs_date, value
            FROM observations
            WHERE series_key = ?
            AND value IS NOT NULL
            ORDER BY obs_date DESC
            LIMIT 150
        """, (inflation_series,))
        
        rows = cursor.fetchall()
        if rows:
            values_by_date = {date: value for date, value in rows}
            snapshot[inflation_series] = values_by_date
    
    cursor.execute("""
        SELECT DISTINCT series_key
        FROM observations
        WHERE series_key NOT IN ({})
        ORDER BY series_key
    """.format(','.join('?' * len(INFLATION_SERIES))), INFLATION_SERIES)
    
    other_series = [row[0] for row in cursor.fetchall()]
    
    for series_key in other_series:
        cursor.execute("""
            SELECT obs_date, value
            FROM observations
            WHERE series_key = ?
            AND value IS NOT NULL
            ORDER BY obs_date DESC
            LIMIT 2
        """, (series_key,))
        
        rows = cursor.fetchall()
        if rows:
            values_by_date = {date: value for date, value in rows}
            snapshot[series_key] = values_by_date
    
    # Calculate YoY rates from inflation_history.json
    yoy_rates = calculate_yoy_from_history()
    
    cursor.execute("""
        SELECT outcome, probability
        FROM rate_probabilities
        WHERE central_bank = 'BOC'
        ORDER BY asof_date DESC, meeting_date ASC
        LIMIT 1
    """)
    
    boc_result = cursor.fetchone()
    boc_consensus = {}
    if boc_result:
        outcome, prob = boc_result
        boc_consensus = {
            "outcome": outcome,
            "probability": prob
        }
    
    cursor.execute("""
        SELECT outcome, probability
        FROM rate_probabilities
        WHERE central_bank = 'FED'
        ORDER BY asof_date DESC, meeting_date ASC
        LIMIT 1
    """)
    
    fed_result = cursor.fetchone()
    fed_consensus = {}
    if fed_result:
        outcome, prob = fed_result
        fed_consensus = {
            "outcome": outcome,
            "probability": prob
        }
    
    metadata = {
        "generated_at": dt.datetime.now().isoformat(),
        "series_count": len(snapshot),
        "observations_count": sum(len(v) for v in snapshot.values()),
    }
    
    output = {
        "_meta": metadata,
        "data": snapshot,
        "yoy_rates": yoy_rates,
        "boc_consensus": boc_consensus,
        "fed_consensus": fed_consensus,
    }
    
    with open(SNAPSHOT, "w") as f:
        json.dump(output, f, indent=2)
    
    conn.close()
    
    print(f"✓ Generated {SNAPSHOT}")
    print(f"  {metadata['series_count']} series")
    print(f"  {metadata['observations_count']} observations total")
    print(f"  {len(yoy_rates)} YoY inflation rates loaded")
    if boc_consensus:
        print(f"  BoC Consensus: {boc_consensus['outcome'].upper()} ({boc_consensus['probability']:.1%})")
    if fed_consensus:
        print(f"  Fed Consensus: {fed_consensus['outcome'].upper()} ({fed_consensus['probability']:.1%})")

if __name__ == "__main__":
    main()
