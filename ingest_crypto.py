"""
ingest_crypto.py — Load crypto prices and on-chain data.

Usage:
    python3 ingest_crypto.py

Sources:
    - CoinGecko (prices, market cap, dominance)
    - DefiLlama (stablecoin supply)
    - Alternative.me (Fear & Greed)
"""

import sqlite3
import requests
import json
import datetime as dt

DB = "market.db"

CRYPTO_SERIES = {
    "btc.price.usd": ("crypto", "usd", "d", "crypto"),
    "btc.price.cad": ("crypto", "cad", "d", "crypto"),
    "eth.price.usd": ("crypto", "usd", "d", "crypto"),
    "eth.price.cad": ("crypto", "cad", "d", "crypto"),
    "crypto.mcap.usd": ("crypto", "usd", "d", "crypto"),
    "btc.dominance": ("crypto", "percent", "d", "crypto"),
    "stablecoin.supply.usd": ("crypto", "usd", "d", "crypto"),
    "fear.greed.index": ("crypto", "index", "d", "sentiment"),
}

def fetch_coingecko():
    """Fetch BTC, ETH prices and market data from CoinGecko."""
    r = requests.get(
        "https://api.coingecko.com/api/v3/simple/price",
        params={
            "ids": "bitcoin,ethereum",
            "vs_currencies": "usd,cad",
            "include_market_cap": "true",
            "include_24hr_change": "true",
        },
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()
    
    results = {}
    
    # BTC and ETH prices
    if "bitcoin" in data:
        btc = data["bitcoin"]
        results["btc.price.usd"] = btc.get("usd")
        results["btc.price.cad"] = btc.get("cad")
    
    if "ethereum" in data:
        eth = data["ethereum"]
        results["eth.price.usd"] = eth.get("usd")
        results["eth.price.cad"] = eth.get("cad")
    
    # Global data
    r2 = requests.get(
        "https://api.coingecko.com/api/v3/global",
        timeout=10,
    )
    r2.raise_for_status()
    global_data = r2.json().get("data", {})
    
    results["crypto.mcap.usd"] = global_data.get("total_market_cap", {}).get("usd")
    results["btc.dominance"] = global_data.get("market_cap_percentage", {}).get("btc")
    
    return results

def fetch_stablecoins():
    """Fetch total stablecoin supply from DefiLlama."""
    r = requests.get(
        "https://stablecoins.llama.fi/stablecoins",
        params={"includePrices": "true"},
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()
    
    peg_assets = data.get("peggedAssets", [])
    total = sum(
        a.get("circulating", {}).get("peggedUSD", 0) or 0
        for a in peg_assets
    )
    
    return {"stablecoin.supply.usd": total}

def fetch_fear_greed():
    """Fetch Fear & Greed Index from Alternative.me."""
    r = requests.get(
        "https://api.alternative.me/fng/",
        params={"limit": 1},
        timeout=10,
    )
    r.raise_for_status()
    data = r.json().get("data", [])
    
    if data:
        return {"fear.greed.index": float(data[0]["value"])}
    return {}

def upsert_observation(conn, series_key, obs_date, value):
    """Insert or update an observation."""
    if value is None:
        return
    
    fetched_at = dt.datetime.now().isoformat()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO observations (series_key, obs_date, value, fetched_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(series_key, obs_date) DO UPDATE SET
            value=excluded.value,
            fetched_at=excluded.fetched_at
    """, (series_key, obs_date, value, fetched_at))
    conn.commit()

def init_series(conn):
    """Register crypto series."""
    cursor = conn.cursor()
    
    for series_key, (source, unit, freq, cat) in CRYPTO_SERIES.items():
        cursor.execute("""
            INSERT OR IGNORE INTO series
            (series_key, source, source_id, label, unit, frequency, category, country, priority)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (series_key, "coingecko", series_key, series_key, unit, freq, cat, "GLOBAL", 1))
    
    conn.commit()

def main():
    conn = sqlite3.connect(DB)
    
    print("Registering crypto series...")
    init_series(conn)
    
    today = dt.date.today().isoformat()
    
    print("\nFetching CoinGecko (BTC, ETH, market cap, dominance)...")
    try:
        cg_data = fetch_coingecko()
        for series_key, value in cg_data.items():
            if value is not None:
                upsert_observation(conn, series_key, today, value)
                print(f"  {series_key:<30} = {value:,.2f}")
            else:
                print(f"  {series_key:<30} (no data)")
    except Exception as e:
        print(f"  ERROR: {e}")
    
    print("\nFetching DefiLlama (stablecoin supply)...")
    try:
        sc_data = fetch_stablecoins()
        for series_key, value in sc_data.items():
            upsert_observation(conn, series_key, today, value)
            print(f"  {series_key:<30} = ${value/1e9:.1f}B")
    except Exception as e:
        print(f"  ERROR: {e}")
    
    print("\nFetching Alternative.me (Fear & Greed)...")
    try:
        fg_data = fetch_fear_greed()
        for series_key, value in fg_data.items():
            upsert_observation(conn, series_key, today, value)
            print(f"  {series_key:<30} = {value:.0f}")
    except Exception as e:
        print(f"  ERROR: {e}")
    
    conn.close()
    print(f"\n✓ Crypto data loaded into {DB}")
    
    # Verify
    conn = sqlite3.connect(DB)
    count = conn.execute("SELECT COUNT(DISTINCT series_key) FROM series").fetchone()[0]
    print(f"✓ {count} unique series registered total")
    conn.close()

if __name__ == "__main__":
    main()
