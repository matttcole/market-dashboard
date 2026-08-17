import requests

headers = {"User-Agent": "market-dashboard-verify/0.1"}

r = requests.get(
    "https://gamma-api.polymarket.com/events",
    params={
        "tag_slug": "fed-rates",
        "active": "true",
        "closed": "false",
        "limit": 20,
    },
    headers=headers,
    timeout=15,
)
print(f"HTTP {r.status_code}\n")

data = r.json()
print(f"Got {len(data)} active event(s)\n")

for event in data:
    print(f"Title: {event.get('title')}")
    print(f"  Slug: {event.get('slug')}")
    print(f"  End date: {event.get('endDate')}")
    print(f"  # markets: {len(event.get('markets', []))}")
    print()
