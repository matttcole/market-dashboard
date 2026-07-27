"""
ingest_boc_expectations.py — Parse BoC rate expectations from Montreal Exchange

Extracts implied probabilities for next BoC decision from CORRA futures.
"""

import sqlite3
import requests
from bs4 import BeautifulSoup
import datetime as dt
import re

DB = "market.db"

def fetch_boc_expectations():
    """
    Parse next BoC decision consensus from M-X table 5.
    
    Returns: {meeting_date: {outcome: probability}}
    """
    url = "https://www.m-x.ca/en/trading/tools/canadian-interest-rate-expectations"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }
    
    try:
        r = requests.get(url, timeout=10, headers=headers)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        
        # Get all tables
        tables = soup.find_all("table")
        
        if len(tables) < 5:
            print("  ERROR: Expected at least 5 tables")
            return {}
        
        # Table 5 (index 4) contains the expectations
        table5 = tables[4]
        rows = table5.find_all("tr")[1:]  # Skip header
        
        results = {}
        
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 7:
                continue
            
            # First cell: BoC Meeting Date
            date_text = cells[0].get_text(strip=True)
            
            try:
                meeting_date = dt.datetime.strptime(date_text, "%B %d, %Y").date()
            except ValueError:
                continue
            
            # Cells 3-6 contain: 0.25%, 0.50%, 0.75%, 1.00% probabilities
            probs = {}
            
            # Extract percentage values from remaining cells
            prob_cells = cells[3:]
            hike_increments = [0.25, 0.50, 0.75, 1.00]
            
            for i, cell in enumerate(prob_cells[:4]):
                text = cell.get_text(strip=True)
                # Look for percentage
                match = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
                if match:
                    prob_pct = float(match.group(1))
                    increment = hike_increments[i]
                    
                    if increment == 0.25:
                        outcome = "hike_25bp"
                    elif increment == 0.50:
                        outcome = "hike_50bp"
                    elif increment == 0.75:
                        outcome = "hike_75bp"
                    elif increment == 1.00:
                        outcome = "hike_100bp"
                    
                    probs[outcome] = prob_pct / 100.0
            
            if probs:
                results[meeting_date.isoformat()] = probs
        
        return results
    
    except Exception as e:
        print(f"  ERROR fetching M-X: {e}")
        import traceback
        traceback.print_exc()
        return {}

def determine_consensus(probs):
    """
    Determine if consensus is: hike, hold, or cut.
    Return the most likely outcome.
    """
    if not probs:
        return None, 0.0
    
    # If any hike has >50%, consensus is hike
    total_hike = sum(p for outcome, p in probs.items() if "hike" in outcome)
    
    if total_hike > 0.5:
        # Return strongest hike
        return "hike", total_hike
    else:
        # Default to hold if no hike consensus
        return "hold", 1.0 - total_hike

def store_consensus(conn, asof_date: dt.date, results):
    """Store BoC expectations in database."""
    cursor = conn.cursor()
    
    for meeting_date_str, probs in results.items():
        consensus_outcome, consensus_prob = determine_consensus(probs)
        
        cursor.execute("""
            INSERT INTO rate_probabilities
            (asof_date, central_bank, meeting_date, outcome, probability, anchor)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(asof_date, central_bank, meeting_date, outcome) DO UPDATE SET
                probability=excluded.probability
        """, (
            asof_date.isoformat(),
            "BOC",
            meeting_date_str,
            consensus_outcome,
            consensus_prob,
            "m-x",
        ))
    
    conn.commit()

def main():
    asof_date = dt.date.today()
    
    print(f"Fetching BoC rate expectations from M-X...")
    print(f"As of: {asof_date}\n")
    
    results = fetch_boc_expectations()
    
    if not results:
        print("  No expectations retrieved")
        return
    
    conn = sqlite3.connect(DB)
    store_consensus(conn, asof_date, results)
    conn.close()
    
    print(f"✓ Stored {len(results)} meeting expectations\n")
    
    # Summary
    for meeting_date_str, probs in sorted(results.items()):
        consensus, prob = determine_consensus(probs)
        detail = ", ".join(f"{k.replace('_', ' ')} {v:.1%}" for k, v in sorted(probs.items(), key=lambda x: -x[1]))
        print(f"{meeting_date_str}")
        print(f"  Consensus: {consensus.upper()} ({prob:.1%})")
        print(f"  Detail: {detail}")
        print()

if __name__ == "__main__":
    main()
