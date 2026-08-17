"""
verify_sources.py — Run this BEFORE writing any schema.

Hits every endpoint in the data map exactly once and reports what came back:
value, timestamp, latency, and shape. Roughly 15 of the series IDs in the map
were unverified, and the two Canadian APIs fail *silently* — a wrong ID returns
an empty array with HTTP 200, not an error. This script surfaces that.

    pip install requests
    export FRED_API_KEY=your_key_here
    export COINGECKO_KEY=xxxx      # optional; falls back to keyless
    python verify_sources.py

Output is a pass/fail table. Anything marked FAIL or EMPTY needs its ID fixed
before it goes in the schema.
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable

try:
    import requests
except ImportError:
    sys.exit("pip install requests")

FRED_KEY = os.environ.get("FRED_API_KEY", "")
CG_KEY = os.environ.get("COINGECKO_KEY", "")
TIMEOUT = 20
UA = {"User-Agent": "market-dashboard-verify/0.1"}


@dataclass
class Check:
    name: str
    group: str
    fn: Callable[[], tuple[str, Any]]
    critical: bool = True


results: list[tuple[Check, str, str, float]] = []


def run(check: Check) -> None:
    t0 = time.time()
    try:
        status, value = check.fn()
    except requests.exceptions.Timeout:
        status, value = "FAIL", "timeout"
    except Exception as e:
        status, value = "FAIL", f"{type(e).__name__}: {e}"[:90]
    results.append((check, status, str(value)[:70], time.time() - t0))


def get(url: str, **kw) -> requests.Response:
    r = requests.get(url, timeout=TIMEOUT, headers=UA, **kw)
    r.raise_for_status()
    return r


# --------------------------------------------------------------------------
# FRED — series IDs I'm confident in, but confirm they're all live
# --------------------------------------------------------------------------

FRED_SERIES = {
    # rates & policy
    "DFEDTARU": "Fed target upper", "DFEDTARL": "Fed target lower",
    "EFFR": "Effective fed funds", "SOFR": "SOFR",
    "DGS2": "UST 2Y", "DGS5": "UST 5Y", "DGS10": "UST 10Y", "DGS30": "UST 30Y",
    "T10Y2Y": "2s10s", "T10Y3M": "3m10y", "DFII10": "10Y TIPS real",
    # inflation
    "PCEPILFE": "Core PCE", "PCEPI": "PCE", "CPIAUCSL": "CPI",
    "CPILFESL": "Core CPI", "T5YIFR": "5y5y fwd", "T10YIE": "10y breakeven",
    "MICH": "UMich 1yr exp",
    # growth & labour
    "GDPC1": "Real GDP", "A191RL1Q225SBEA": "GDP %chg", "GDPNOW": "GDPNow",
    "UNRATE": "Unemployment", "PAYEMS": "Payrolls", "ICSA": "Initial claims",
    "CCSA": "Continuing claims", "JTSJOL": "JOLTS openings",
    "CES0500000003": "Avg hourly earnings", "RSAFS": "Retail sales",
    "INDPRO": "Industrial prod", "UMCSENT": "Consumer sentiment",
    # liquidity
    "WALCL": "Fed assets", "WTREGEN": "TGA (weekly)",
    "RRPONTSYD": "Reverse repo", "WRESBAL": "Reserve balances", "M2SL": "M2",
    # credit & risk
    "BAMLH0A0HYM2": "HY OAS", "BAMLC0A0CM": "IG OAS", "NFCI": "Chicago NFCI",
    "STLFSI4": "StL stress", "VIXCLS": "VIX", "VXVCLS": "VIX3M",
    # markets
    "SP500": "S&P 500", "NASDAQCOM": "Nasdaq", "DJIA": "Dow",
    "DCOILWTICO": "WTI", "DCOILBRENTEU": "Brent", "DTWEXBGS": "Broad USD",
    "MORTGAGE30US": "30y mortgage", "HOUST": "Housing starts",
    "CSUSHPINSA": "Case-Shiller",
    # flagged as uncertain in the map
    "MICH5YR": "UMich 5yr exp  [UNVERIFIED]",
    "GACDISA066MSFRBPHI": "Philly Fed  [UNVERIFIED]",
    "GACDFNA066MNFRBNY": "Empire State  [UNVERIFIED]",
}


def check_fred(series_id: str):
    if not FRED_KEY:
        return "SKIP", "no FRED_API_KEY"
    r = get(
        "https://api.stlouisfed.org/fred/series/observations",
        params={
            "series_id": series_id, "api_key": FRED_KEY, "file_type": "json",
            "sort_order": "desc", "limit": 1,
        },
    )
    obs = r.json().get("observations", [])
    if not obs:
        return "EMPTY", "no observations"
    o = obs[0]
    if o["value"] == ".":
        return "WARN", f"{o['date']} = missing"
    return "OK", f"{o['date']} = {o['value']}"


# --------------------------------------------------------------------------
# Bank of Canada Valet — the silent-failure risk
# --------------------------------------------------------------------------

def check_boc_group(group: str):
    r = get(f"https://www.bankofcanada.ca/valet/observations/group/{group}/json",
            params={"recent": 1})
    obs = r.json().get("observations", [])
    if not obs:
        return "EMPTY", "group returned no observations"
    latest = obs[-1]
    keys = [k for k in latest if k != "d"]
    return "OK", f"{latest['d']}: {len(keys)} series ({', '.join(keys[:3])}...)"


def check_boc_series(series: str):
    r = get(f"https://www.bankofcanada.ca/valet/observations/{series}/json",
            params={"recent": 1})
    obs = r.json().get("observations", [])
    if not obs:
        return "EMPTY", "series returned no observations  <-- BAD ID"
    latest = obs[-1]
    val = next((v.get("v") for k, v in latest.items() if k != "d"), None)
    return "OK", f"{latest['d']} = {val}"


def check_boc_list():
    """Dump candidate series so you can resolve the unverified IDs by hand."""
    r = get("https://www.bankofcanada.ca/valet/lists/groups/json")
    groups = r.json().get("groups", {})
    hits = {
        k: v.get("label", "")
        for k, v in groups.items()
        if any(t in k.lower() or t in v.get("label", "").lower()
               for t in ("corra", "cpi", "inflation", "interest", "policy"))
    }
    with open("boc_candidate_groups.json", "w") as f:
        json.dump(hits, f, indent=2)
    return "OK", f"{len(groups)} groups; {len(hits)} candidates -> boc_candidate_groups.json"


# --------------------------------------------------------------------------
# StatCan WDS — POST-based, vectors must be resolved from tables first
# --------------------------------------------------------------------------

def check_statcan_alive():
    r = requests.post(
        "https://www150.statcan.gc.ca/t1/wds/rest/getDataFromVectorsAndLatestNPeriods",
        json=[{"vectorId": 41690973, "latestN": 1}],
        timeout=TIMEOUT, headers={**UA, "Content-Type": "application/json"},
    )
    r.raise_for_status()
    body = r.json()
    if not body or body[0].get("status") != "SUCCESS":
        return "WARN", f"reachable, sample vector rejected: {str(body)[:50]}"
    obj = body[0]["object"]
    pts = obj.get("vectorDataPoint", [])
    return "OK", f"v{obj.get('vectorId')} {pts[0]['refPer']} = {pts[0]['value']}" if pts else ("EMPTY", "no points")


def check_statcan_cube(pid: str, label: str):
    """Resolve a table's metadata so you can pick coordinates -> vector IDs."""
    r = requests.post(
        "https://www150.statcan.gc.ca/t1/wds/rest/getCubeMetadata",
        json=[{"productId": int(pid.replace("-", "")[:8])}],
        timeout=TIMEOUT, headers={**UA, "Content-Type": "application/json"},
    )
    r.raise_for_status()
    body = r.json()
    if not body or body[0].get("status") != "SUCCESS":
        return "FAIL", f"bad PID {pid}  <-- fix in map"
    obj = body[0]["object"]
    dims = obj.get("dimension", [])
    return "OK", f"{obj.get('cubeTitleEn','')[:40]} ({len(dims)} dims)"


