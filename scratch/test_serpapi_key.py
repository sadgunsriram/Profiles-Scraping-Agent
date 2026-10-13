import httpx
import os
from dotenv import load_dotenv

load_dotenv()
serpapi_key = os.getenv("SERPAPI_API_KEY") or os.getenv("SERPAPI_KEY")
print(f"Testing SerpAPI key: {serpapi_key}")

try:
    resp = httpx.get(
        "https://serpapi.com/search",
        params={
            "engine": "google",
            "q": "Python Developer",
            "api_key": serpapi_key
        },
        timeout=10.0
    )
    print(f"Status Code: {resp.status_code}")
    print("Response JSON snippet:")
    print(resp.text[:500])
except Exception as e:
    print(f"Error testing SerpAPI: {e}")
