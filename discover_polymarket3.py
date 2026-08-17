import requests

headers = {"User-Agent": "market-dashboard-verify/0.1"}

r = requests.get(
    "https://gamma-api.polymarket.com/events",
    params={"slug": "fed-decision-in-september-762"},
    headers=headers,
    timeout=15,
)
print(f"HTTP {r.status_code}\n")

data = r.json()
event = data[0]
print(f"Title: {event.get('title')}")
print(f"End date: {event.get('endDate')}\n")

for m in event.get("markets", []):
    print(f"  Question: {m.get('question')}")
    print(f"  Outcomes: {m.get('outcomes')}")
    print(f"  Outcome prices: {m.get('outcomePrices')}")
    print()
