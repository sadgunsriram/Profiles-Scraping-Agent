import os
import sys
import json
import httpx
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

load_dotenv()

api_key = os.getenv("BRIGHTDATA_API_KEY") or os.getenv("SERPAPI_KEY")
url = "https://www.linkedin.com/in/claudiadeluna"

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

scrape_url = "https://api.brightdata.com/datasets/v3/scrape"
params = {
    "dataset_id": "gd_l1viktl72bvl7bjuj0"
}
payload = [{"url": url}]

print("Querying Bright Data...")
resp = httpx.post(
    scrape_url,
    headers=headers,
    params=params,
    json=payload,
    timeout=60
)
print("Scrape response status:", resp.status_code)
if resp.status_code == 200:
    data = resp.json()
    # Save raw json output
    output_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'claudia_raw.json'))
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Successfully saved raw JSON response to {output_path}")
else:
    print("Error response text:", resp.text)
