"""Tests for agents/profile.py and the fictional sample profile in data/sample/ (decision #28).

The sample must load and pass every check, and each check must catch the mistake it exists for.
Broken variants are built by editing the parsed sample, never by touching the files.
"""

import copy
import re
import shutil
import tomllib
from pathlib import Path

import pytest

from agents.profile import (
    APPLICANT_PROFILE_FILE,
    EVIDENCE_BANK_FILE,
    ProfileError,
    check_applicant_profile,
    check_evidence_bank,
    check_resume,
    load_profile,
    main,
    parse_applicant_profile,
    parse_evidence_bank,
    resume_month,
    validate_profile,
)
from pipeline.config import REPO_ROOT, profile_dir

SAMPLE = REPO_ROOT / "data" / "sample"
FICTIONAL_ORGS = {"Quillfeather Outdoor", "Brightmoor Logistics", "Front Range State University"}


@pytest.fixture(scope="module")
def profile():
    return load_profile(SAMPLE)


@pytest.fixture
def bank_data():
    return tomllib.loads((SAMPLE / EVIDENCE_BANK_FILE).read_text(encoding="utf-8"))


@pytest.fixture
def applicant_data():
    return tomllib.loads((SAMPLE / APPLICANT_PROFILE_FILE).read_text(encoding="utf-8"))


# ---------------------------------------------------------------- the sample itself


def test_sample_profile_passes_every_check(profile):
    assert validate_profile(profile) == []
    assert profile.bank.sample is True
    assert profile.applicant["sample"] is True


def test_sample_is_visibly_fictional(profile):
    """Privacy guard: the public sample may only use reserved, made-up contact details."""
    text = "\n".join(
        (SAMPLE / name).read_text(encoding="utf-8")
        for name in (EVIDENCE_BANK_FILE, APPLICANT_PROFILE_FILE, "resume.md", "README.md")
    )
    for email in re.findall(r"[\w.+-]+@[\w.-]+", text):
        assert email.endswith("@example.com"), email
    for url in re.findall(r"https?://[^\s\"')]+", text):
        assert url.startswith("https://example.com/"), url
    for phone in re.findall(r"\(?\d{3}\)?[ -]\d{3}-\d{4}", text):
        assert re.search(r"555-01\d\d$", phone), phone
    orgs = {role.employer for role in profile.bank.roles}
    orgs |= {school.school for school in profile.bank.education}
    assert orgs == FICTIONAL_ORGS


def test_built_in_test_cases_are_present(profile):
    """The cases data/sample/README.md promises the Milestone 2 agents."""
    bank = profile.bank
    assert "ETL jobs" in profile.resume
    assert bank.find_skill("data pipelines").name == "ETL"
    assert bank.skill_level("Apache Airflow") == "practiced"
    assert "Airflow" not in profile.resume
    spark = bank.find_skill("PySpark")
    assert (spark.name, spark.status, bank.skill_level(spark.name)) == (
        "Apache Spark", "learning", "practiced",
    )
    for never_touched in ("Kafka", "Scala", "Snowflake", "Java"):
        assert bank.find_skill(never_touched) is None
    assert any(entry.rounded for entry in bank.evidence)


def test_find_skill_by_name_or_alias_ignoring_case(profile):
    bank = profile.bank
    assert bank.find_skill("airflow").name == "Apache Airflow"
    assert bank.find_skill("  Redshift ").name == "Amazon Redshift"
    assert bank.find_skill("SQL").name == "SQL"
    assert bank.find_skill("Kafka") is None


def test_skill_level_is_the_strongest_evidence(profile):
    bank = profile.bank
    assert bank.skill_level("SQL") == "production"
    assert bank.skill_level("Docker") == "project"  # project and practiced entries
    assert bank.skill_level("dbt") == "project"
    assert bank.skill_level("Kafka") is None


def test_resume_month():
    assert resume_month("2021-03") == "Mar 2021"
    assert resume_month("2017-12") == "Dec 2017"


def test_profile_dir_default_and_override(monkeypatch, tmp_path):
    monkeypatch.delenv("PROFILE_DIR", raising=False)
    assert profile_dir(env_file=None) == SAMPLE
    monkeypatch.setenv("PROFILE_DIR", "private")
    assert profile_dir(env_file=None) == REPO_ROOT / "private"
    monkeypatch.setenv("PROFILE_DIR", str(tmp_path))
    assert profile_dir(env_file=None) == tmp_path


# ---------------------------------------------------------------- each check catches its mistake


def test_resume_skill_without_evidence_is_caught(profile):
    resume = profile.resume.replace("Excel, Git, Docker", "Excel, Git, Docker, Kafka")
    problems = check_resume(resume, profile.bank, profile.applicant)
    assert problems == ["resume: skill 'Kafka' has no Evidence Bank entry"]


def test_resume_alias_in_skills_is_fine(profile):
    resume = profile.resume.replace("Excel, Git, Docker", "Excel, Git, Docker, Airflow")
    assert check_resume(resume, profile.bank, profile.applicant) == []


def test_resume_number_without_evidence_is_caught(profile):
    resume = profile.resume.replace("Migrated 25 Tableau", "Migrated 60 Tableau")
    problems = check_resume(resume, profile.bank, profile.applicant)
    assert problems == ["resume: the number 60 is in no Evidence Bank metric"]


