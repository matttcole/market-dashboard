"""
Debug M-X page - get table content
"""
import requests
from bs4 import BeautifulSoup

url = "https://www.m-x.ca/en/trading/tools/canadian-interest-rate-expectations"

headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}

try:
    r = requests.get(url, timeout=10, headers=headers)
    soup = BeautifulSoup(r.text, "html.parser")
    
    # Find all tables and print their content
    tables = soup.find_all("table")
    print(f"Found {len(tables)} tables\n")
    
    for i, table in enumerate(tables):
        print(f"--- TABLE {i+1} ---")
        print(table.get_text()[:1000])
        print("\n")
    
    # Also look for any text mentioning "BoC"
    text = soup.get_text()
    lines = [line.strip() for line in text.split('\n') if line.strip() and ('BoC' in line or 'Hike' in line or 'Cut' in line or 'Hold' in line or '%' in line)]
    
    print("--- Lines with BoC/Hike/Cut/Hold/% ---")
    for line in lines[:30]:
        print(line)
    
except Exception as e:
    print(f"Error: {e}")
