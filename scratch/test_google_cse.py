import os
import sys
import httpx
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
_env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.env'))
load_dotenv(dotenv_path=_env_path)

def test_cse():
    key = os.getenv("GOOGLE_CSE_API_KEY")
    cx = os.getenv("GOOGLE_CSE_ID")
    
    print(f"Testing Google CSE API connection with key: {key} and CX: {cx}...")
    
    try:
        query = 'site:github.com "Terraform" "USA"'
        resp = httpx.get(
            "https://www.googleapis.com/customsearch/v1",
            params={
                "key": key,
                "cx": cx,
                "q": query,
                "num": 3
            },
            timeout=10.0
        )
        print(f"Response Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            items = data.get("items", [])
            print(f"Success! Retrieved {len(items)} results programmatically using your Custom Search Engine.")
            for i, item in enumerate(items):
                print(f"  Result {i+1}: {item.get('link')}")
        else:
            print(f"Error Response Body: {resp.text}")
    except Exception as e:
        print(f"HTTP Exception: {e}")

if __name__ == '__main__':
    test_cse()
