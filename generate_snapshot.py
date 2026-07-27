"""
generate_snapshot.py — Export database to snapshot.json for the frontend.

Includes current + previous day's values for trend calculations.

Usage:
    python3 generate_snapshot.py

Output:
    snapshot.json (static file the frontend loads)
"""

import sqlite3
import json
import datetime as dt

DB = "market.db"
SNAPSHOT = "snapshot.json"

def main():
    conn = sqlite3.connect(DB)
    cursor = conn.cursor()
    
    # Build snapshot: series_key -> {obs_date: value, ...}
    snapshot = {}
    
    # Get all observations, sorted by date descending
    cursor.execute("""
        SELECT series_key, obs_date, value
        FROM observations
        WHERE value IS NOT NULL
        ORDER BY series_key, obs_date DESC
    """)
    
    rows = cursor.fetchall()
    series_count = {}
    
    for series_key, obs_date, value in rows:
        if series_key not in snapshot:
            snapshot[series_key] = {}
            series_count[series_key] = 0
        
        # Include latest + previous day (2 most recent observations)
        if series_count[series_key] < 2:
            snapshot[series_key][obs_date] = value
            series_count[series_key] += 1
    
    # Add latest BoC consensus
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
    
    # Add latest Fed consensus
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
    
    # Add metadata
    metadata = {
        "generated_at": dt.datetime.now().isoformat(),
        "series_count": len(snapshot),
        "observations_count": sum(len(v) for v in snapshot.values()),
    }
    
    output = {
        "_meta": metadata,
        "data": snapshot,
        "boc_consensus": boc_consensus,
        "fed_consensus": fed_consensus,
    }
    
    with open(SNAPSHOT, "w") as f:
        json.dump(output, f, indent=2)
    
    conn.close()
    
    print(f"✓ Generated {SNAPSHOT}")
    print(f"  {metadata['series_count']} series")
    print(f"  {metadata['observations_count']} observations total")
    if boc_consensus:
        print(f"  BoC Consensus: {boc_consensus['outcome'].upper()} ({boc_consensus['probability']:.1%})")
    if fed_consensus:
        print(f"  Fed Consensus: {fed_consensus['outcome'].upper()} ({fed_consensus['probability']:.1%})")

if __name__ == "__main__":
    main()
