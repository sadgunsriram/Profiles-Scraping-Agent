"""
dom_selectors.py — Centralized DOM selector registry for LinkedIn profile scraping.
Supports primary and fallback selectors for all critical profile components.
"""

from typing import List, Optional, Tuple, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Page, Locator

# --- Profile Top Card Selectors ---
PROFILE_NAME_SELECTORS: List[str] = [
    "h1.text-heading-xlarge",
    "div.pv-text-details__left-panel h1",
    "section.artdeco-card h1",
    "main h1",
    "div[componentkey*='Topcard'] h2",
    "section[componentkey*='Topcard'] h2",
    "[componentkey*='Topcard'] h2",
]

HEADLINE_SELECTORS: List[str] = [
    ".text-body-medium",
    "div.pv-text-details__left-panel .text-body-medium",
    "div.text-body-medium.break-words",
    "div[data-generated-suggestion-target]",
    "div[componentkey*='Topcard'] p:nth-of-type(2)",
    "section[componentkey*='Topcard'] p:nth-of-type(2)",
]

LOCATION_SELECTORS: List[str] = [
    ".text-body-small.inline",
    "span.text-body-small.inline.t-black--light",
    "div.pv-text-details__left-panel span.text-body-small",
    "div.pv-text-details__left-panel div.text-body-small",
    "div[componentkey*='Topcard'] p:nth-of-type(3)",
    "section[componentkey*='Topcard'] p:nth-of-type(3)",
]

CONNECTION_COUNT_SELECTORS: List[str] = [
    "li.text-body-small.t-black--light span.t-bold",
    "span.text-body-small.t-black--light:has-text('connection')",
    "span.text-body-small.t-black--light:has-text('follower')",
    "div.pv-text-details__left-panel span:has-text('connection')",
    "ul.pv-top-card--list-bullet li",
]

# --- Section Container Selectors ---
FEATURED_SECTION_SELECTORS: List[str] = [
    "section#featured",
    "section:has(h2:has-text('Featured'))",
    "[data-section='featured']",
    "section[componentkey*='Featured']",
    "div[componentkey*='Featured']",
]

ABOUT_SECTION_SELECTORS: List[str] = [
    "section#about",
    "section:has(h2:has-text('About'))",
    "[data-section='about']",
    "section[componentkey*='About']",
    "div[componentkey*='About']",
]

EXPERIENCE_SECTION_SELECTORS: List[str] = [
    "section#experience",
    "section:has(h2:has-text('Experience'))",
    "[data-section='experience']",
    "section[componentkey*='ExperienceTopLevelSection']",
    "div[componentkey*='ExperienceTopLevelSection']",
    "div[componentkey*='profileCardsExperienceOnly']",
]

EDUCATION_SECTION_SELECTORS: List[str] = [
    "section#education",
    "section:has(h2:has-text('Education'))",
    "[data-section='education']",
    "section[componentkey*='EducationTopLevelSection']",
    "div[componentkey*='EducationTopLevelSection']",
]

SKILLS_SECTION_SELECTORS: List[str] = [
    "section#skills",
    "section:has(h2:has-text('Skills'))",
    "[data-section='skills']",
    "section[componentkey*='Skills']",
    "div[componentkey*='Skills']",
]

CERTIFICATIONS_SECTION_SELECTORS: List[str] = [
    "section#licenses_and_certifications",
    "section:has(h2:has-text('Licenses & certifications'))",
    "section:has(h2:has-text('Certifications'))",
    "section[componentkey*='CertificationTopLevel']",
    "div[componentkey*='CertificationTopLevel']",
]

PROJECTS_SECTION_SELECTORS: List[str] = [
    "section#projects",
    "section:has(h2:has-text('Projects'))",
    "[data-section='projects']",
    "section[componentkey*='Projects']",
    "div[componentkey*='Projects']",
]

LANGUAGES_SECTION_SELECTORS: List[str] = [
    "section#languages",
    "section:has(h2:has-text('Languages'))",
    "[data-section='languages']",
    "section[componentkey*='Languages']",
    "div[componentkey*='Languages']",
]

VOLUNTEER_SECTION_SELECTORS: List[str] = [
    "section#volunteer_experience",
    "section:has(h2:has-text('Volunteer'))",
    "[data-section='volunteer']",
    "section[componentkey*='Volunteer']",
    "div[componentkey*='Volunteer']",
]

# --- Interactive & Modal Selectors ---
CONTACT_BUTTON_SELECTORS: List[str] = [
    "a[href*='overlay/contact-info']",
    "#topcard-contact-info",
    "a:has-text('Contact info')",
    "button:has-text('Contact info')",
]

CONTACT_MODAL_SELECTORS: List[str] = [
    "div.artdeco-modal[role='dialog']",
    "div[aria-labelledby*='contact-info']",
    "section.artdeco-modal",
    "div.artdeco-modal__content",
    "div.pv-profile-section__section-info",
]

CONTACT_DISMISS_SELECTORS: List[str] = [
    "button[aria-label='Dismiss']",
    "button.artdeco-modal__dismiss",
    "button[data-test-modal-close-btn]",
]

EXPAND_SEE_MORE_SELECTORS: List[str] = [
    "button.inline-show-more-text__button",
    "button[aria-label*='more']",
    "button:has-text('see more')",
    "button:has-text('more')",
    "a.inline-show-more-text__link",
]

EXPAND_EXPERIENCE_ROLES_SELECTORS: List[str] = [
    "a[href*='/details/experience/']",
    "button:has-text('Show all')",
]

PAGE_READINESS_SELECTORS: List[str] = [
    "h1.text-heading-xlarge",
    "main section.artdeco-card",
    "div.profile-view-grid",
    "section[componentkey*='Topcard']",
    "div[componentkey*='Topcard']",
    "main",
]

EXPERIENCE_ITEM_SELECTORS: List[str] = [
    "div[componentkey*='entity-collection-item']",
    "section#experience ul > li",
    "section:has(h2:has-text('Experience')) ul > li",
    "li.artdeco-list__item",
]


def find_first_matching(page, selectors: List[str], state: str = "attached", timeout_ms: int = 2000) -> Tuple[Optional[Any], Optional[str], List[str]]:
    """
    Attempts each selector in order. Returns (matching_locator, successful_selector, failed_selectors).
    """
    failed = []
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            loc.wait_for(state=state, timeout=timeout_ms)
            return loc, sel, failed
        except Exception:
            failed.append(sel)
    return None, None, failed


def query_first_text(page, selectors: List[str]) -> Tuple[str, Optional[str], List[str]]:
    """
    Attempts each selector in order and returns first non-empty inner_text.
    Returns (text, matched_selector, failed_selectors).
    """
    failed = []
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.count() > 0 and loc.is_visible():
                txt = loc.inner_text().strip()
                if txt:
                    return txt, sel, failed
                failed.append(sel)
            else:
                failed.append(sel)
        except Exception:
            failed.append(sel)
    return "", None, failed
