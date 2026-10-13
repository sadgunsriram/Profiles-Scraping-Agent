import httpx

email_key = "8fd7c133ff3a46eca37e6bdaa6fee5af"
phone_key = "a3b487fcfcb941b5a320a912bf26933b"

print("Checking Abstract Email Verification API Key...")
email_url = f"https://emailvalidation.abstractapi.com/v1/?api_key={email_key}&email=test@example.com"
try:
    resp = httpx.get(email_url, timeout=10)
    print(f"Status Code: {resp.status_code}")
    print(f"Headers: {dict(resp.headers)}")
    if resp.status_code == 200:
        data = resp.json()
        print("Success! Response:")
        print(data)
    else:
        print(f"Failure: {resp.text}")
except Exception as e:
    print(f"Error checking email API: {e}")

print("\nChecking Abstract Phone Validation API Key...")
phone_url = f"https://phonevalidation.abstractapi.com/v1/?api_key={phone_key}&phone=12245550100"
try:
    resp = httpx.get(phone_url, timeout=10)
    print(f"Status Code: {resp.status_code}")
    print(f"Headers: {dict(resp.headers)}")
    if resp.status_code == 200:
        data = resp.json()
        print("Success! Response:")
        print(data)
    else:
        print(f"Failure: {resp.text}")
except Exception as e:
    print(f"Error checking phone API: {e}")
