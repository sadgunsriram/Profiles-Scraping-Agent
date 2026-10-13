"""
Session monitor module for tracking authorized browser session health,
detecting challenges, login expiration, and enforcing operational limits.
"""

import time
from typing import Optional, Tuple
from loguru import logger
from skills.profile_scraper.config import ScraperConfig, load_config


class SessionTerminatedException(Exception):
    """Base exception for clean session termination."""
    pass


class SessionLimitExceededException(SessionTerminatedException):
    """Raised when profile count or session duration limits are exceeded."""
    pass


class AuthenticationRequiredException(SessionTerminatedException):
    """Raised when authentication expires or login is required."""
    pass


class CheckpointDetectedException(SessionTerminatedException):
    """Raised when an unexpected checkpoint, CAPTCHA, or verification challenge is detected."""
    pass


class ConsecutiveFailureLimitException(SessionTerminatedException):
    """Raised when repeated profile extraction failures exceed allowed threshold."""
    pass


class SessionMonitor:
    """
    Monitors browser session health and enforces operational limits.
    Stops processing cleanly before account restrictions or data corruption occur.
    """

    def __init__(self, config: Optional[ScraperConfig] = None):
        self.config = config or load_config()
        self.session_start_time: float = time.time()
        self.profiles_processed: int = 0
        self.consecutive_failures: int = 0
        self.total_failures: int = 0

    def reset(self):
        """Reset monitoring counters."""
        self.session_start_time = time.time()
        self.profiles_processed = 0
        self.consecutive_failures = 0
        self.total_failures = 0

    def check_limits(self) -> None:
        """Check if session duration or profile count limits have been reached."""
        elapsed_minutes = (time.time() - self.session_start_time) / 60.0
        if elapsed_minutes >= self.config.max_session_duration_minutes:
            msg = (
                f"Session duration limit reached: {elapsed_minutes:.1f} minutes elapsed "
                f"(Limit: {self.config.max_session_duration_minutes}m). Stopping cleanly."
            )
            logger.warning(f"[SessionMonitor] {msg}")
            raise SessionLimitExceededException(msg)

        if self.profiles_processed >= self.config.max_profiles_per_session:
            msg = (
                f"Max profiles per session reached: {self.profiles_processed} profiles "
                f"(Limit: {self.config.max_profiles_per_session}). Stopping cleanly."
            )
            logger.info(f"[SessionMonitor] {msg}")
            raise SessionLimitExceededException(msg)

    def check_page_health(self, page) -> None:
        """
        Inspects the page URL and DOM for authentication/challenge issues.
        Raises specific SessionTerminatedException subclasses if an issue is found.
        """
        curr_url = page.url.lower()

        # 1. Check for verification / checkpoint / challenge URLs
        checkpoint_indicators = [
            "/checkpoint/",
            "urn:li:page:d_checkpoint",
            "challenge",
            "/security-check",
            "captcha",
            "identity-verification"
        ]
        for indicator in checkpoint_indicators:
            if indicator in curr_url:
                msg = f"Security verification or challenge page detected: {page.url}"
                logger.error(f"[SessionMonitor] {msg}")
                raise CheckpointDetectedException(msg)

        # 2. Check for login / session expiry URLs
        login_indicators = [
            "/login",
            "/uas/login",
            "linkedin.com/signup",
            "/authwall"
        ]
        for indicator in login_indicators:
            if indicator in curr_url:
                msg = f"Session expired or login redirect detected: {page.url}"
                logger.warning(f"[SessionMonitor] {msg}")
                raise AuthenticationRequiredException(msg)

        # 3. Check page title or DOM text for verification signals
        try:
            title = (page.title() or "").lower()
            if any(term in title for term in ["security verification", "quick security check", "challenge", "checkpoint"]):
                msg = f"Security checkpoint detected in page title: '{page.title()}'"
                logger.error(f"[SessionMonitor] {msg}")
                raise CheckpointDetectedException(msg)
        except Exception:
            pass

    def record_success(self, profile_url: str = "") -> None:
        """Record a successfully extracted profile."""
        self.profiles_processed += 1
        self.consecutive_failures = 0
        logger.info(
            f"[SessionMonitor] Profile processed successfully "
            f"({self.profiles_processed}/{self.config.max_profiles_per_session})"
        )

    def record_failure(self, profile_url: str = "", reason: str = "") -> None:
        """Record a profile extraction failure and enforce consecutive failure limits."""
        self.consecutive_failures += 1
        self.total_failures += 1
        logger.warning(
            f"[SessionMonitor] Extraction failure ({self.consecutive_failures}/"
            f"{self.config.max_extraction_retries}) on '{profile_url}': {reason}"
        )

        if self.consecutive_failures >= self.config.max_extraction_retries:
            msg = (
                f"Consecutive extraction failure limit exceeded ({self.consecutive_failures} "
                f"failures). Halting session to protect account and preserve existing data."
            )
            logger.critical(f"[SessionMonitor] {msg}")
            raise ConsecutiveFailureLimitException(msg)

    def get_summary(self) -> dict:
        """Return session statistics dictionary."""
        elapsed_sec = time.time() - self.session_start_time
        return {
            "elapsed_minutes": round(elapsed_sec / 60.0, 2),
            "profiles_processed": self.profiles_processed,
            "consecutive_failures": self.consecutive_failures,
            "total_failures": self.total_failures,
            "max_profiles_limit": self.config.max_profiles_per_session,
            "max_duration_limit_minutes": self.config.max_session_duration_minutes,
        }
