import requests

HEADERS_STATCAN = {
    "User-Agent": "market-dashboard-verify/0.1",
    "Content-Type": "application/json",
    "Accept": "application/json",
}
HEADERS_BOC = {"User-Agent": "market-dashboard-verify/0.1"}

# --- 1. Resolve Canada unemployment rate vector ---
print("=== Canada unemployment rate vector ===")
coord = "1.7.1.1.1.1.0.0.0.0"  # Geography.LFchar.Gender.AgeGroup.Statistics.DataType
r = requests.post(
    "https://www150.statcan.gc.ca/t1/wds/rest/getSeriesInfoFromCubePidCoord",
    json=[{"productId": 14100287, "coordinate": coord}],
    headers=HEADERS_STATCAN, timeout=20,
)
body = r.json()[0]
if body.get("status") == "SUCCESS":
    obj = body["object"]
    print(f"  vector: v{obj.get('vectorId')}")
    print(f"  title:  {obj.get('SeriesTitleEn')}")
else:
    print(f"  FAILED: {body}")

# --- 2. Find the real BoC group name for core inflation ---
print("\n=== BoC groups matching core/trim/median/cpi ===")
r = requests.get("https://www.bankofcanada.ca/valet/lists/groups/json", headers=HEADERS_BOC, timeout=20)
groups = r.json().get("groups", {})
for k, v in groups.items():
    label = v.get("label", "")
    if any(t in k.lower() or t in label.lower() for t in ("core", "trim", "median", "cpi")):
        print(f"  [{k}]  {label}")
