"""
generate_snapshot.py — Export database to snapshot.json for the frontend.

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
    
    cursor.execute("""
        SELECT series_key, obs_date, value
        FROM observations
        WHERE value IS NOT NULL
        ORDER BY series_key, obs_date DESC
    """)
    
    for series_key, obs_date, value in cursor.fetchall():
        if series_key not in snapshot:
            snapshot[series_key] = {}
        snapshot[series_key][obs_date] = value
    
    # Add metadata
    metadata = {
        "generated_at": dt.datetime.now().isoformat(),
        "series_count": len(snapshot),
        "observations_count": sum(len(v) for v in snapshot.values()),
    }
    
    output = {
        "_meta": metadata,
        "data": snapshot,
    }
    
    with open(SNAPSHOT, "w") as f:
        json.dump(output, f, indent=2)
    
    conn.close()
    
    print(f"✓ Generated {SNAPSHOT}")
    print(f"  {metadata['series_count']} series")
    print(f"  {metadata['observations_count']} observations total")
    print(f"  Generated at {metadata['generated_at']}")

if __name__ == "__main__":
    main()
