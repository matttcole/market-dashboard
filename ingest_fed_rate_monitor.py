"""
ingest_fed_rate_monitor.py — Scrape FOMC probabilities from investing.com

Investing.com publishes free daily market-implied probabilities for FOMC
decisions. Parse the Fed Rate Monitor table.

Usage:
    python3 ingest_fed_rate_monitor.py
"""

import sqlite3
import requests
from bs4 import BeautifulSoup
import datetime as dt
import re

DB = "market.db"

def fetch_fed_rate_monitor():
    """
    Scrape FOMC probabilities from investing.com Fed Rate Monitor.
    
    Returns: dict of {meeting_date: {outcome: probability, ...}}
    """
    url = "https://www.investing.com/central-banks/fed-rate-monitor"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }
    
    try:
        r = requests.get(url, timeout=10, headers=headers)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        
        results = {}
        
        # Find the rate monitor table
        table = soup.find("table", {"class": re.compile(".*rate.*monitor.*", re.I)})
        
        if not table:
            # Try finding any table with FOMC data
            tables = soup.find_all("table")
            for t in tables:
                if "FOMC" in t.get_text() or "probability" in t.get_text().lower():
                    table = t
                    break
        
        if not table:
            print("  WARNING: Could not find rate monitor table")
            return {}
        
        rows = table.find_all("tr")[1:]  # Skip header
        
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            
            # First cell is meeting date
            date_text = cells[0].get_text(strip=True)
            
            # Try to parse date (format varies)
            meeting_date = None
            for fmt in ["%B %d, %Y", "%b %d, %Y", "%Y-%m-%d"]:
                try:
                    meeting_date = dt.datetime.strptime(date_text, fmt).date()
                    break
                except ValueError:
                    continue
            
            if not meeting_date:
                continue
            
            # Parse probability cells
            probs = {}
            for i, cell in enumerate(cells[1:]):
                text = cell.get_text(strip=True)
                # Match patterns like "62.4%" or "No Change 62.4%"
                match = re.search(r"(\d+(?:\.\d+)?)%", text)
                if match:
                    prob_pct = float(match.group(1))
                    # Infer outcome from cell content
                    cell_text_lower = text.lower()
                    if "no change" in cell_text_lower or "hold" in cell_text_lower:
                        outcome = "hold"
                    elif "hike" in cell_text_lower or "+25" in text or "+50" in text:
                        outcome = "+25bp"
                    elif "cut" in cell_text_lower or "-25" in text or "-50" in text:
                        outcome = "-25bp"
                    else:
                        outcome = f"outcome_{i}"
                    
                    probs[outcome] = prob_pct / 100.0
            
            if probs:
                results[meeting_date.isoformat()] = probs
        
        return results
    
    except Exception as e:
        print(f"  ERROR fetching rate monitor: {e}")
        return {}

def store_probabilities(conn, asof_date: dt.date, probabilities):
    """Store probability results in database."""
    cursor = conn.cursor()
    
    for meeting_date_str, outcomes in probabilities.items():
        for outcome, prob in outcomes.items():
            cursor.execute("""
                INSERT INTO rate_probabilities
                (asof_date, central_bank, meeting_date, outcome, probability, anchor)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(asof_date, central_bank, meeting_date, outcome) DO UPDATE SET
                    probability=excluded.probability
            """, (
                asof_date.isoformat(),
                "FED",
                meeting_date_str,
                outcome,
                prob,
                "investing.com",
            ))
    
    conn.commit()

def main():
    asof_date = dt.date.today()
    
    print(f"Fetching FOMC probabilities from investing.com...")
    print(f"As of: {asof_date}\n")
    
    probabilities = fetch_fed_rate_monitor()
    
    if not probabilities:
        print("  No probabilities retrieved")
        print("  (Site structure may have changed)")
        return
    
    conn = sqlite3.connect(DB)
    store_probabilities(conn, asof_date, probabilities)
    conn.close()
    
    print(f"✓ Stored {len(probabilities)} meeting outcomes\n")
    
    # Summary
    for meeting_date_str, outcomes in sorted(probabilities.items()):
        top_outcome = max(outcomes.items(), key=lambda kv: kv[1])
        prob_strs = ", ".join(
            f"{k} {v:.1%}" for k, v in sorted(
                outcomes.items(), key=lambda kv: -kv[1]
            ) if v >= 0.01
        )
        print(f"{meeting_date_str}")
        print(f"  {prob_strs}  << {top_outcome[0]}")
        print()

if __name__ == "__main__":
    main()
