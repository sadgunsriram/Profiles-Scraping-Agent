import pytest
from unittest.mock import patch, MagicMock
from skills.profile_scraper.signalhire_client import SignalHireClient


def test_signalhire_disabled_when_no_api_key():
    client = SignalHireClient(api_key="")
    assert not client.enabled
    res = client.enrich_candidate("https://www.linkedin.com/in/test-user")
    assert res["status"] == "SKIPPED_NO_API_KEY"
    assert res["phone"] == "Not Available"
    assert res["email"] == "Not Available"


def test_signalhire_invalid_url():
    client = SignalHireClient(api_key="mock_key")
    res = client.enrich_candidate("https://google.com")
    assert res["status"] == "INVALID_URL"


def test_signalhire_successful_enrichment():
    client = SignalHireClient(api_key="valid_test_key")

    mock_response_data = [
        {
            "status": "success",
            "item": "https://www.linkedin.com/in/john-doe",
            "candidate": {
                "fullName": "John Doe",
                "contacts": [
                    {"type": "phone", "value": "+1-555-234-5678"},
                    {"type": "email", "value": "john.doe@company.com"}
                ]
            }
        }
    ]

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_response_data
    mock_resp.text = "OK"

    with patch("httpx.Client.post", return_value=mock_resp):
        res = client.enrich_candidate("https://www.linkedin.com/in/john-doe")
        assert res["status"] == "SUCCESS"
        assert res["phone"] == "+1-555-234-5678"
        assert res["email"] == "john.doe@company.com"
        assert "+1-555-234-5678" in res["all_phones"]
        assert "john.doe@company.com" in res["all_emails"]


def test_signalhire_out_of_credits_402():
    client = SignalHireClient(api_key="valid_test_key")

    mock_resp = MagicMock()
    mock_resp.status_code = 402
    mock_resp.text = "Payment required / Out of credits"
    mock_resp.json.return_value = {"error": "out of credits"}

    with patch("httpx.Client.post", return_value=mock_resp):
        res = client.enrich_candidate("https://www.linkedin.com/in/john-doe")
        assert res["status"] == "OUT_OF_CREDITS"
        assert res["phone"] == "Not Available"
        assert res["email"] == "Not Available"


def test_signalhire_key_pool_init_comma_separated():
    client = SignalHireClient(api_key="key1, key2,  key3, key1, , none, null")
    assert client.enabled
    assert client.api_keys == ["key1", "key2", "key3"]
    assert client.current_api_key == "key1"
    status = client.get_pool_status()
    assert status["total_keys"] == 3
    assert status["remaining_keys"] == 3
    assert status["active_index"] == 0


def test_signalhire_key_pool_init_list():
    client = SignalHireClient(api_keys=["key_a", "key_b"])
    assert client.enabled
    assert client.api_keys == ["key_a", "key_b"]
    assert client.current_api_key == "key_a"


def test_signalhire_rotation_on_402():
    client = SignalHireClient(api_key="exhausted_key, active_key")
    assert client.current_api_key == "exhausted_key"

    # Call 1: exhausted_key returns 402
    # Call 2: active_key returns 200 with contacts
    resp_402 = MagicMock()
    resp_402.status_code = 402
    resp_402.text = "Payment required / Out of credits"
    resp_402.json.return_value = {"error": "out of credits"}

    resp_200 = MagicMock()
    resp_200.status_code = 200
    resp_200.text = "OK"
    resp_200.json.return_value = [
        {
            "status": "success",
            "item": "https://www.linkedin.com/in/john-doe",
            "candidate": {
                "fullName": "John Doe",
                "contacts": [
                    {"type": "phone", "value": "+1-555-999-8888"},
                    {"type": "email", "value": "john.doe@company.com"}
                ]
            }
        }
    ]

    with patch("httpx.Client.post", side_effect=[resp_402, resp_200]) as mock_post:
        res = client.enrich_candidate("https://www.linkedin.com/in/john-doe")
        assert res["status"] == "SUCCESS"
        assert res["phone"] == "+1-555-999-8888"
        assert res["email"] == "john.doe@company.com"
        # Verify it rotated to key 2
        assert client.current_api_key == "active_key"
        assert client.current_key_index == 1
        assert "exhausted_key" in client.exhausted_keys
        # Check pool status
        status = client.get_pool_status()
        assert status["active_index"] == 1
        assert status["remaining_keys"] == 1
        assert status["exhausted_keys_count"] == 1


def test_signalhire_all_keys_exhausted():
    client = SignalHireClient(api_key="key1, key2")

    resp_402 = MagicMock()
    resp_402.status_code = 402
    resp_402.text = "Out of credits"
    resp_402.json.return_value = {"error": "out of credits"}

    with patch("httpx.Client.post", side_effect=[resp_402, resp_402]):
        res = client.enrich_candidate("https://www.linkedin.com/in/john-doe")
        assert res["status"] == "OUT_OF_CREDITS"
        assert client.current_api_key == ""
        assert len(client.exhausted_keys) == 2
        status = client.get_pool_status()
        assert not status["has_available_keys"]
        assert status["remaining_keys"] == 0


def test_signalhire_rotation_on_auth_error_401():
    client = SignalHireClient(api_key="bad_auth_key, good_key")

    resp_401 = MagicMock()
    resp_401.status_code = 401
    resp_401.text = "Unauthorized"

    resp_200 = MagicMock()
    resp_200.status_code = 200
    resp_200.text = "OK"
    resp_200.json.return_value = {
        "candidate": {
            "fullName": "Jane Doe",
            "contacts": [{"type": "email", "value": "jane@example.com"}]
        }
    }

    with patch("httpx.Client.post", side_effect=[resp_401, resp_200]):
        res = client.enrich_candidate("https://www.linkedin.com/in/jane-doe")
        assert res["status"] == "SUCCESS"
        assert res["email"] == "jane@example.com"
        assert client.current_api_key == "good_key"

