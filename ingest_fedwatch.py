"""
ingest_fedwatch.py — Compute FOMC meeting probabilities from ZQ futures.

Uses fedwatch.py to derive probabilities from 30-day Fed Funds futures.

Usage:
    python3 ingest_fedwatch.py
"""

import sqlite3
import requests
import datetime as dt
import time
from typing import Optional
from fedwatch import FedWatch, FOMC_2026_2027

DB = "market.db"

def fetch_zq_price(year: int, month: int) -> Optional[float]:
    """Fetch ZQ front month price from Yahoo Finance with rate limiting."""
    from fedwatch import zq_symbol
    
    sym = zq_symbol(year, month, "yahoo")
    
    for attempt in range(3):
        try:
            r = requests.get(
                f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}",
                params={"range": "1d", "interval": "1d"},
                timeout=10,
            )
            r.raise_for_status()
            res = r.json().get("chart", {}).get("result")
            if not res:
                return None
            
            closes = [c for c in res[0]["indicators"]["quote"][0]["close"] if c]
            return closes[-1] if closes else None
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                # Rate limited, wait and retry
                wait_time = 2 ** attempt
                print(f"    Rate limited on {sym}, waiting {wait_time}s...")
                time.sleep(wait_time)
                continue
            else:
                print(f"    {sym}: HTTP {e.response.status_code}")
                return None
        except Exception as e:
            print(f"    {sym}: {e}")
            return None
    
    return None

def solve_fedwatch(asof_date: dt.date):
    """
    Solve FedWatch using live ZQ prices.
    
    Current rates (as of Jul 27, 2026):
    - Target: 3.50-3.75 (mid 3.625)
    - EFFR: 3.63
    """
    
    # Initialize solver with current policy
    fw = FedWatch(
        current_lower=3.50,
        current_upper=3.75,
        effr=3.63,
        meetings=FOMC_2026_2027,
        asof=asof_date,
    )
    
    # Fetch ZQ prices for relevant months
    print("  Fetching ZQ prices (with rate limiting)...")
    for year in [2026, 2027]:
        for month in range(1, 13):
            price = fetch_zq_price(year, month)
            if price is not None:
                fw.add_contract(year, month, price)
                print(f"    {year}-{month:02d}: ${price:.4f}")
            time.sleep(0.5)  # Small delay between requests
    
    # Solve for probabilities
    print("  Solving for probabilities...")
    results = fw.solve()
    
    return results

def store_probabilities(conn, asof_date: dt.date, results):
    """Store probability results in database."""
    cursor = conn.cursor()
    
    for r in results:
        meeting_date = r.meeting.announcement.isoformat()
        
        for outcome, prob in r.probabilities.items():
            cursor.execute("""
                INSERT INTO rate_probabilities
                (asof_date, central_bank, meeting_date, outcome, probability, implied_rate, anchor)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                asof_date.isoformat(),
                "FED",
                meeting_date,
                outcome,
                prob,
                r.rate_after,
                r.anchor,
            ))
    
    conn.commit()

def main():
    asof_date = dt.date.today()
    
    print(f"Solving FedWatch for {asof_date}...")
    print(f"Current policy: 3.50-3.75 (mid 3.625%), EFFR 3.63%\n")
    
    try:
        results = solve_fedwatch(asof_date)
        
        if not results:
            print("  No meetings solved")
            return
        
        conn = sqlite3.connect(DB)
        store_probabilities(conn, asof_date, results)
        conn.close()
        
        print(f"\n✓ Stored {len(results)} meeting outcomes\n")
        
        # Summary
        for r in results:
            top = max(r.probabilities.items(), key=lambda kv: kv[1])
            probs = ", ".join(
                f"{k} {v:.1%}" for k, v in sorted(
                    r.probabilities.items(), key=lambda kv: -kv[1]
                ) if v >= 0.005
            )
            print(f"{r.meeting.announcement:%b %d, %Y}")
            print(f"  {r.rate_before:.3f}% → {r.rate_after:.3f}% ({r.move_bp:+.1f}bp) [{r.anchor}]")
            print(f"  {probs}")
            print()
    
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
