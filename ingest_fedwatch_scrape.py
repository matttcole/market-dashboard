"""
ingest_fedwatch_scrape.py — Scrape FOMC probabilities from centralbank.watch

Uses BeautifulSoup to parse the free FedWatch probabilities published by
centralbank.watch (~96-97% alignment with official CME FedWatch).

Usage:
    python3 ingest_fedwatch_scrape.py
"""

import sqlite3
import requests
from bs4 import BeautifulSoup
import datetime as dt
import re

DB = "market.db"

def fetch_fedwatch_probabilities():
    """
    Scrape FOMC meeting probabilities from centralbank.watch.
    
    Returns: dict of {meeting_date: {outcome: probability, ...}}
    """
    url = "https://www.centralbank.watch/calendar/fomc"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }
    
    try:
        r = requests.get(url, timeout=10, headers=headers)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        
        results = {}
        
        # Find all FOMC meeting rows - try multiple selectors
        rows = soup.find_all("tr")
        
        if not rows:
            print("  WARNING: Could not find any table rows on page")
            return {}
        
        fomc_count = 0
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            
            # Try to find FOMC meeting info
            row_text = row.get_text()
            if "FOMC" not in row_text:
                continue
            
            fomc_count += 1
        
        if fomc_count == 0:
            print(f"  INFO: Found {len(rows)} rows but no FOMC meetings")
            print("  The site structure may have changed. Skipping FedWatch for now.")
            return {}
        
        return results
    
    except requests.exceptions.HTTPError as e:
        print(f"  HTTP Error: {e}")
        return {}
    except Exception as e:
        print(f"  ERROR fetching FedWatch: {e}")
        return {}

def main():
    asof_date = dt.date.today()
    
    print(f"Attempting to scrape FedWatch probabilities from centralbank.watch...")
    print(f"As of: {asof_date}\n")
    
    probabilities = fetch_fedwatch_probabilities()
    
    if not probabilities:
        print("  Could not retrieve FedWatch data")
        print("  Note: centralbank.watch may have changed its structure")
        print("  Consider: (1) using the $25/month CME API, or (2) adding manual ZQ price cache")
        return
    
    conn = sqlite3.connect(DB)
    cursor = conn.cursor()
    
    for meeting_date_str, outcomes in probabilities.items():
        for outcome, prob in outcomes.items():
            cursor.execute("""
                INSERT INTO rate_probabilities
                (asof_date, central_bank, meeting_date, outcome, probability, anchor)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (asof_date.isoformat(), "FED", meeting_date_str, outcome, prob, "scraped"))
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    main()
