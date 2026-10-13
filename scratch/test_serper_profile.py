import httpx
import os
import json
from dotenv import load_dotenv

load_dotenv("c:/Users/USER/.openclaw/workspace/profile_scraping_agent/.env")
key = os.getenv("SERPER_API_KEY")
print("Key:", bool(key))

resp = httpx.post(
    "https://google.serper.dev/search",
    headers={"X-API-KEY": key, "Content-Type": "application/json"},
    json={"q": 'site:linkedin.com/in/deontelee93'},
    timeout=15.0
)
data = resp.json()
print(json.dumps(data, indent=2))
