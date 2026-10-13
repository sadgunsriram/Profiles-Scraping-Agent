"""
Page readiness and navigation module for authorized LinkedIn profile scraping.
Implements event-driven DOM readiness checks, eliminating arbitrary fixed sleeps.
"""

from typing import Tuple
from loguru import logger
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError


def navigate_to_profile(page: Page, url: str, timeout_ms: int = 45000) -> bool:
    """
    Navigates to candidate profile URL with domcontentloaded wait state.
    """
    if not url or "linkedin.com/in/" not in url.lower():
        logger.warning(f"[PageReadiness] Invalid LinkedIn URL provided: {url}")
        return False

    try:
        logger.info(f"[PageReadiness] Navigating to: {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        return True
    except PlaywrightTimeoutError:
        logger.warning(f"[PageReadiness] Navigation timeout ({timeout_ms}ms) navigating to: {url}")
        return False
    except Exception as e:
        logger.error(f"[PageReadiness] Navigation error on {url}: {e}")
        return False


def wait_for_profile_ready(page: Page, timeout_ms: int = 10000) -> Tuple[bool, str]:
    """
    Awaits required DOM elements to verify profile view is fully loaded and interactive.
    Returns (True, "READY") if page is ready, or (False, reason) if authwall/checkpoint/timeout.
    """
    curr_url = page.url.lower()

    # 1. Immediate URL redirection checks
    if "/checkpoint/" in curr_url or "urn:li:page:d_checkpoint" in curr_url:
        return False, "CHECKPOINT_DETECTED"
    if "/login" in curr_url or "/uas/login" in curr_url or "/authwall" in curr_url:
        return False, "LOGIN_OR_AUTHWALL"

    # 2. Event-driven wait for core profile layout elements using centralized selectors
    from skills.profile_scraper.selectors import PAGE_READINESS_SELECTORS

    for selector in PAGE_READINESS_SELECTORS:
        try:
            locator = page.locator(selector).first
            locator.wait_for(state="attached", timeout=timeout_ms)
            logger.debug(f"[PageReadiness] Target profile element '{selector}' confirmed attached.")
            return True, "READY"
        except PlaywrightTimeoutError:
            continue
        except Exception as e:
            logger.debug(f"[PageReadiness] Readiness check error on '{selector}': {e}")
            continue

    # 3. Fallback: check if page body has substantial content
    try:
        body_text = page.locator("body").inner_text(timeout=2000)
        if len(body_text) > 200 and ("experience" in body_text.lower() or "activity" in body_text.lower() or "about" in body_text.lower()):
            return True, "READY_FALLBACK_TEXT"
    except Exception:
        pass

    return False, "ELEMENT_TIMEOUT"
