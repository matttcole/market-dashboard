"""
ingest_fed_polymarket.py — Fed rate decision consensus from Polymarket.

Uses Polymarket's public Gamma API (no auth required for market data) to find
the nearest upcoming "Fed Decision in <Month>?" event, and stores the single
highest-probability outcome as the Fed consensus — mirroring the pattern in
ingest_boc_expectations.py.

Note: Polymarket odds reflect real-money trader positioning, not the CME
FedWatch ZQ-futures methodology (see fedwatch.py for that approach, currently
blocked by Yahoo's auth requirements). Independent source, not a CME mirror.

Usage:
    python3 ingest_fed_polymarket.py
"""

import sqlite3
import requests
import datetime as dt
import re
import json

DB = "market.db"
GAMMA_BASE = "https://gamma-api.polymarket.com"
HEADERS = {"User-Agent": "market-dashboard-verify/0.1"}

# Maps each sub-market's question text to a stable outcome label.
OUTCOME_PATTERNS = [
    (re.compile(r"no change", re.I), "hold"),
    (re.compile(r"decrease.*50\+", re.I), "cut_50bp"),
    (re.compile(r"decrease.*25", re.I), "cut_25bp"),
    (re.compile(r"increase.*50\+", re.I), "hike_50bp"),
    (re.compile(r"increase.*25", re.I), "hike_25bp"),
]

def find_next_meeting_event():
    """Find the nearest upcoming 'Fed Decision in <Month>?' event."""
    r = requests.get(
        f"{GAMMA_BASE}/events",
        params={"tag_slug": "fed-rates", "active": "true", "closed": "false", "limit": 100},
        headers=HEADERS, timeout=15,
    )
    r.raise_for_status()
    events = r.json()

    today = dt.datetime.now(dt.timezone.utc)
    candidates = []
    for e in events:
        title = e.get("title", "")
        if not re.match(r"^Fed Decision in \w+\??$", title.strip()):
            continue
        end_date = e.get("endDate")
        if not end_date:
            continue
        end_dt = dt.datetime.fromisoformat(end_date.replace("Z", "+00:00"))
        if end_dt >= today:
            candidates.append((end_dt, e))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]

def parse_outcome(event):
    """Pick the single highest-probability outcome from the event's sub-markets."""
    best_outcome, best_prob = None, -1.0

    for m in event.get("markets", []):
        question = m.get("question", "")
        prices = m.get("outcomePrices")
        if not prices:
            continue

        # outcomePrices is sometimes a JSON-encoded string, sometimes a real list
        if isinstance(prices, str):
            prices = json.loads(prices)
        yes_price = float(prices[0])

        label = None
        for pattern, name in OUTCOME_PATTERNS:
            if pattern.search(question):
                label = name
                break
        if label is None:
            continue

        if yes_price > best_prob:
            best_prob = yes_price
            best_outcome = label

    return best_outcome, best_prob

def store_consensus(conn, asof_date, meeting_date, outcome, prob):
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO rate_probabilities
        (asof_date, central_bank, meeting_date, outcome, probability, anchor)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(asof_date, central_bank, meeting_date, outcome) DO UPDATE SET
            probability=excluded.probability
    """, (asof_date.isoformat(), "FED", meeting_date, outcome, prob, "polymarket"))
    conn.commit()

def main():
    asof_date = dt.date.today()
    print(f"Finding next Fed decision event on Polymarket...")
    print(f"As of: {asof_date}\n")

    event = find_next_meeting_event()
    if not event:
        print("  No upcoming Fed decision event found")
        return

    title = event.get("title")
    meeting_date = event.get("endDate", "")[:10]
    print(f"  Event: {title}  (meeting {meeting_date})")

    outcome, prob = parse_outcome(event)
    if outcome is None:
        print("  Could not parse any outcome from this event's markets")
        return

    conn = sqlite3.connect(DB)
    store_consensus(conn, asof_date, meeting_date, outcome, prob)
    conn.close()

    print(f"\n✓ Stored FED consensus for {meeting_date}")
    print(f"  {outcome.upper()} ({prob:.1%})")

if __name__ == "__main__":
    main()
