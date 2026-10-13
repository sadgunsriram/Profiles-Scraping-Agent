import os, sys
sys.path.insert(0, ".")
from dotenv import load_dotenv
load_dotenv(".env")
from skills.profile_scraper.signalhire_client import SignalHireClient

client = SignalHireClient()
print("SignalHire Enabled:", client.enabled)
print("Pool Status:", client.get_pool_status())

