"""
Configuration module for authorized LinkedIn profile extraction.
Exposes configurable operational limits and timeouts with safe defaults.
"""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class ScraperConfig:
    max_profiles_per_session: int = 25
    max_session_duration_minutes: int = 30
    page_load_timeout: int = 45000  # ms
    element_timeout: int = 10000    # ms
    max_extraction_retries: int = 3
    browser_profile_dir: str = ""
    enable_signalhire_extension: bool = False
    linkedin_username: Optional[str] = None
    linkedin_password: Optional[str] = None
    headless: bool = False


def load_config() -> ScraperConfig:
    """Load configuration from environment variables with sensible defaults."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    default_profile_dir = os.path.join(base_dir, "browser_profile")

    return ScraperConfig(
        max_profiles_per_session=int(os.getenv("MAX_PROFILES_PER_SESSION", "25")),
        max_session_duration_minutes=int(os.getenv("MAX_SESSION_DURATION_MINUTES", "30")),
        page_load_timeout=int(os.getenv("PAGE_LOAD_TIMEOUT", "45000")),
        element_timeout=int(os.getenv("ELEMENT_TIMEOUT", "10000")),
        max_extraction_retries=int(os.getenv("MAX_EXTRACTION_RETRIES", "3")),
        browser_profile_dir=os.getenv("LINKEDIN_BROWSER_PROFILE_DIR", default_profile_dir),
        enable_signalhire_extension=os.getenv("ENABLE_SIGNALHIRE_EXTENSION", "false").lower() in ("true", "1", "yes"),
        linkedin_username=os.getenv("LINKEDIN_USERNAME"),
        linkedin_password=os.getenv("LINKEDIN_PASSWORD"),
        headless=os.getenv("PLAYWRIGHT_HEADLESS", "false").lower() in ("true", "1", "yes")
    )