def test_resume_numbers_glued_to_letters_are_not_claims(profile):
    resume = profile.resume.replace("logs in S3,", "logs in S3 and EC2,")
    assert check_resume(resume, profile.bank, profile.applicant) == []


def test_resume_dates_must_match_the_work_history(profile):
    resume = profile.resume.replace("Mar 2021 - Present", "Jan 2020 - Present")
    problems = check_resume(resume, profile.bank, profile.applicant)
    assert problems == ["resume: role quillfeather-bie needs 'Mar 2021 - Present'"]


def test_resume_headings_must_be_standard(profile):
    resume = profile.resume.replace("## Projects", "## Side Quests")
    problems = check_resume(resume, profile.bank, profile.applicant)
    assert len(problems) == 1 and problems[0].startswith("resume: headings should be")


def test_evidence_pointing_nowhere_is_caught(bank_data):
    bank_data["evidence"][0]["where"] = "no-such-role"
    problems = check_evidence_bank(parse_evidence_bank(bank_data))
    assert problems == ["evidence qf-glue-redshift: where 'no-such-role' is no role or project id"]


def test_evidence_must_use_canonical_skill_names(bank_data):
    bank_data["evidence"][0]["skills"].append("Glue")
    bank_data["evidence"][1]["skills"].append("Kafka")
    problems = check_evidence_bank(parse_evidence_bank(bank_data))
    assert problems == [
        "evidence qf-glue-redshift: use the name 'AWS Glue', not 'Glue'",
        "evidence qf-star-schema: skill 'Kafka' is not in [skills]",
    ]


def test_skill_without_evidence_is_caught(bank_data):
    bank_data["skills"]["Kafka"] = {"aliases": [], "status": "learning"}
    problems = check_evidence_bank(parse_evidence_bank(bank_data))
    assert problems == ["skill 'Kafka' has no evidence entry (then it's not covered)"]


def test_alias_naming_two_skills_is_caught(bank_data):
    bank_data["skills"]["Docker"]["aliases"] = ["glue"]
    problems = check_evidence_bank(parse_evidence_bank(bank_data))
    assert problems == ["'glue' names both 'AWS Glue' and 'Docker'"]


def test_bad_level_status_and_dates_are_caught(bank_data):
    bank_data["evidence"][0]["level"] = "expert"
    bank_data["skills"]["SQL"]["status"] = "maybe"
    bank_data["roles"][1]["end"] = "2016-01"
    bank_data["projects"][0]["start"] = "July 2026"
    problems = check_evidence_bank(parse_evidence_bank(bank_data))
    assert problems == [
        "project bikeshare-pipeline: start 'July 2026' should look like 2021-03",
        "role brightmoor-analyst: ends before it starts",
        "evidence qf-glue-redshift: level 'expert' not in ('production', 'project', 'practiced')",
        "skill 'SQL': status 'maybe' is not have/learning",
    ]


def test_duplicate_ids_are_caught(bank_data):
    bank_data["evidence"][1]["id"] = "qf-glue-redshift"
    bank_data["projects"][0]["id"] = "quillfeather-bie"
    problems = check_evidence_bank(parse_evidence_bank(bank_data))
    assert "role/project id 'quillfeather-bie' is used more than once" in problems
    assert "evidence id 'qf-glue-redshift' is used more than once" in problems


def test_missing_field_or_wrong_type_raises(bank_data, applicant_data):
    broken = copy.deepcopy(bank_data)
    del broken["evidence"][0]["level"]
    with pytest.raises(ProfileError, match=r"evidence\[0\]: missing 'level'"):
        parse_evidence_bank(broken)
    applicant_data["compensation"]["base_salary_floor"] = "120k"
    with pytest.raises(ProfileError, match="'base_salary_floor' should be int"):
        parse_applicant_profile(applicant_data)


def test_wrong_schema_version_raises(bank_data):
    bank_data["schema_version"] = 2
    with pytest.raises(ProfileError, match="schema_version should be 1"):
        parse_evidence_bank(bank_data)


def test_applicant_profile_checks(applicant_data):
    applicant_data["compensation"]["base_salary_floor"] = 150000
    applicant_data["location"]["work_modes"] = ["remote", "anywhere"]
    problems = check_applicant_profile(parse_applicant_profile(applicant_data))
    assert problems == [
        "compensation: need 0 < base_salary_floor <= base_salary_target",
        "location: work_modes ['remote', 'anywhere'] should be some of "
        "('remote', 'hybrid', 'onsite')",
    ]


# ---------------------------------------------------------------- command line


def test_check_command_ok_on_the_sample(capsys):
    assert main(["check", str(SAMPLE)]) == 0
    out = capsys.readouterr().out
    assert "fictional sample profile" in out
    assert out.strip().endswith("OK")


def test_check_command_fails_on_a_broken_copy(tmp_path: Path, capsys):
    for item in SAMPLE.iterdir():
        shutil.copy(item, tmp_path / item.name)
    resume = tmp_path / "resume.md"
    resume.write_text(
        resume.read_text(encoding="utf-8").replace("Git, Docker", "Git, Docker, Kafka"),
        encoding="utf-8",
    )
    assert main(["check", str(tmp_path)]) == 1
    assert "skill 'Kafka' has no Evidence Bank entry" in capsys.readouterr().out


def test_check_command_fails_on_a_missing_file(tmp_path: Path, capsys):
    assert main(["check", str(tmp_path)]) == 1
    assert "not found" in capsys.readouterr().out
