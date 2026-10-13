import httpx
import json

api_key = "22730a00-b373-46b9-8f37-71e7d931d5a0"
headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

# Try the trigger endpoint with standard LinkedIn dataset_id
url = "https://api.brightdata.com/datasets/v3/trigger"
params = {
    "dataset_id": "gd_l1viktl72bvl7bjuj0" # standard public dataset ID for linkedin profiles
}
payload = [
    {"url": "https://www.linkedin.com/in/paolo-di-pinto-70408483"}
]

print("Testing trigger endpoint...")
try:
    resp = httpx.post(url, headers=headers, params=params, json=payload, timeout=20)
    print(f"Status Code: {resp.status_code}")
    print(f"Response Body: {resp.text}")
except Exception as e:
    print(f"Error: {e}")
