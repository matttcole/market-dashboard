"""
generate_snapshot.py — Export database to snapshot.json for the frontend.

Calculates YoY inflation rates from monthly CPI/PCE data.
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

def is_valid_date(date_str):
    """Check if date string is valid YYYY-MM-DD format."""
    try:
        dt.datetime.strptime(date_str, "%Y-%m-%d")
        return True
    except ValueError:
        return False

def calculate_yoy_rate(values_by_date):
    """Calculate YoY inflation rate from monthly index values."""
    # Filter out invalid dates
    valid_values = {date: val for date, val in values_by_date.items() if is_valid_date(date)}
    
    if len(valid_values) < 2:
        return None
    
    sorted_dates = sorted(valid_values.keys(), reverse=True)
    current_date = sorted_dates[0]
    current_value = valid_values[current_date]
    
    try:
        current_dt = dt.datetime.strptime(current_date, "%Y-%m-%d")
    except ValueError:
        return None
    
    target_dt = current_dt.replace(year=current_dt.year - 1)
    
    prior_date = None
    prior_value = None
    
    for check_date_str in sorted_dates[1:]:
        try:
            check_dt = dt.datetime.strptime(check_date_str, "%Y-%m-%d")
            if check_dt.year == target_dt.year and check_dt.month == target_dt.month:
                prior_date = check_date_str
                prior_value = valid_values[check_date_str]
                break
        except ValueError:
            continue
    
    if prior_value is None:
        return None
    
    yoy_rate = ((current_value - prior_value) / prior_value) * 100
    return yoy_rate, current_date, prior_date

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
    
    yoy_rates = {}
    for inflation_series in INFLATION_SERIES:
        if inflation_series in snapshot:
            yoy_data = calculate_yoy_rate(snapshot[inflation_series])
            if yoy_data:
                yoy_rate, current_date, prior_date = yoy_data
                yoy_rates[inflation_series] = {
                    "rate": yoy_rate,
                    "current_date": current_date,
                    "prior_date": prior_date,
                }
    
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
    print(f"  {len(yoy_rates)} YoY inflation rates calculated")
    if boc_consensus:
        print(f"  BoC Consensus: {boc_consensus['outcome'].upper()} ({boc_consensus['probability']:.1%})")
    if fed_consensus:
        print(f"  Fed Consensus: {fed_consensus['outcome'].upper()} ({fed_consensus['probability']:.1%})")

if __name__ == "__main__":
    main()
