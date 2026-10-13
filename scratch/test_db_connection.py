"""
test_db_connection.py — Quick Diagnostic to verify PostgreSQL connection.

Usage:
    python scratch/test_db_connection.py
"""

import os
import sys
from dotenv import load_dotenv

sys.path.insert(0, ".")
load_dotenv(".env")

from skills.profile_scraper.database_repository import DatabaseCandidateRepository

def main():
    print("\n" + "=" * 65)
    print("      DATABASE CONNECTION DIAGNOSTIC CHECK")
    print("=" * 65)

    db_enabled = os.getenv("DATABASE_ENABLED", "false").lower() in ("true", "1", "yes")
    raw_db_url = os.getenv("DATABASE_URL", "").strip()

    print(f"DATABASE_ENABLED : {db_enabled}")
    if raw_db_url:
        # Mask password in URL for safe printing
        masked_url = raw_db_url
        if "@" in masked_url and ":" in masked_url.split("@")[0]:
            prefix, rest = masked_url.split("@", 1)
            scheme_user = prefix.split(":")[0] + ":" + prefix.split(":")[1]
            masked_url = f"{scheme_user}:****@{rest}"
        print(f"DATABASE_URL     : {masked_url}")
    else:
        print("DATABASE_URL     : (Not Set)")

    if not db_enabled:
        print("\n[!] Note: DATABASE_ENABLED is currently 'false' in .env.")
        print("    To enable, set DATABASE_ENABLED=true and provide a valid DATABASE_URL.")
        return

    if not raw_db_url:
        print("\n[!] Error: DATABASE_URL is empty in .env. Please provide a connection string.")
        return

    print("\nConnecting to database and verifying table 'eligible_candidates'...")
    repo = DatabaseCandidateRepository()

    if repo.enabled:
        print(f" [OK] Successfully connected to {repo.dialect_name.upper()} database!")
        print(f" [OK] Schema validated: Table 'eligible_candidates' is ready.")
        count = repo.get_eligible_count()
        print(f" [OK] Current Eligible Candidates stored: {count}")
    else:
        print(" [X] Database connection failed. Please double check credentials/host in DATABASE_URL.")

    print("=" * 65 + "\n")

if __name__ == "__main__":
    main()
