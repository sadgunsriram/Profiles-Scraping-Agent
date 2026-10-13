"""
content_scroller.py — Progressive section-aware scrolling for authorized LinkedIn scraping.

Executes intelligent viewport progression similar to professional workflow automation tools:
- Progressively scrolls down the page section-by-section.
- Waits for lazy-loaded section containers to attach and render.
- Applies natural, variable micro-delays between scroll increments.
- Stabilizes scroll height before concluding.
"""

import time
import random
from typing import List, Optional, Dict, Any
from loguru import logger
from playwright.sync_api import Page


def scroll_profile_progressively(
    page: Page,
    target_selectors: Optional[List[str]] = None,
    max_steps: int = 16
) -> List[Dict[str, Any]]:
    """
    Scrolls the profile page progressively through all standard sections.
    Ensures that dynamically rendered components (Experience, Education, Certifications,
    Projects, Skills, Languages, Volunteer) are detected, rendered, expanded, and marked as processed.

    Returns:
        List of section processing records with status, rendering verification, and expansion actions.
    """
    from skills.profile_scraper.selectors import (
        FEATURED_SECTION_SELECTORS,
        ABOUT_SECTION_SELECTORS,
        EXPERIENCE_SECTION_SELECTORS,
        EDUCATION_SECTION_SELECTORS,
        CERTIFICATIONS_SECTION_SELECTORS,
        PROJECTS_SECTION_SELECTORS,
        SKILLS_SECTION_SELECTORS,
        LANGUAGES_SECTION_SELECTORS,
        VOLUNTEER_SECTION_SELECTORS
    )

    section_definitions = [
        ("about", ABOUT_SECTION_SELECTORS),
        ("featured", FEATURED_SECTION_SELECTORS),
        ("experience", EXPERIENCE_SECTION_SELECTORS),
        ("education", EDUCATION_SECTION_SELECTORS),
        ("certifications", CERTIFICATIONS_SECTION_SELECTORS),
        ("projects", PROJECTS_SECTION_SELECTORS),
        ("skills", SKILLS_SECTION_SELECTORS),
        ("languages", LANGUAGES_SECTION_SELECTORS),
        ("volunteer", VOLUNTEER_SECTION_SELECTORS),
    ]

    logger.debug("[ContentScroller] Starting progressive section-aware viewport scrolling...")

    last_scroll_height = page.evaluate("""() => {
        const scroller = document.querySelector('main#workspace, main, [role="main"]');
        return scroller ? scroller.scrollHeight : document.body.scrollHeight;
    }""")

    processed_sections: List[Dict[str, Any]] = []
    seen_section_names = set()

    for step in range(max_steps):
        found_target = False

        # 1. Detect if any unvisited section container is attached to DOM
        for sec_name, selectors in section_definitions:
            if sec_name in seen_section_names:
                continue

            for selector in selectors:
                try:
                    elem = page.locator(selector).first
                    if elem.count() > 0 and elem.is_visible():
                        logger.debug(f"[ContentScroller] Bringing section '{sec_name}' ({selector}) into viewport (step {step + 1}).")
                        elem.scroll_into_view_if_needed(timeout=1500)
                        seen_section_names.add(sec_name)
                        found_target = True

                        # Micro-delay: wait for dynamic content to render in viewport
                        page.wait_for_timeout(random.randint(400, 700))

                        # Expand applicable inline 'see more' controls for this section
                        expanded_count = 0
                        try:
                            toggles = elem.locator("button.inline-show-more-text__button, button.inline-show-more-text__button--link, button:has-text('see more')")
                            t_count = toggles.count()
                            for i in range(min(t_count, 6)):
                                t_btn = toggles.nth(i)
                                if t_btn.is_visible():
                                    t_btn.click(timeout=600)
                                    page.wait_for_timeout(100)
                                    expanded_count += 1
                        except Exception:
                            pass

                        processed_sections.append({
                            "section": sec_name,
                            "selector": selector,
                            "status": "PROCESSED",
                            "step_reached": step + 1,
                            "expanded_controls": expanded_count
                        })
                        break
                except Exception:
                    continue

            if found_target:
                break

        # 2. If no specific target section was triggered, scroll smoothly downward
        if not found_target:
            scroll_delta = random.randint(600, 800)
            page.evaluate(f"""() => {{
                const scroller = document.querySelector('main#workspace, main, [role="main"]');
                if (scroller && scroller.scrollHeight > scroller.clientHeight) {{
                    scroller.scrollBy(0, {scroll_delta});
                }}
                window.scrollBy(0, {scroll_delta});
            }}""")
            page.wait_for_timeout(random.randint(400, 700))

        # 3. Check for DOM height stabilization
        new_scroll_height = page.evaluate("""() => {
            const scroller = document.querySelector('main#workspace, main, [role="main"]');
            return scroller ? scroller.scrollHeight : document.body.scrollHeight;
        }""")

        if new_scroll_height == last_scroll_height and step >= 6:
            logger.debug(f"[ContentScroller] Document height stabilized at step {step + 1}. Halting scroll.")
            break

        last_scroll_height = new_scroll_height

    # Final brief stabilization pause
    page.wait_for_timeout(300)

    # Record unavailable sections
    for sec_name, _ in section_definitions:
        if sec_name not in seen_section_names:
            processed_sections.append({
                "section": sec_name,
                "selector": "NONE",
                "status": "NOT_PRESENT",
                "step_reached": -1,
                "expanded_controls": 0
            })

    logger.debug(f"[ContentScroller] Progressive scroll completed. Activated sections: {len(seen_section_names)}.")
    return processed_sections


def scroll_profile_content(page: Page, target_selectors: Optional[List[str]] = None, max_steps: int = 12) -> None:
    """Backward compatibility alias for scroll_profile_progressively."""
    scroll_profile_progressively(page, target_selectors=target_selectors, max_steps=max_steps)
