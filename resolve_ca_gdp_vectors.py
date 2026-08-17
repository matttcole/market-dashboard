import requests

BASE = "https://www150.statcan.gc.ca/t1/wds/rest"
HEADERS = {
    "User-Agent": "market-dashboard-verify/0.1",
    "Content-Type": "application/json",
    "Accept": "application/json",
}

# coordinate order: Geography.Prices.Seasonal adjustment.Estimates (padded to 10 slots)
coords = {
    "GDP growth rate (q/q, headline)": "1.7.1.30.0.0.0.0.0.0",
    "GDP annualized growth rate": "1.4.1.30.0.0.0.0.0.0",
}

for label, coord in coords.items():
    r = requests.post(
        f"{BASE}/getSeriesInfoFromCubePidCoord",
        json=[{"productId": 36100104, "coordinate": coord}],
        headers=HEADERS,
        timeout=20,
    )
    print(f"\n{label}  (coord {coord}) -> HTTP {r.status_code}")
    body = r.json()[0]
    if body.get("status") == "SUCCESS":
        obj = body["object"]
        print(f"   vector: v{obj.get('vectorId')}")
        print(f"   title:  {obj.get('SeriesTitleEn')}")
    else:
        print(f"   FAILED: {body}")