# --------------------------------------------------------------------------
# Everything else
# --------------------------------------------------------------------------

def check_nyfed_rrp():
    r = get("https://markets.newyorkfed.org/api/rp/reverserepo/propositions/lastTwoWeeks.json")
    ops = r.json().get("repo", {}).get("operations", [])
    return ("OK", f"{ops[0]['operationDate']} ${ops[0].get('totalAmtAccepted',0)/1e9:.1f}B") if ops else ("EMPTY", "no ops")


def check_nyfed_effr():
    r = get("https://markets.newyorkfed.org/api/rates/unsecured/effr/last/1.json")
    rates = r.json().get("refRates", [])
    return ("OK", f"{rates[0]['effectiveDate']} = {rates[0]['percentRate']}") if rates else ("EMPTY", "none")


def check_treasury_tga():
    r = get(
        "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/"
        "accounting/dts/operating_cash_balance",
        params={"sort": "-record_date", "page[size]": 1},
    )
    d = r.json().get("data", [])
    return ("OK", f"{d[0]['record_date']} = ${d[0]['close_today_bal']}M") if d else ("EMPTY", "none")


def check_coingecko_simple():
    base = "https://api.coingecko.com/api/v3"
    hdr = {**UA, **({"x-cg-demo-api-key": CG_KEY} if CG_KEY else {})}
    r = requests.get(f"{base}/simple/price", timeout=TIMEOUT, headers=hdr,
                     params={"ids": "bitcoin,ethereum", "vs_currencies": "usd,cad",
                             "include_24hr_change": "true"})
    r.raise_for_status()
    d = r.json()
    return "OK", f"BTC ${d['bitcoin']['usd']:,.0f} / ETH ${d['ethereum']['usd']:,.0f}"


