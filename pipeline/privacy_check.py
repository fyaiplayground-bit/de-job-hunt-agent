"""Privacy check (decision #62): no commit may add FL's name, employers, schools or contact
details to the public repo.

    uv run python -m pipeline.privacy_check --staged          # what the pre-commit hook runs
    uv run python -m pipeline.privacy_check --message FILE    # what the commit-msg hook runs
    uv run python -m pipeline.privacy_check --all             # every tracked file

The words to look for come from FL's private profile (`private/`, gitignored), never from a
committed list, so the check itself reveals nothing. Product names that start with an employer's
name ("Acme Redshift" for an employer called Acme) are not leaks: every skill name in the
vocabulary and the Evidence Bank that starts with the employer is allowed. Without a `private/`
folder (someone else's clone) there is nothing to check and the commit goes ahead.

Hooks live in `.githooks/` and are turned on once per clone with
`git config core.hooksPath .githooks`.
"""

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from agents.profile import load_profile
from pipeline.config import REPO_ROOT

PRIVATE_DIR = REPO_ROOT / "private"
VOCABULARY_FILE = REPO_ROOT / "config" / "skill_vocabulary.toml"
EDGE_BEFORE, EDGE_AFTER = r"(?<![A-Za-z0-9])", r"(?![A-Za-z0-9])"


@dataclass(frozen=True)
class Term:
    label: str  # what kind of detail, shown when a line is blocked
    pattern: re.Pattern[str]


@dataclass(frozen=True)
class Leak:
    where: str  # path:line, or "commit message:line"
    label: str
    found: str


def _word(text: str) -> re.Pattern[str]:
    """The text as a whole word or phrase, ignoring case; spaces match any run of spaces."""
    body = r"\s+".join(re.escape(part) for part in text.split())
    return re.compile(EDGE_BEFORE + body + EDGE_AFTER, re.IGNORECASE)


def _organization(text: str) -> re.Pattern[str]:
    """Like _word, but not inside a web address: "aws.amazon.com" names a website, not a
    workplace. A name at the end of a sentence ("... at Acme.") still counts."""
    body = r"\s+".join(re.escape(part) for part in text.split())
    return re.compile(r"(?<![A-Za-z0-9.])" + body + r"(?![A-Za-z0-9]|\.[A-Za-z])", re.IGNORECASE)


def _phone(phone: str) -> re.Pattern[str] | None:
    """The phone's last 10 digits with any separators: (860) 555-0100, 860.555.0100, 8605550100."""
    digits = re.sub(r"\D", "", phone)[-10:]
    if len(digits) < 10:
        return None
    sep = r"[\s().-]*"
    body = sep.join([re.escape(digits[:3]), re.escape(digits[3:6]), re.escape(digits[6:])])
    return re.compile(r"(?<!\d)\(?" + body + r"(?!\d)")


def private_terms(folder: Path = PRIVATE_DIR) -> list[Term]:
    """The details that must never be committed, read from the private profile."""
    profile = load_profile(folder)
    contact = profile.applicant["contact"]
    terms: list[Term] = []
    name = contact["name"].strip()
    terms.append(Term("your name", _word(name)))
    terms.append(Term("your name", _word(name.replace(" ", ""))))
    first = name.split()[0]
    if len(first) >= 4:  # a short first name would match ordinary words
        terms.append(Term("your first name", _word(first)))
    email = contact["email"].strip()
    terms.append(Term("your email", _word(email)))
    terms.append(Term("your email name", _word(email.split("@")[0])))
    phone = _phone(contact.get("phone", ""))
    if phone is not None:
        terms.append(Term("your phone", phone))
    if contact.get("street"):
        terms.append(Term("your street address", _word(contact["street"])))
    for employer in sorted({role.employer.strip() for role in profile.bank.roles}):
        terms.append(Term("an employer of yours", _organization(employer)))
    for school in sorted({entry.school.split(",")[0].strip() for entry in profile.bank.education}):
        terms.append(Term("a school of yours", _organization(school)))
    return terms


