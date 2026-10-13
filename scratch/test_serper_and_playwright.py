import os
import sys
import httpx
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from skills.profile_scraper.browser_session import BrowserSessionManager
from skills.profile_scraper.scraper import unified_google_search
from skills.profile_scraper.set1_identity import is_search_result_open_to_work

print("=== 1. Testing Serper Query ===")
query = 'site:linkedin.com/in/ ("Network Engineer") ("open to work" OR "#opentowork") ("USA" OR "United States") -inurl:dir'
results = unified_google_search(query, num=3)
print(f"Serper returned {len(results)} results.")
for i, r in enumerate(results):
    title = r.get("title", "")
    link = r.get("link", "")
    snippet = r.get("snippet", "")
    otw_match, otw_reason = is_search_result_open_to_work(r)
    print(f"[{i+1}] {title}")
    print(f"     URL: {link}")
    print(f"     OTW match: {otw_match} ({otw_reason})")

print("\n=== 2. Testing Playwright Session ===")
mgr = BrowserSessionManager()
try:
    print("Launching BrowserSessionManager...")
    page = mgr.start_session()
    print("Browser context launched successfully!")
    test_url = results[0].get("link") if results else "https://www.linkedin.com"
    print(f"Navigating to: {test_url}...")
    page.goto(test_url, timeout=30000)
    page.wait_for_timeout(3000)
    print("Current Page Title:", page.title())
    print("Current Page URL:", page.url)
finally:
    mgr.close()
    print("Browser closed cleanly.")
