"""
Unit tests for contact extraction module.
"""

from unittest.mock import MagicMock
from skills.profile_scraper.contact_extractor import extract_contact_info


def test_extract_contact_info_full():
    mock_page = MagicMock()

    # Trigger link
    mock_trigger = MagicMock()
    mock_trigger.is_visible.return_value = True
    mock_page.locator.return_value.first = mock_trigger

    # Modal content
    modal_text = "Contact Info\nEmail\nalex.vance@examplecorp.com\nPhone\n+1 512-555-0199\nLinkedIn\nlinkedin.com/in/alex"
    mock_modal = MagicMock()
    mock_modal.inner_text.return_value = modal_text

    # Mailto element
    mock_email_elem = MagicMock()
    mock_email_elem.count.return_value = 1
    mock_email_elem.inner_text.return_value = "alex.vance@examplecorp.com"

    # Website links
    link_gh = MagicMock()
    link_gh.get_attribute.return_value = "https://github.com/alexvance"
    link_blog = MagicMock()
    link_blog.get_attribute.return_value = "https://alexvance.dev"

    mock_modal.locator.side_effect = lambda sel: (
        MagicMock(first=mock_email_elem) if "mailto:" in sel
        else MagicMock(all=lambda: [link_gh, link_blog])
    )

    # Setup locator dispatcher
    def locator_side_effect(selector):
        if "overlay/contact-info" in selector or "#topcard-contact-info" in selector:
            return MagicMock(first=mock_trigger)
        if "role='dialog'" in selector or "artdeco-modal" in selector:
            return MagicMock(first=mock_modal)
        return MagicMock(first=MagicMock(is_visible=lambda: False), count=lambda: 0)

    mock_page.locator.side_effect = locator_side_effect

    contacts = extract_contact_info(mock_page)

    assert contacts["email"] == "alex.vance@examplecorp.com"
    assert contacts["phone"] == "+1 512-555-0199"
    assert contacts["github_url"] == "https://github.com/alexvance"
    assert "https://alexvance.dev" in contacts["websites"]


def test_extract_contact_info_missing_contact_button():
    mock_page = MagicMock()
    # Contact button not visible or absent
    mock_not_found = MagicMock()
    mock_not_found.is_visible.return_value = False
    mock_page.locator.return_value.first = mock_not_found

    contacts = extract_contact_info(mock_page)

    # Handled gracefully without raising exceptions
    assert contacts["email"] == ""
    assert contacts["phone"] == ""
    assert contacts["websites"] == []


def test_extract_contact_info_modal_without_email_or_phone():
    mock_page = MagicMock()

    mock_trigger = MagicMock(is_visible=lambda: True)
    mock_modal = MagicMock()
    mock_modal.inner_text.return_value = "Contact Info\nLinkedIn\nlinkedin.com/in/privatemember"

    mock_email_empty = MagicMock(count=lambda: 0)
    mock_modal.locator.side_effect = lambda sel: (
        MagicMock(first=mock_email_empty) if "mailto:" in sel
        else MagicMock(all=lambda: [])
    )

    def locator_side_effect(selector):
        if "overlay/contact-info" in selector:
            return MagicMock(first=mock_trigger)
        if "role='dialog'" in selector:
            return MagicMock(first=mock_modal)
        return MagicMock(first=MagicMock(is_visible=lambda: False), count=lambda: 0)

    mock_page.locator.side_effect = locator_side_effect

    contacts = extract_contact_info(mock_page)

    # Missing fields are safely handled
    assert contacts["email"] == ""
    assert contacts["phone"] == ""
