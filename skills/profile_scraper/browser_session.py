"""
Browser session management module for authorized LinkedIn extraction.
Manages Playwright persistent context lifecycle, launch arguments, and clean shutdown.
"""

import os
from typing import Optional
from loguru import logger
from playwright.sync_api import sync_playwright, BrowserContext, Page, Playwright

from skills.profile_scraper.config import ScraperConfig, load_config


class BrowserSessionManager:
    """
    Manages the lifecycle of an authorized Playwright persistent browser context.
    """

    def __init__(self, config: Optional[ScraperConfig] = None):
        self.config = config or load_config()
        self._playwright: Optional[Playwright] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    def start_session(self) -> Page:
        """
        Launches the persistent browser context and returns a prepared Page.
        """
        profile_dir = os.path.abspath(self.config.browser_profile_dir)
        if not os.path.exists(profile_dir):
            raise FileNotFoundError(
                f"LinkedIn persistent browser profile directory not found at: {profile_dir}. "
                "Please ensure the profile directory is created with save_linkedin_session.py."
            )

        logger.info(f"[BrowserSession] Launching standard persistent context from: {profile_dir}")

        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu"
        ]

        # SignalHire extension integration if enabled
        if self.config.enable_signalhire_extension:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            ext_dir = os.path.abspath(os.path.join(base_dir, "extensions", "signalhire"))
            if os.path.exists(os.path.join(ext_dir, "manifest.json")):
                logger.info(f"[BrowserSession] Attaching SignalHire extension from: {ext_dir}")
                launch_args.extend([
                    f"--disable-extensions-except={ext_dir}",
                    f"--load-extension={ext_dir}",
                ])

        self._playwright = sync_playwright().start()
        self._context = self._playwright.chromium.launch_persistent_context(
            profile_dir,
            headless=self.config.headless,
            channel="chrome",
            viewport={"width": 1280, "height": 800},
            args=launch_args,
            ignore_default_args=["--enable-automation"]
        )

        # Retrieve existing page or create new page
        pages = self._context.pages
        self._page = pages[0] if pages else self._context.new_page()

        # Set default timeouts from configuration
        self._page.set_default_timeout(self.config.element_timeout)
        self._page.set_default_navigation_timeout(self.config.page_load_timeout)

        return self._page

    @property
    def page(self) -> Optional[Page]:
        """Returns the active page if initialized."""
        return self._page

    @property
    def context(self) -> Optional[BrowserContext]:
        """Returns the active BrowserContext if initialized."""
        return self._context

    def close(self) -> None:
        """Closes page, browser context, and terminates Playwright gracefully."""
        if self._context:
            try:
                self._context.close()
            except Exception as e:
                logger.warning(f"[BrowserSession] Error closing context: {e}")
            self._context = None

        if self._playwright:
            try:
                self._playwright.stop()
            except Exception as e:
                logger.warning(f"[BrowserSession] Error stopping Playwright: {e}")
            self._playwright = None

        self._page = None
        logger.info("[BrowserSession] Browser session closed cleanly.")

    def __enter__(self):
        return self.start_session()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
