"""
Unit tests for browser navigation module.
"""

from unittest.mock import MagicMock
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from skills.profile_scraper.page_readiness import navigate_to_profile


def test_navigate_to_profile_invalid_urls():
    mock_page = MagicMock()
    # Empty URL
    assert navigate_to_profile(mock_page, "") is False
    mock_page.goto.assert_not_called()

    # Non-LinkedIn URL
    assert navigate_to_profile(mock_page, "https://github.com/torvalds") is False
    mock_page.goto.assert_not_called()

    # Non-profile LinkedIn URL
    assert navigate_to_profile(mock_page, "https://www.linkedin.com/feed/") is False
    mock_page.goto.assert_not_called()


def test_navigate_to_profile_valid_url():
    mock_page = MagicMock()
    url = "https://www.linkedin.com/in/satyanadella"
    success = navigate_to_profile(mock_page, url, timeout_ms=30000)

    assert success is True
    mock_page.goto.assert_called_once_with(url, wait_until="domcontentloaded", timeout=30000)


def test_navigate_to_profile_timeout_handling():
    mock_page = MagicMock()
    mock_page.goto.side_effect = PlaywrightTimeoutError("Navigation timed out")
    url = "https://www.linkedin.com/in/satyanadella"

    success = navigate_to_profile(mock_page, url, timeout_ms=5000)
    assert success is False
