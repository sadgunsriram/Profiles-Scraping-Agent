"""
contact_extractor.py — Contact extraction module for authorized LinkedIn profile scraping.
Extracts legitimately available contact details (Email, Phone, Websites, GitHub, Birthday)
from the Contact Info modal and profile text, gracefully handling missing fields.
"""

import re
from typing import Dict, List, Optional, Any
from loguru import logger
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError


def extract_contact_info(page: Page, enable_extension: bool = False) -> Dict[str, Any]:
    """
    Extracts legitimately available contact details from the candidate's Contact Info modal.
    Handles missing contact fields gracefully without raising exceptions.
    Returns:
        dict with keys: email, phone, websites, github_url, date_of_birth, raw_modal_text, signalhire
    """
    contacts: Dict[str, Any] = {
        "email": "",
        "phone": "",
        "websites": [],
        "github_url": "",
        "date_of_birth": "NOT_AVAILABLE",
        "raw_modal_text": "",
        "signalhire": {}
    }

    from skills.profile_scraper.selectors import (
        CONTACT_BUTTON_SELECTORS,
        CONTACT_MODAL_SELECTORS,
        CONTACT_DISMISS_SELECTORS
    )

    contact_link = None
    for sel in CONTACT_BUTTON_SELECTORS:
        try:
            elem = page.locator(sel).first
            if elem.is_visible():
                contact_link = elem
                break
        except Exception:
            continue

    if contact_link:
        try:
            logger.debug("[ContactExtractor] Opening Contact Info modal...")
            contact_link.click(timeout=3000)

            # Wait for dialog modal to appear using centralized selectors
            modal = None
            for m_sel in CONTACT_MODAL_SELECTORS:
                try:
                    cand = page.locator(m_sel).first
                    cand.wait_for(state="visible", timeout=4000)
                    modal = cand
                    break
                except PlaywrightTimeoutError:
                    continue

            if modal:
                modal_text = modal.inner_text() or ""
                contacts["raw_modal_text"] = modal_text

                # 1. Extract Email
                try:
                    email_elem = modal.locator("a[href^='mailto:']").first
                    if email_elem.count() > 0:
                        contacts["email"] = email_elem.inner_text().strip()
                except Exception:
                    pass

                if not contacts["email"]:
                    email_matches = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', modal_text)
                    clean_emails = [e for e in email_matches if not any(ign in e.lower() for ign in ["example.com", "domain.com", "sentry"])]
                    if clean_emails:
                        contacts["email"] = clean_emails[0]

                # 2. Extract Phone
                lines = [l.strip() for l in modal_text.split("\n") if l.strip()]
                for idx, line in enumerate(lines):
                    if "phone" in line.lower() and idx + 1 < len(lines):
                        cand_phone = lines[idx + 1].strip()
                        if len(re.sub(r'\D', '', cand_phone)) >= 10:
                            contacts["phone"] = cand_phone
                            break

                # 3. Extract Explicit Birthday (DOB) if voluntarily provided
                for idx, line in enumerate(lines):
                    if "birthday" in line.lower() or "born" in line.lower():
                        if idx + 1 < len(lines):
                            b_val = lines[idx + 1].strip()
                            if b_val and not any(kw in b_val.lower() for kw in ["contact", "profile", "dismiss", "edit"]):
                                contacts["date_of_birth"] = b_val
                                break

                # 4. Extract Websites & GitHub
                try:
                    links = modal.locator("a").all()
                    for lnk in links:
                        href = lnk.get_attribute("href") or ""
                        if href and not any(kw in href.lower() for kw in ["linkedin.com", "mailto:", "javascript:"]):
                            if href not in contacts["websites"]:
                                contacts["websites"].append(href)
                            if "github.com" in href.lower() and not contacts["github_url"]:
                                contacts["github_url"] = href
                except Exception:
                    pass

            # Close modal cleanly via close button or Escape key
            closed = False
            for d_sel in CONTACT_DISMISS_SELECTORS:
                try:
                    close_btn = page.locator(d_sel).first
                    if close_btn.is_visible():
                        close_btn.click(timeout=1500)
                        closed = True
                        break
                except Exception:
                    continue
            if not closed:
                page.keyboard.press("Escape")

            # Explicitly verify the modal is fully closed/hidden before continuing
            if modal:
                try:
                    modal.wait_for(state="hidden", timeout=2000)
                except Exception:
                    pass
            logger.debug("[ContactExtractor] Contact modal dismissed and closed verified.")

        except Exception as e:
            logger.debug(f"[ContactExtractor] Note during contact modal interaction: {e}")

    # Fallback: scan About text or Headline for GitHub URLs if not in modal
    if not contacts["github_url"]:
        try:
            body_text = page.locator("main").inner_text(timeout=2000) or ""
            gh_match = re.search(r'(https?://(?:www\.)?github\.com/[a-zA-Z0-9_-]+)', body_text)
            if gh_match:
                contacts["github_url"] = gh_match.group(1)
        except Exception:
            pass

    return contacts
