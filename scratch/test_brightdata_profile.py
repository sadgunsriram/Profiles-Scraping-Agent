import sys
import os

# Ensure the workspace and skills folders are in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import skills.profile_scraper.scraper as scraper

url = "https://www.linkedin.com/in/paolo-di-pinto-70408483"
print(f"Calling scraper.brightdata_linkedin_profile with: {url}")
profile = scraper.brightdata_linkedin_profile(url)

print("\n--- Scraped Profile Details ---")
for k, v in profile.items():
    print(f"{k}: {v}")

if "error" in profile:
    print("\nTest Failed! Error encountered:", profile["error"])
    sys.exit(1)
else:
    print("\nTest Passed! Profile scraped and parsed successfully.")
