"""
Unit tests for centralized selectors module.
"""

from unittest.mock import MagicMock
from skills.profile_scraper.selectors import (
    PROFILE_NAME_SELECTORS,
    HEADLINE_SELECTORS,
    LOCATION_SELECTORS,
    EXPERIENCE_SECTION_SELECTORS,
    EDUCATION_SECTION_SELECTORS,
    SKILLS_SECTION_SELECTORS,
    CONTACT_BUTTON_SELECTORS,
    EXPAND_SEE_MORE_SELECTORS,
    query_first_text,
    find_first_matching
)


def test_selector_lists_non_empty():
    assert len(PROFILE_NAME_SELECTORS) >= 2
    assert len(HEADLINE_SELECTORS) >= 2
    assert len(LOCATION_SELECTORS) >= 2
    assert len(EXPERIENCE_SECTION_SELECTORS) >= 2
    assert len(EDUCATION_SECTION_SELECTORS) >= 2
    assert len(SKILLS_SECTION_SELECTORS) >= 2
    assert len(CONTACT_BUTTON_SELECTORS) >= 2
    assert len(EXPAND_SEE_MORE_SELECTORS) >= 2


def test_query_first_text_primary_success():
    mock_page = MagicMock()
    mock_elem = MagicMock()
    mock_elem.count.return_value = 1
    mock_elem.is_visible.return_value = True
    mock_elem.inner_text.return_value = "Satya Nadella"

    mock_page.locator.return_value.first = mock_elem

    text, matched, failed = query_first_text(mock_page, PROFILE_NAME_SELECTORS)
    assert text == "Satya Nadella"
    assert matched == PROFILE_NAME_SELECTORS[0]
    assert failed == []


def test_query_first_text_fallback_success():
    mock_page = MagicMock()

    mock_fail = MagicMock()
    mock_fail.count.return_value = 0
    mock_fail.is_visible.return_value = False

    mock_success = MagicMock()
    mock_success.count.return_value = 1
    mock_success.is_visible.return_value = True
    mock_success.inner_text.return_value = "Chairman and CEO at Microsoft"

    def locator_side_effect(sel):
        if sel == HEADLINE_SELECTORS[0]:
            return MagicMock(first=mock_fail)
        return MagicMock(first=mock_success)

    mock_page.locator.side_effect = locator_side_effect

    text, matched, failed = query_first_text(mock_page, HEADLINE_SELECTORS)
    assert text == "Chairman and CEO at Microsoft"
    assert matched == HEADLINE_SELECTORS[1]
    assert HEADLINE_SELECTORS[0] in failed
