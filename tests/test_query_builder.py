import pytest
from skills.profile_scraper.query_builder import is_raw_boolean_query, build_search_dorks


def test_is_raw_boolean_query():
    # True Boolean expressions
    assert is_raw_boolean_query('("SailPoint" OR "CyberArk") AND ("IAM Engineer" OR "Architect")')
    assert is_raw_boolean_query('"Python Developer" AND "AWS" OR "GCP"')
    assert is_raw_boolean_query('DevOps AND (Kubernetes OR Docker)')

    # Simple keywords / role titles (False)
    assert not is_raw_boolean_query("IAM Engineer")
    assert not is_raw_boolean_query("Network Engineer")
    assert not is_raw_boolean_query("data scientist")
    assert not is_raw_boolean_query("")


def test_build_search_dorks_for_raw_boolean():
    raw_query = '("SailPoint" OR "CyberArk") AND "Architect"'
    dorks = build_search_dorks(raw_query, target_count=500, mode="linkedin")

    assert len(dorks) >= 2
    # Ensure raw query logic is preserved and Open to Work clause is injected by default
    for d in dorks:
        assert 'site:linkedin.com/in/' in d
        assert '("SailPoint" OR "CyberArk") AND "Architect"' in d
        assert 'open to work' in d
        assert '-inurl:dir' in d


def test_build_search_dorks_for_simple_role():
    role_query = "Network Engineer"
    dorks = build_search_dorks(role_query, target_count=500, mode="linkedin")

    assert len(dorks) >= 3
    # Check that it expanded roles and includes Open to Work clause
    has_role_expansion = any("Network" in d for d in dorks)
    assert has_role_expansion
    assert all("open to work" in d for d in dorks)
    # Check that it includes USA region tags
    has_usa_tag = any("USA" in d or "California" in d for d in dorks)
    assert has_usa_tag


def test_build_search_dorks_open_to_work_toggle():
    role_query = "IAM Engineer"
    dorks_with_otw = build_search_dorks(role_query, mode="linkedin", require_open_to_work=True)
    assert all("open to work" in d for d in dorks_with_otw)

    dorks_without_otw = build_search_dorks(role_query, mode="linkedin", require_open_to_work=False)
    assert not any("open to work" in d for d in dorks_without_otw)


def test_repair_cli_argv_windows_cmd_split():
    from skills.profile_scraper.query_builder import repair_cli_argv

    # Case 1: Windows CMD split boolean with single quotes and count
    cmd_split = ["'(Network Engineer)", "AND", "(open to work", "OR", "#opentowork)'", "10"]
    repaired = repair_cli_argv(cmd_split)
    assert repaired == ["(Network Engineer) AND (open to work OR #opentowork)", "10"]

    # Case 2: Windows CMD split boolean without count
    cmd_split_no_count = ["'(Network Engineer)", "AND", "(open to work", "OR", "#opentowork)'"]
    repaired = repair_cli_argv(cmd_split_no_count)
    assert repaired == ["(Network Engineer) AND (open to work OR #opentowork)"]

    # Case 3: Space-separated keywords with count and mode flag
    unquoted = ["Network", "Security", "Engineer", "15", "--mode", "linkedin"]
    repaired = repair_cli_argv(unquoted)
    assert repaired == ["Network Security Engineer", "15", "--mode", "linkedin"]

    # Case 4: Standard single-quoted string
    single_quoted = ["'IAM Engineer'", "10"]
    repaired = repair_cli_argv(single_quoted)
    assert repaired == ["IAM Engineer", "10"]
