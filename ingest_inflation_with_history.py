"""
ingest_inflation_with_history.py

Persistent inflation data ingest.
Fetches latest FRED inflation data, merges with history, calculates YoY rates.
"""

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:
    sys.exit("pip install requests")


INFLATION_SERIES = {
    "PCEPILFE": "us.inflation.pce.core",
    "PCEPI": "us.inflation.pce",
    "CPILFESL": "us.inflation.cpi.core",
    "CPIAUCSL": "us.inflation.cpi",
}

HISTORY_FILE = Path("inflation_history.json")


def fetch_fred_series(series_id: str, api_key: str) -> list[dict[str, Any]]:
    """Fetch all available observations for a series from FRED."""
    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "sort_order": "asc",
        "limit": 10000,
    }
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    return r.json().get("observations", [])


def load_history() -> dict[str, Any]:
    """Load existing inflation_history.json, or return empty structure."""
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE) as f:
            return json.load(f)
    return {
        "description": "Raw FRED inflation observations.",
        "schema": {},
        "observations": [],
    }


def merge_observations(
    history: dict[str, Any],
    series_id: str,
    series_key: str,
    fred_obs: list[dict[str, Any]],
) -> int:
    """Merge FRED observations into history. Returns count of new observations added."""
    existing_keys = {
        (o["series_key"], o["obs_date"])
        for o in history["observations"]
    }
    
    added = 0
    now = dt.datetime.utcnow().isoformat() + "Z"
    
    for obs in fred_obs:
        if obs["value"] == ".":
            continue
        
        obs_date = obs["date"]
        key = (series_key, obs_date)
        
        if key not in existing_keys:
            history["observations"].append({
                "series_key": series_key,
                "obs_date": obs_date,
                "value": float(obs["value"]),
                "fetched_at": now,
            })
            existing_keys.add(key)
            added += 1
    
    history["observations"].sort(
        key=lambda o: (o["series_key"], o["obs_date"])
    )
    
    return added


def calculate_yoy_rates(history: dict[str, Any]) -> dict[str, dict]:
    """Calculate YoY inflation rates."""
    by_series: dict[str, list[dict[str, Any]]] = {}
    for obs in history["observations"]:
        if obs["series_key"] not in by_series:
            by_series[obs["series_key"]] = []
        by_series[obs["series_key"]].append(obs)
    
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fred-key", required=True, help="FRED API key")
    parser.add_argument("--no-commit", action="store_true",
                        help="Don't commit to repo (for testing)")
    args = parser.parse_args()
    
    history = load_history()
    total_added = 0
    
    for series_id, series_key in INFLATION_SERIES.items():
        try:
            fred_obs = fetch_fred_series(series_id, args.fred_key)
            added = merge_observations(history, series_id, series_key, fred_obs)
            total_added += added
            print(f"  {series_key:<30} +{added:2d} observations", file=sys.stderr)
        except Exception as e:
            print(f"  {series_key:<30} ERROR: {e}", file=sys.stderr)
    
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)
    
    yoy_rates = calculate_yoy_rates(history)
    
    if total_added > 0 and not args.no_commit:
        try:
            os.system("git add inflation_history.json")
            os.system(f'git commit -m "chore: update inflation history (+{total_added} obs)"')
            print(f"✓ Committed {total_added} new observations", file=sys.stderr)
        except Exception as e:
            print(f"⚠ Commit failed (non-fatal): {e}", file=sys.stderr)
    
    result = {
        "yoy_rates": yoy_rates,
        "updated_count": total_added,
    }
    
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
