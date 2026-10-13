import sys, os
sys.path.insert(0, ".")
from dotenv import load_dotenv
load_dotenv(".env")

import skills.profile_scraper.scraper as scraper

results = scraper.search_all_sources("Cloud Engineer", num=2, page=1, mode="linkedin")
print(f"Total results: {len(results)}")
for r in results:
    print("LINK:", r.get("link"))
    print("TITLE:", r.get("title"))
    print("SNIPPET:", r.get("snippet"))
    print("-" * 40)