def check_coingecko_global():
    hdr = {**UA, **({"x-cg-demo-api-key": CG_KEY} if CG_KEY else {})}
    r = requests.get("https://api.coingecko.com/api/v3/global",
                     timeout=TIMEOUT, headers=hdr)
    r.raise_for_status()
    d = r.json()["data"]
    return "OK", (f"mcap ${d['total_market_cap']['usd']/1e12:.2f}T, "
                  f"BTC.D {d['market_cap_percentage']['btc']:.1f}%")


def check_fng():
    r = get("https://api.alternative.me/fng/", params={"limit": 1})
    d = r.json()["data"][0]
    return "OK", f"{d['value']} ({d['value_classification']})"


def check_stablecoins():
    r = get("https://stablecoins.llama.fi/stablecoins", params={"includePrices": "true"})
    peg = r.json().get("peggedAssets", [])
    total = sum(a.get("circulating", {}).get("peggedUSD", 0) or 0 for a in peg)
    return "OK", f"{len(peg)} assets, ${total/1e9:.0f}B circulating"


def check_stooq(sym: str, label: str):
    r = get(f"https://stooq.com/q/l/", params={"s": sym, "f": "sd2t2ohlcv", "h": "", "e": "csv"})
    lines = r.text.strip().splitlines()
    if len(lines) < 2 or "N/D" in lines[1]:
        return "EMPTY", f"no data for '{sym}'  <-- check symbol"
    return "OK", lines[1][:60]


def check_yahoo_zq():
    """The one input FedWatch actually needs."""
    r = get("https://query1.finance.yahoo.com/v8/finance/chart/ZQ=F",
            params={"range": "5d", "interval": "1d"})
    res = r.json().get("chart", {}).get("result")
    if not res:
        return "EMPTY", "no chart result"
    closes = [c for c in res[0]["indicators"]["quote"][0]["close"] if c]
    return ("OK", f"ZQ=F last {closes[-1]:.4f} -> implied {100-closes[-1]:.3f}%") if closes else ("EMPTY", "no closes")


