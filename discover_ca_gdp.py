"""
One-time discovery script. Prints StatCan's dimension/member structure for
candidate GDP tables so we can pick the exact vector IDs by hand, instead of
guessing. Doesn't touch market.db.
"""
import requests

BASE = "https://www150.statcan.gc.ca/t1/wds/rest"
HEADERS = {
    "User-Agent": "market-dashboard-verify/0.1",
    "Content-Type": "application/json",
    "Accept": "application/json",
}

def try_metadata(pid_variants, label):
    for pid in pid_variants:
        r = requests.post(
            f"{BASE}/getCubeMetadata",
            json=[{"productId": pid}],
            headers=HEADERS,
            timeout=20,
        )
        print(f"{label}  productId={pid} -> HTTP {r.status_code}")
        if r.status_code != 200:
            print(f"   body: {r.text[:200]}")
            continue
        body = r.json()[0]
        if body.get("status") == "SUCCESS":
            obj = body["object"]
            print(f"\n=== {label}  (productId={pid}) \u2014 SUCCESS ===")
            print(f"Title: {obj.get('cubeTitleEn')}")
            for dim in obj.get("dimension", []):
                print(f"\n  Dimension: {dim.get('dimensionNameEn')}")
                for m in dim.get("member", [])[:30]:
                    print(f"     [{m.get('memberId')}] {m.get('memberNameEn')}")
            return pid
        print(f"   -> {body.get('status')} (trying next)")
    print(f"!! No working productId found for {label}")
    return None

# control case: CPI table, known productId format from verify_sources.py
try_metadata([18100004], "CONTROL: CPI table")

try_metadata([3610010401, 36100104], "GDP expenditure-based, quarterly")
try_metadata([3610043402, 36100434], "GDP by industry, monthly growth rates")
