"""
Unit tests for session monitoring, challenge detection, and operational limit enforcement.
"""

import time
import pytest
from unittest.mock import MagicMock
from skills.profile_scraper.config import ScraperConfig
from skills.profile_scraper.session_monitor import (
    SessionMonitor,
    SessionLimitExceededException,
    CheckpointDetectedException,
    AuthenticationRequiredException,
    ConsecutiveFailureLimitException
)


def test_session_monitor_profile_limit():
    config = ScraperConfig(max_profiles_per_session=2)
    monitor = SessionMonitor(config)

    monitor.record_success("https://linkedin.com/in/c1")
    monitor.check_limits()  # 1 processed, limit 2 -> ok

    monitor.record_success("https://linkedin.com/in/c2")
    # 2 processed -> limit reached
    with pytest.raises(SessionLimitExceededException):
        monitor.check_limits()


def test_session_monitor_duration_limit():
    config = ScraperConfig(max_session_duration_minutes=1)
    monitor = SessionMonitor(config)
    # Simulate session start 70 seconds ago
    monitor.session_start_time = time.time() - 70

    with pytest.raises(SessionLimitExceededException):
        monitor.check_limits()


def test_session_monitor_challenge_detected():
    monitor = SessionMonitor()
    mock_page = MagicMock()
    mock_page.url = "https://www.linkedin.com/checkpoint/challenge/I289291"
    mock_page.title.return_value = "Security Verification | LinkedIn"

    with pytest.raises(CheckpointDetectedException):
        monitor.check_page_health(mock_page)


def test_session_monitor_auth_expiry_detected():
    monitor = SessionMonitor()
    mock_page = MagicMock()
    mock_page.url = "https://www.linkedin.com/uas/login?session_redirect=..."
    mock_page.title.return_value = "LinkedIn Login"

    with pytest.raises(AuthenticationRequiredException):
        monitor.check_page_health(mock_page)


def test_session_monitor_consecutive_failures():
    config = ScraperConfig(max_extraction_retries=3)
    monitor = SessionMonitor(config)

    monitor.record_failure("url1", "timeout")
    assert monitor.consecutive_failures == 1

    monitor.record_failure("url2", "timeout")
    assert monitor.consecutive_failures == 2

    # 3rd failure reaches limit and raises ConsecutiveFailureLimitException
    with pytest.raises(ConsecutiveFailureLimitException):
        monitor.record_failure("url3", "timeout")


def test_session_monitor_success_resets_consecutive_failures():
    config = ScraperConfig(max_extraction_retries=3)
    monitor = SessionMonitor(config)

    monitor.record_failure("url1", "timeout")
    monitor.record_failure("url2", "timeout")
    assert monitor.consecutive_failures == 2

    # Success resets counter
    monitor.record_success("url3")
    assert monitor.consecutive_failures == 0
    assert monitor.profiles_processed == 1
