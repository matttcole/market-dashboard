import requests

HEADERS = {"User-Agent": "market-dashboard-verify/0.1"}

# --- 1. Verify unemployment vector against known public figure (6.4%, July 2026) ---
print("=== Verify Canada unemployment vector v2062815 ===")
r = requests.post(
    "https://www150.statcan.gc.ca/t1/wds/rest/getDataFromVectorsAndLatestNPeriods",
    json=[{"vectorId": 2062815, "latestN": 3}],
    headers={**HEADERS, "Content-Type": "application/json", "Accept": "application/json"},
    timeout=20,
)
body = r.json()[0]
if body.get("status") == "SUCCESS":
    for pt in body["object"]["vectorDataPoint"]:
        print(f"  {pt['refPer']}  =  {pt['value']}")
else:
    print(f"  FAILED: {body}")

# --- 2. Search BoC's full series list for trim/median/common ---
print("\n=== BoC series matching trim/median/common ===")
r = requests.get("https://www.bankofcanada.ca/valet/lists/series/json", headers=HEADERS, timeout=30)
series = r.json().get("series", {})
for code, info in series.items():
    label = info.get("label", "")
    if any(t in label.lower() for t in ("trim", "median", "common")) and "cpi" in label.lower():
        print(f"  [{code}]  {label}")
