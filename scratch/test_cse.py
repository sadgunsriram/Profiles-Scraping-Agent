import httpx
import os
from dotenv import load_dotenv

load_dotenv()
cse_key = os.getenv("GOOGLE_CSE_API_KEY") or os.getenv("CSE_KEY")
cse_id = os.getenv("GOOGLE_CSE_ID") or os.getenv("CSE_ID")

print(f"Testing Google CSE ID: {cse_id}")
print(f"Testing Google CSE Key: {cse_key}")

try:
    resp = httpx.get(
        "https://www.googleapis.com/customsearch/v1",
        params={
            "key": cse_key,
            "cx": cse_id,
            "q": "John Doe GitHub"
        },
        timeout=10.0
    )
    print(f"Status Code: {resp.status_code}")
    print("Response text snippet:")
    print(resp.text[:500])
except Exception as e:
    print(f"Error testing Google CSE: {e}")
