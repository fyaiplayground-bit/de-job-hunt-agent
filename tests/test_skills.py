"""Tests for agents/skills.py: skill files load as versioned prompts, and a prompt's text can't
change without a version bump (decision #30)."""

import shutil
from pathlib import Path

import pytest

from agents.skills import (
    SKILLS_DIR,
    SkillError,
    load_all_skills,
    load_skill,
    lock_problems,
    parse_skill,
    read_lock,
    write_lock,
)

AGENT_SKILLS = {
    "ats-critic", "coverage-report", "fit-scoring", "jd-analysis", "outreach-drafting",
    "resume-tailoring",
}
SKILL_TEXT = "---\nname: demo\ndescription: A demo skill.\nversion: 2\n---\n\n# Demo\n\nDo it.\n"


@pytest.fixture
def skills_copy(tmp_path: Path) -> Path:
    """A private copy of the real skills folder, safe to edit."""
    target = tmp_path / "skills"
    shutil.copytree(SKILLS_DIR, target)
    return target


def _edit(skills_dir: Path, name: str, old: str, new: str) -> None:
    path = skills_dir / name / "SKILL.md"
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def test_every_agent_skill_loads_with_a_version():
    skills = load_all_skills()
    assert set(skills) == AGENT_SKILLS
    for name, skill in skills.items():
        assert skill.name == name
        assert skill.version >= 1
        assert skill.prompt_version == f"{name}@{skill.version}"
        assert skill.body.startswith("# ")  # front matter stripped, prompt starts at the title


def test_prompt_lock_matches_every_skill():
    """Fails when someone edits a SKILL.md without bumping its version and the lock."""
    assert lock_problems(load_all_skills(), read_lock()) == []


def test_parse_skill_reads_front_matter_and_body():
    skill = parse_skill(SKILL_TEXT, "demo")
    assert (skill.name, skill.description, skill.version) == ("demo", "A demo skill.", 2)
    assert skill.body == "# Demo\n\nDo it.\n"


def test_line_endings_dont_change_the_fingerprint():
    lf = parse_skill(SKILL_TEXT, "lf")
    crlf = parse_skill(SKILL_TEXT.replace("\n", "\r\n"), "crlf")
    assert lf.fingerprint == crlf.fingerprint


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("# no front matter\n", "should start with front matter"),
        (SKILL_TEXT.replace("version: 2\n", ""), "needs 'version'"),
        (SKILL_TEXT.replace("version: 2", "version: two"), "whole number"),
    ],
)
def test_bad_front_matter_raises(text, message):
    with pytest.raises(SkillError, match=message):
        parse_skill(text, "demo")


def test_skill_name_must_match_its_folder(skills_copy):
    _edit(skills_copy, "jd-analysis", "name: jd-analysis", "name: jd-analyst")
    with pytest.raises(SkillError, match="should match its folder"):
        load_skill("jd-analysis", skills_copy)


def test_text_change_without_bump_is_caught_and_cant_be_locked(skills_copy, tmp_path):
    lock = tmp_path / "prompt_lock.toml"
    write_lock(load_all_skills(skills_copy), lock)
    version = load_skill("jd-analysis", skills_copy).version
    _edit(skills_copy, "jd-analysis", "Decode what", "Figure out what")

    skills = load_all_skills(skills_copy)
    assert lock_problems(skills, read_lock(lock)) == [
        f"jd-analysis: text changed but version is still {version} (bump it, and record the "
        "change through the rules loop)"
    ]
    with pytest.raises(SkillError, match="text changed"):
        write_lock(skills, lock)


def test_bumped_version_is_flagged_until_locked(skills_copy, tmp_path):
    lock = tmp_path / "prompt_lock.toml"
    write_lock(load_all_skills(skills_copy), lock)
    version = load_skill("jd-analysis", skills_copy).version
    _edit(skills_copy, "jd-analysis", "Decode what", "Figure out what")
    _edit(skills_copy, "jd-analysis", f"version: {version}", f"version: {version + 1}")

    skills = load_all_skills(skills_copy)
    assert lock_problems(skills, read_lock(lock)) == [
        f"jd-analysis: version bumped to {version + 1}, lock not updated yet"
    ]
    write_lock(skills, lock)
    assert lock_problems(skills, read_lock(lock)) == []
    assert read_lock(lock)["jd-analysis"]["version"] == version + 1


def test_missing_and_removed_skills_are_flagged(skills_copy, tmp_path):
    lock = tmp_path / "prompt_lock.toml"
    write_lock(load_all_skills(skills_copy), lock)
    shutil.rmtree(skills_copy / "coverage-report")
    (skills_copy / "new-agent").mkdir()
    (skills_copy / "new-agent" / "SKILL.md").write_text(
        SKILL_TEXT.replace("name: demo", "name: new-agent"), encoding="utf-8"
    )
    problems = lock_problems(load_all_skills(skills_copy), read_lock(lock))
    assert problems == [
        "new-agent: not in the prompt lock (run: python -m agents.skills lock)",
        "coverage-report: in the prompt lock but the skill file is gone",
    ]
