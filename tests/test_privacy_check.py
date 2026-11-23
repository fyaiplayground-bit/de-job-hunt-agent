"""The privacy check (decision #62), run against the fictional sample profile as if it were the
private one: its name, employers, school and contact details stand in for FL's."""

import subprocess

import pytest

from pipeline import privacy_check
from pipeline.config import REPO_ROOT
from pipeline.privacy_check import _word, find_leaks, message_lines, private_terms, staged_lines

SAMPLE = REPO_ROOT / "data" / "sample"
TERMS = private_terms(SAMPLE)


def leaks(text, allowed=()):
    return [(leak.label, leak.found) for leak in find_leaks([("f:1", text)], TERMS, list(allowed))]


@pytest.mark.parametrize(
    "text, label",
    [
        ("Resume for Alex Sample", "your name"),
        ("AlexSample_DataEngineer_Acme.pdf", "your name"),
        ("write to alex.sample@example.com", "your email"),
        ("call (303) 555-0142", "your phone"),
        ("or 303.555.0142", "your phone"),
        ("or 3035550142", "your phone"),
        ("the Quillfeather Outdoor bullets were cut", "an employer of yours"),
        ("she works at quillfeather   outdoor.", "an employer of yours"),  # case, spaces, period
        ("an M.S. from Front Range State University", "a school of yours"),
    ],
)
def test_private_details_are_found(text, label):
    assert label in [found_label for found_label, _ in leaks(text)]


@pytest.mark.parametrize(
    "text",
    [
        "the current role keeps 5 bullets",
        "see https://www.quillfeatheroutdoor.example/careers",  # not the two-word name
        "Alexander the Great",  # the first name is 4 letters but must be a whole word
        "order 303-555-01420 is a longer number",
    ],
)
def test_ordinary_text_passes(text):
    assert leaks(text) == []


def test_a_product_named_after_an_employer_is_allowed():
    """A product named after an employer is not a workplace; the employer alone is."""
    allowed = [_word("Quillfeather Outdoor Gear")]
    assert leaks("built on Quillfeather Outdoor Gear", allowed) == []
    assert leaks("Quillfeather Outdoor Gear at Quillfeather Outdoor", allowed) == [
        ("an employer of yours", "Quillfeather Outdoor")
    ]


def test_a_name_inside_a_web_address_is_not_a_workplace():
    terms = [privacy_check.Term("an employer of yours", privacy_check._organization("Acme"))]
    found = find_leaks
    assert found([("f:1", "sign up at aws.acme.com")], terms, []) == []
    assert found([("f:1", "acme.jobs lists it")], terms, []) == []
    assert len(found([("f:1", "I work at Acme.")], terms, [])) == 1


def test_git_comment_lines_in_a_message_are_skipped(tmp_path):
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text("Fix trim\n# Alex Sample is only in a git comment\nbody\n", encoding="utf-8")
    kept = [where for where, _ in message_lines(message)]
    assert kept == ["commit message:1", "commit message:3"]


def test_staged_lines_give_each_added_line_with_its_number(tmp_path):
    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q")
    git("config", "user.email", "test@example.com")
    git("config", "user.name", "Test")
    (tmp_path / "a.md").write_text("one\ntwo\n", encoding="utf-8")
    git("add", "a.md")
    git("commit", "-q", "-m", "first", "--no-verify")
    (tmp_path / "a.md").write_text("one\nTWO\nthree\n", encoding="utf-8")
    git("add", "a.md")
    assert staged_lines(tmp_path) == [("a.md:2", "TWO"), ("a.md:3", "three")]


def test_without_a_private_profile_there_is_nothing_to_check(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(privacy_check, "PRIVATE_DIR", tmp_path)
    assert privacy_check.main(["--all"]) == 0
    assert "nothing to check" in capsys.readouterr().out