def allowed_phrases(folder: Path = PRIVATE_DIR) -> list[re.Pattern[str]]:
    """Skill names that merely start with an employer's name, longest first: a product, not a
    workplace."""
    profile = load_profile(folder)
    employers = [role.employer.strip().casefold() for role in profile.bank.roles]
    names = set(re.findall(r'"([^"\n]+)"', VOCABULARY_FILE.read_text(encoding="utf-8")))
    for skill in profile.bank.skills:
        names |= {skill.name, *skill.aliases}
    products = {
        name for name in names
        if any(name.casefold().startswith(f"{employer} ") for employer in employers)
    }
    return [_word(name) for name in sorted(products, key=len, reverse=True)]


def find_leaks(
    lines: list[tuple[str, str]], terms: list[Term], allowed: list[re.Pattern[str]]
) -> list[Leak]:
    """Every term found in (where, text) lines, after blanking the allowed product names."""
    leaks = []
    for where, text in lines:
        masked = text
        for phrase in allowed:
            masked = phrase.sub(lambda m: " " * len(m.group(0)), masked)
        for term in terms:
            match = term.pattern.search(masked)
            if match:
                leaks.append(Leak(where, term.label, text[match.start():match.end()]))
    return leaks


def staged_lines(repo: Path = REPO_ROOT) -> list[tuple[str, str]]:
    """The lines a commit would add: (path:line, text) from the staged diff."""
    diff = subprocess.run(
        ["git", "diff", "--cached", "-U0", "--no-color", "--no-ext-diff"],
        cwd=repo, capture_output=True, text=True, encoding="utf-8", errors="replace", check=True,
    ).stdout
    lines, path, number = [], "", 0
    for line in diff.splitlines():
        if line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") else line[4:]
        elif line.startswith("@@"):
            hunk = re.search(r"\+(\d+)", line)
            number = int(hunk.group(1)) if hunk else 0
        elif line.startswith("+"):
            lines.append((f"{path}:{number}", line[1:]))
            number += 1
    return lines


def tracked_lines(repo: Path = REPO_ROOT) -> list[tuple[str, str]]:
    files = subprocess.run(
        ["git", "ls-files", "-z"], cwd=repo, capture_output=True, check=True
    ).stdout.decode("utf-8").split("\0")
    lines = []
    for name in filter(None, files):
        try:
            text = (repo / name).read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue  # binary files (fonts, PDFs) and files deleted but not yet staged
        lines += [(f"{name}:{i}", line) for i, line in enumerate(text.splitlines(), start=1)]
    return lines


def message_lines(path: Path) -> list[tuple[str, str]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return [
        (f"commit message:{i}", line)
        for i, line in enumerate(text.splitlines(), start=1)
        if not line.startswith("#")  # git's own comment lines
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pipeline.privacy_check")
    what = parser.add_mutually_exclusive_group(required=True)
    what.add_argument("--staged", action="store_true", help="the lines this commit adds")
    what.add_argument("--message", type=Path, help="a commit message file")
    what.add_argument("--all", action="store_true", help="every tracked file")
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    if not (PRIVATE_DIR / "applicant_profile.toml").is_file():
        print("privacy check: no private/ profile here, nothing to check")
        return 0
    terms, allowed = private_terms(), allowed_phrases()
    if args.staged:
        lines = staged_lines()
    elif args.message:
        lines = message_lines(args.message)
    else:
        lines = tracked_lines()
    leaks = find_leaks(lines, terms, allowed)
    for leak in leaks:
        print(f"BLOCKED {leak.where}: {leak.label} ({leak.found!r})")
    if leaks:
        print(
            "privacy check: these must not reach the public repo (decision #62). Reword them, "
            "e.g. 'current role' instead of the employer, then commit again."
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