def check_yahoo_zq_chain():
    """Individual contract months - ticker format is the risky part."""
    from fedwatch import zq_symbol
    import datetime as dt
    today = dt.date.today()
    y, m = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
    sym = zq_symbol(y, m, "yahoo")
    try:
        r = get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}",
                params={"range": "5d", "interval": "1d"})
        res = r.json().get("chart", {}).get("result")
        if not res:
            return "FAIL", f"'{sym}' not recognised  <-- try without .CBT"
        closes = [c for c in res[0]["indicators"]["quote"][0]["close"] if c]
        return "OK", f"{sym} = {closes[-1]:.4f}"
    except requests.HTTPError:
        return "FAIL", f"'{sym}' rejected  <-- ticker format needs fixing"


def check_farside():
    r = get("https://farside.co.uk/btc/")
    ok = "<table" in r.text.lower()
    return ("OK", f"{len(r.text)//1000}KB, table present") if ok else ("WARN", "no table found - layout changed?")


# --------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------

checks: list[Check] = []

for sid, label in FRED_SERIES.items():
    checks.append(Check(f"{sid:<20} {label}", "FRED",
                        lambda s=sid: check_fred(s),
                        critical="UNVERIFIED" not in label))

checks += [
    Check("bond_yields_benchmark", "BoC", lambda: check_boc_group("bond_yields_benchmark")),
    Check("FXUSDCAD", "BoC", lambda: check_boc_series("FXUSDCAD")),
    Check("V39079  policy rate [UNVERIFIED]", "BoC", lambda: check_boc_series("V39079"), False),
    Check("CBC20210 policy alt  [UNVERIFIED]", "BoC", lambda: check_boc_series("CBC20210"), False),
    Check("AVG.INTWO  CORRA     [UNVERIFIED]", "BoC", lambda: check_boc_series("AVG.INTWO"), False),
    Check("group discovery dump", "BoC", check_boc_list),

    Check("WDS reachable", "StatCan", check_statcan_alive),
    Check("18-10-0004  CPI", "StatCan", lambda: check_statcan_cube("18-10-0004-01", "CPI")),
    Check("14-10-0287  LFS", "StatCan", lambda: check_statcan_cube("14-10-0287-01", "LFS")),
    Check("36-10-0434  GDP monthly", "StatCan", lambda: check_statcan_cube("36-10-0434-01", "GDP")),

    Check("Reverse repo", "NY Fed", check_nyfed_rrp),
    Check("EFFR", "NY Fed", check_nyfed_effr),
    Check("TGA daily balance", "Treasury", check_treasury_tga),

    Check("simple/price", "CoinGecko", check_coingecko_simple),
    Check("global", "CoinGecko", check_coingecko_global),
    Check("Fear & Greed", "Alt.me", check_fng),
    Check("stablecoin supply", "DefiLlama", check_stablecoins),


    Check("ZQ=F front month", "Yahoo", check_yahoo_zq),
    Check("ZQ contract chain", "Yahoo", check_yahoo_zq_chain),
    Check("BTC ETF flow table", "Farside", check_farside, False),
]


def main() -> int:
    print(f"\nVerifying {len(checks)} endpoints...\n")
    for c in checks:
        run(c)

    counts: dict[str, int] = {}
    current_group = None
    for c, status, value, elapsed in results:
        counts[status] = counts.get(status, 0) + 1
        if c.group != current_group:
            current_group = c.group
            print(f"\n--- {current_group} " + "-" * (60 - len(current_group)))
        mark = {"OK": "  ok  ", "EMPTY": " EMPTY", "FAIL": " FAIL ",
                "WARN": " warn ", "SKIP": " skip "}.get(status, status)
        print(f"[{mark}] {c.name:<38} {value:<45} {elapsed:5.2f}s")

    print("\n" + "=" * 100)
    print("  ".join(f"{k}: {v}" for k, v in sorted(counts.items())))

    blocking = [
        c.name for c, s, _, _ in results
        if s in ("FAIL", "EMPTY") and c.critical
    ]
    if blocking:
        print(f"\n{len(blocking)} CRITICAL failures - fix these before writing schema:")
        for n in blocking:
            print(f"  - {n}")
        return 1

    print("\nAll critical sources verified. Safe to design the schema.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
