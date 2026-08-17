import requests

BASE = "https://www150.statcan.gc.ca/t1/wds/rest"
HEADERS = {
    "User-Agent": "market-dashboard-verify/0.1",
    "Content-Type": "application/json",
    "Accept": "application/json",
}
KEYWORDS = ["unemployment rate", "canada", "both sexes", "15 years and over", "seasonally adjusted"]

r = requests.post(f"{BASE}/getCubeMetadata", json=[{"productId": 14100287}], headers=HEADERS, timeout=20)
body = r.json()[0]
if body.get("status") != "SUCCESS":
    print("FAILED:", body)
else:
    obj = body["object"]
    print(f"Title: {obj.get('cubeTitleEn')}")
    for dim in obj.get("dimension", []):
        members = dim.get("member", [])
        matches = [m for m in members if any(k in m.get("memberNameEn","").lower() for k in KEYWORDS)]
        shown = matches if matches else members[:15]
        print(f"\nDimension: {dim.get('dimensionNameEn')}  ({len(members)} total members)")
        for m in shown:
            print(f"   [{m.get('memberId')}] {m.get('memberNameEn')}")
