"""
Unit tests for structured experience extraction module.
"""

from skills.profile_scraper.experience_extractor import (
    extract_structured_experience,
    parse_experience_date_range,
    _clean_company_name
)


def test_clean_company_name():
    assert _clean_company_name("Google · Full-time") == "Google"
    assert _clean_company_name("Microsoft • Contract") == "Microsoft"
    assert _clean_company_name("Amazon - Self-employed") == "Amazon"
    assert _clean_company_name("Apple Inc.") == "Apple Inc."


def test_extract_single_position_experience():
    html = """
    <section id="experience">
      <h2>Experience</h2>
      <ul>
        <li>
          <div>
            <span>Senior Software Engineer</span>
            <span>Databricks · Full-time</span>
            <span>Jan 2021 - Present · 3 yrs 8 mos</span>
            <span>Dallas, Texas, United States</span>
            <div>Designed and implemented scalable distributed data pipelines using Spark and Delta Lake.</div>
          </div>
        </li>
      </ul>
    </section>
    """
    jobs = extract_structured_experience(html)
    assert len(jobs) == 1
    job = jobs[0]
    assert job["company"] == "Databricks"
    assert job["company_name"] == "Databricks"
    assert job["title"] == "Senior Software Engineer"
    assert job["start_date"] == "Jan 2021"
    assert job["end_date"] == "Present"
    assert "3 yrs 8 mos" in job["duration_text"]
    assert "distributed data pipelines" in job["description"]


def test_extract_grouped_position_experience():
    html = """
    <section id="experience">
      <h2>Experience</h2>
      <ul>
        <li>
          <div>
            <span>Google</span>
            <span>Full-time · 4 yrs 2 mos</span>
            <ul>
              <li>
                <span>Staff Software Engineer</span>
                <span>Jan 2022 - Present · 2 yrs 8 mos</span>
                <div>Leading the Cloud Networking core infrastructure team.</div>
              </li>
              <li>
                <span>Senior Software Engineer</span>
                <span>Jul 2020 - Jan 2022 · 1 yr 7 mos</span>
                <div>Built low-latency proxy services.</div>
              </li>
            </ul>
          </div>
        </li>
      </ul>
    </section>
    """
    jobs = extract_structured_experience(html)
    assert len(jobs) == 2

    job1 = jobs[0]
    assert job1["company"] == "Google"
    assert job1["title"] == "Staff Software Engineer"
    assert job1["start_date"] == "Jan 2022"
    assert job1["end_date"] == "Present"
    assert "Cloud Networking" in job1["description"]

    job2 = jobs[1]
    assert job2["company"] == "Google"
    assert job2["title"] == "Senior Software Engineer"
    assert job2["start_date"] == "Jul 2020"
    assert job2["end_date"] == "Jan 2022"
    assert "low-latency proxy" in job2["description"]


def test_extract_experience_missing_optional_fields():
    html = """
    <section id="experience">
      <h2>Experience</h2>
      <ul>
        <li>
          <span>Software Developer</span>
          <span>Acme Corp</span>
          <span>2018 - 2020</span>
        </li>
      </ul>
    </section>
    """
    jobs = extract_structured_experience(html)
    assert len(jobs) == 1
    job = jobs[0]
    assert job["company"] == "Acme Corp"
    assert job["title"] == "Software Developer"
    assert job["start_date"] == "2018"
    assert job["end_date"] == "2020"
    assert job["description"] == ""


def test_extract_experience_empty():
    assert extract_structured_experience("") == []
    assert extract_structured_experience("<section></section>") == []
