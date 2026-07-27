"""
generate_snapshot.py — Export database to snapshot.json for the frontend.

Reads YoY inflation rates from inflation_output.json (persistent historical data)
instead of relying on the database.
"""

import sqlite3
import json
import datetime as dt
import re

DB = "market.db"
SNAPSHOT = "snapshot.json"

INFLATION_SERIES = [
    "ca.inflation.cpi",
    "us.inflation.cpi",
    "us.inflation.cpi.core",
    "us.inflation.pce",
    "us.inflation.pce.core",
]

def load_inflation_yoy():
    """Load YoY rates from inflation_output.json (created by ingest_inflation_with_history.py)."""
    try:
        with open("inflation_output.json") as f:
            data = json.load(f)
            return data.get("yoy_rates", {})
    except FileNotFoundError:
        return {}

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
    
    # Load YoY rates from persistent inflation history
    yoy_rates = load_inflation_yoy()
    
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
    print(f"  {len(yoy_rates)} YoY inflation rates loaded from persistent history")
    if boc_consensus:
        print(f"  BoC Consensus: {boc_consensus['outcome'].upper()} ({boc_consensus['probability']:.1%})")
    if fed_consensus:
        print(f"  Fed Consensus: {fed_consensus['outcome'].upper()} ({fed_consensus['probability']:.1%})")

if __name__ == "__main__":
    main()
