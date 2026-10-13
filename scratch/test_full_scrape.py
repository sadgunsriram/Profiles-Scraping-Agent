import os
import sys
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from skills.profile_scraper.scraper import AuthorizedLinkedInProvider

provider = AuthorizedLinkedInProvider()
test_url = "https://www.linkedin.com/in/isaiahmiller"
print(f"Calling fetch_profile for {test_url}...")
res = provider.fetch_profile(test_url, require_open_to_work=True)
print("Result keys:", list(res.keys()) if isinstance(res, dict) else type(res))
if "error" in res:
    print("Error:", res.get("error"))
    print("Reason:", res.get("reason"))
else:
    print("Full Name:", res.get("full_name"))
    print("Headline:", res.get("headline"))
    print("Location:", res.get("location"))
    print("Open to Work:", res.get("is_open_to_work"))
    print("Experience Count:", len(res.get("experience_history", [])))
    print("Skills Count:", len(res.get("skills", [])))
