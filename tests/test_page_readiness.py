"""
Unit tests for event-based profile page readiness checks.
"""

from unittest.mock import MagicMock
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from skills.profile_scraper.page_readiness import wait_for_profile_ready


def test_wait_for_profile_ready_success():
    mock_page = MagicMock()
    mock_page.url = "https://www.linkedin.com/in/test-candidate"

    mock_locator = MagicMock()
    mock_locator.wait_for.return_value = None
    mock_page.locator.return_value.first = mock_locator

    is_ready, reason = wait_for_profile_ready(mock_page, timeout_ms=5000)
    assert is_ready is True
    assert reason == "READY"


def test_wait_for_profile_ready_checkpoint_detected():
    mock_page = MagicMock()
    mock_page.url = "https://www.linkedin.com/checkpoint/challenge/12345"

    is_ready, reason = wait_for_profile_ready(mock_page, timeout_ms=5000)
    assert is_ready is False
    assert reason == "CHECKPOINT_DETECTED"


def test_wait_for_profile_ready_login_detected():
    mock_page = MagicMock()
    mock_page.url = "https://www.linkedin.com/login?fromSignIn=true"

    is_ready, reason = wait_for_profile_ready(mock_page, timeout_ms=5000)
    assert is_ready is False
    assert reason == "LOGIN_OR_AUTHWALL"


def test_wait_for_profile_ready_timeout():
    mock_page = MagicMock()
    mock_page.url = "https://www.linkedin.com/in/test-candidate"

    mock_locator = MagicMock()
    mock_locator.wait_for.side_effect = PlaywrightTimeoutError("Element not found")

    mock_body = MagicMock()
    mock_body.inner_text.return_value = ""

    def locator_dispatcher(sel):
        if sel == "body":
            return mock_body
        mock_obj = MagicMock()
        mock_obj.first = mock_locator
        return mock_obj

    mock_page.locator.side_effect = locator_dispatcher

    is_ready, reason = wait_for_profile_ready(mock_page, timeout_ms=1000)
    assert is_ready is False
    assert reason == "ELEMENT_TIMEOUT"
