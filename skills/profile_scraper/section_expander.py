"""
section_expander.py — Section expansion module for authorized LinkedIn profile scraping.
Expands 'Show more', 'see more', and expandable profile sections dynamically.
"""

from loguru import logger
from playwright.sync_api import Page

from skills.profile_scraper.selectors import (
    ABOUT_SECTION_SELECTORS,
    EXPAND_SEE_MORE_SELECTORS,
    EXPERIENCE_SECTION_SELECTORS,
    SKILLS_SECTION_SELECTORS,
    PROJECTS_SECTION_SELECTORS
)


def expand_about_section(page: Page) -> None:
    """
    Expands the collapsed About section if a legitimate 'see more' toggle exists.
    """
    about_card = None
    for sel in ABOUT_SECTION_SELECTORS:
        try:
            cand = page.locator(sel).first
            if cand.count() > 0 and cand.is_visible():
                about_card = cand
                break
        except Exception:
            continue

    if not about_card:
        return

    for sel in EXPAND_SEE_MORE_SELECTORS:
        try:
            toggle = about_card.locator(sel).first
            if toggle.is_visible():
                logger.debug(f"[SectionExpander] Expanding About section via '{sel}'")
                toggle.scroll_into_view_if_needed(timeout=1500)
                toggle.click(timeout=1500)
                page.wait_for_timeout(250)
                break
        except Exception:
            continue


def expand_experience_descriptions(page: Page) -> None:
    """
    Expands inline 'see more' description buttons within the Experience section.
    """
    exp_card = None
    for sel in EXPERIENCE_SECTION_SELECTORS:
        try:
            cand = page.locator(sel).first
            if cand.count() > 0 and cand.is_visible():
                exp_card = cand
                break
        except Exception:
            continue

    if not exp_card:
        return

    try:
        toggles = exp_card.locator("button.inline-show-more-text__button, button:has-text('see more'), button:has-text('more')")
        count = toggles.count()
        for i in range(min(count, 8)):
            toggle = toggles.nth(i)
            if toggle.is_visible():
                try:
                    toggle.click(timeout=1000)
                    page.wait_for_timeout(100)
                except Exception:
                    pass
    except Exception as e:
        logger.debug(f"[SectionExpander] Note expanding experience descriptions: {e}")


def expand_skills_section(page: Page) -> None:
    """
    Expands inline 'Show all ... skills' button if present without opening full modal dialog.
    """
    for sel in SKILLS_SECTION_SELECTORS:
        try:
            skill_card = page.locator(sel).first
            if skill_card.count() > 0 and skill_card.is_visible():
                see_more_btn = skill_card.locator("button.inline-show-more-text__button, button:has-text('more')").first
                if see_more_btn.count() > 0 and see_more_btn.is_visible():
                    see_more_btn.click(timeout=1000)
                    page.wait_for_timeout(150)
                break
        except Exception:
            continue
