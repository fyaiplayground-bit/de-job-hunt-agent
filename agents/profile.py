"""Load and check a candidate profile (decision #28): the Evidence Bank, the Applicant Profile
and the master resume, from the folder in PROFILE_DIR (`data/sample` until Milestone 5, then
`private`).

    uv run python -m agents.profile check              # the folder in PROFILE_DIR
    uv run python -m agents.profile check private      # any folder

The Evidence Bank is the only source of facts about the candidate. The resume is a view of it:
every skill and every number on the resume must trace back to an Evidence Bank entry. These are
plain code checks, so the same files always get the same answer (decision #22).
"""

import argparse
import re
import sys
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pipeline.config import profile_dir

SCHEMA_VERSION = 1
EVIDENCE_BANK_FILE = "evidence_bank.toml"
APPLICANT_PROFILE_FILE = "applicant_profile.toml"
RESUME_FILE = "resume.md"

# Strongest first: a skill's level is the strongest level among its evidence entries.
LEVELS = ("production", "project", "practiced")
SKILL_STATUSES = ("have", "learning")
PROJECT_STATUSES = ("in_progress", "done")
WORK_MODES = ("remote", "hybrid", "onsite")
RESUME_HEADINGS = ("Summary", "Experience", "Projects", "Skills", "Education")

# Required keys of each Applicant Profile section, and the type each value must have.
APPLICANT_FIELDS: dict[str, dict[str, type]] = {
    "contact": {
        "name": str, "email": str, "phone": str, "city": str, "state": str, "country": str,
    },
    "links": {"portfolio": str, "github": str, "linkedin": str},
    "work_authorization": {
        "authorized_us": bool, "needs_sponsorship_now": bool, "needs_sponsorship_future": bool,
    },
    "availability": {"notice_period_weeks": int},
    "compensation": {"currency": str, "base_salary_floor": int, "base_salary_target": int},
    "location": {"work_modes": list, "office_cities": list, "relocate": bool},
    "background": {
        "age_18_or_over": bool, "background_check_ok": bool, "has_security_clearance": bool,
        "can_obtain_security_clearance": bool,
    },
    "eeo": {"gender": str, "race_ethnicity": str, "veteran_status": str, "disability_status": str},
}

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
YEAR_MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
YEAR = re.compile(r"^\d{4}$")  # education may give the year alone, as most resumes do
# A number on the resume: digits not glued to a letter, so "S3" doesn't count as a 3.
NUMBER = re.compile(r"(?<![A-Za-z\d.])\d+(?:[.,]\d+)*")
# A label, not an amount, so no metric has to back it: "SCD Type 2", "Type 1 and Type 2",
# "Type 1/2" (decision #50).
NOT_A_QUANTITY = re.compile(
    r"\bType\s+[1-6](?:\s*(?:/|,|and|or)\s*(?:Type\s+)?[1-6])*\b", re.IGNORECASE
)


class ProfileError(ValueError):
    """A profile file is missing, isn't valid TOML, or lacks a required field."""


@dataclass(frozen=True)
class Role:
    id: str
    title: str
    employer: str
    employer_blurb: str
    location: str
    start: str  # YYYY-MM
    end: str  # YYYY-MM, or "" for present


@dataclass(frozen=True)
class Project:
    id: str
    name: str
    status: str
    start: str
    url: str
    description: str


@dataclass(frozen=True)
class Education:
    degree: str
    school: str
    end: str


@dataclass(frozen=True)
class Evidence:
    id: str
    where: str  # a role or project id
    summary: str
    skills: tuple[str, ...]
    level: str
    metrics: tuple[str, ...]
    rounded: bool
    story: str


@dataclass(frozen=True)
class Skill:
    name: str
    aliases: tuple[str, ...]
    status: str


@dataclass(frozen=True)
class EvidenceBank:
    sample: bool
    roles: tuple[Role, ...]
    projects: tuple[Project, ...]
    education: tuple[Education, ...]
    evidence: tuple[Evidence, ...]
    skills: tuple[Skill, ...]

    def find_skill(self, term: str) -> Skill | None:
        """The skill a JD or resume term means, by name or alias, ignoring case. None = no entry,
        which means not covered."""
        key = term.strip().casefold()
        for skill in self.skills:
            if key in {skill.name.casefold(), *(alias.casefold() for alias in skill.aliases)}:
                return skill
        return None

    def evidence_for(self, skill_name: str) -> list[Evidence]:
        return [entry for entry in self.evidence if skill_name in entry.skills]

    def skill_level(self, skill_name: str) -> str | None:
        """Strongest level among the skill's evidence entries; None when there is none."""
        levels = {entry.level for entry in self.evidence_for(skill_name)}
        return next((level for level in LEVELS if level in levels), None)


@dataclass(frozen=True)
class Profile:
    folder: Path
    bank: EvidenceBank
    applicant: dict[str, Any]  # the Applicant Profile as parsed TOML; see APPLICANT_FIELDS
    resume: str


# ---------------------------------------------------------------- loading


def _read_toml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ProfileError(f"{path} not found")
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ProfileError(f"{path.name} is not valid TOML: {exc}") from exc


def _value(table: dict[str, Any], key: str, kind: type, where: str) -> Any:
    if key not in table:
        raise ProfileError(f"{where}: missing '{key}'")
    value = table[key]
    if not isinstance(value, kind) or (kind is int and isinstance(value, bool)):
        raise ProfileError(f"{where}: '{key}' should be {kind.__name__}, got {value!r}")
    return value


def _str(table: dict[str, Any], key: str, where: str) -> str:
    return _value(table, key, str, where).strip()


def _strs(table: dict[str, Any], key: str, where: str) -> tuple[str, ...]:
    values = _value(table, key, list, where)
    if not all(isinstance(value, str) for value in values):
        raise ProfileError(f"{where}: '{key}' should be a list of text")
    return tuple(value.strip() for value in values)


def _tables(data: dict[str, Any], key: str, file: str) -> list[dict[str, Any]]:
    tables = data.get(key, [])
    if not isinstance(tables, list) or not all(isinstance(t, dict) for t in tables):
        raise ProfileError(f"{file}: '{key}' should be a list of [[{key}]] tables")
    return tables


def _check_header(data: dict[str, Any], file: str) -> bool:
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ProfileError(f"{file}: schema_version should be {SCHEMA_VERSION}")
    return _value(data, "sample", bool, file)


def parse_evidence_bank(data: dict[str, Any]) -> EvidenceBank:
    file = EVIDENCE_BANK_FILE
    sample = _check_header(data, file)
    roles = []
    for i, t in enumerate(_tables(data, "roles", file)):
        where = f"{file} roles[{i}]"
        roles.append(Role(
            id=_str(t, "id", where), title=_str(t, "title", where),
            employer=_str(t, "employer", where), employer_blurb=t.get("employer_blurb", ""),
            location=_str(t, "location", where), start=_str(t, "start", where),
            end=_str(t, "end", where),
        ))
    projects = []
    for i, t in enumerate(_tables(data, "projects", file)):
        where = f"{file} projects[{i}]"
        projects.append(Project(
            id=_str(t, "id", where), name=_str(t, "name", where),
            status=_str(t, "status", where), start=_str(t, "start", where),
            url=t.get("url", ""), description=_str(t, "description", where),
        ))
    education = []
    for i, t in enumerate(_tables(data, "education", file)):
        where = f"{file} education[{i}]"
        education.append(Education(
            degree=_str(t, "degree", where), school=_str(t, "school", where),
            end=_str(t, "end", where),
        ))
    evidence = []
    for i, t in enumerate(_tables(data, "evidence", file)):
        where = f"{file} evidence[{i}]"
        evidence.append(Evidence(
            id=_str(t, "id", where), where=_str(t, "where", where),
            summary=_str(t, "summary", where), skills=_strs(t, "skills", where),
            level=_str(t, "level", where), metrics=_strs(t, "metrics", where),
            rounded=_value(t, "rounded", bool, where), story=_str(t, "story", where),
        ))
    skills_table = _value(data, "skills", dict, file)
    skills = []
    for name, t in skills_table.items():
        where = f"{file} skills.{name!r}"
        if not isinstance(t, dict):
            raise ProfileError(f"{where}: should be a table")
        skills.append(Skill(
            name=name.strip(), aliases=_strs(t, "aliases", where), status=_str(t, "status", where),
        ))
    return EvidenceBank(
        sample=sample, roles=tuple(roles), projects=tuple(projects), education=tuple(education),
        evidence=tuple(evidence), skills=tuple(skills),
    )


def parse_applicant_profile(data: dict[str, Any]) -> dict[str, Any]:
    file = APPLICANT_PROFILE_FILE
    _check_header(data, file)
    for section, fields in APPLICANT_FIELDS.items():
        table = _value(data, section, dict, file)
        for key, kind in fields.items():
            _value(table, key, kind, f"{file} [{section}]")
    return data


def load_profile(folder: Path) -> Profile:
    resume_path = folder / RESUME_FILE
    if not resume_path.is_file():
        raise ProfileError(f"{resume_path} not found")
    return Profile(
        folder=folder,
        bank=parse_evidence_bank(_read_toml(folder / EVIDENCE_BANK_FILE)),
        applicant=parse_applicant_profile(_read_toml(folder / APPLICANT_PROFILE_FILE)),
        resume=resume_path.read_text(encoding="utf-8"),
    )


# ---------------------------------------------------------------- checks


def resume_month(year_month: str) -> str:
    """'2021-03' -> 'Mar 2021', the one date format on the resume; a year alone stays '2018'."""
    if YEAR.match(year_month):
        return year_month
    year, month = year_month.split("-")
    return f"{MONTHS[int(month) - 1]} {year}"


def resume_sections(resume: str) -> dict[str, str]:
    """Text under each '## ' heading, in order."""
    sections: dict[str, str] = {}
    current = None
    for line in resume.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            sections[current] = ""
        elif current is not None:
            sections[current] += line + "\n"
    return sections


def _numbers(text: str) -> set[str]:
    """The amounts a text claims; labels such as "SCD Type 2" don't count."""
    text = NOT_A_QUANTITY.sub(" ", text)
    return {match.replace(",", "") for match in NUMBER.findall(text)}


def check_evidence_bank(bank: EvidenceBank) -> list[str]:
    problems = []
    if not bank.roles:
        problems.append("no roles: the work history is empty")

    places = [role.id for role in bank.roles] + [project.id for project in bank.projects]
    for dup in sorted({p for p in places if places.count(p) > 1}):
        problems.append(f"role/project id {dup!r} is used more than once")
    entry_ids = [entry.id for entry in bank.evidence]
    for dup in sorted({e for e in entry_ids if entry_ids.count(e) > 1}):
        problems.append(f"evidence id {dup!r} is used more than once")

    dates = [(f"role {r.id}", "start", r.start) for r in bank.roles]
    dates += [(f"role {r.id}", "end", r.end) for r in bank.roles if r.end]
    dates += [(f"project {p.id}", "start", p.start) for p in bank.projects]
    for owner, key, value in dates:
        if not YEAR_MONTH.match(value):
            problems.append(f"{owner}: {key} {value!r} should look like 2021-03")
    for school in bank.education:
        if not (YEAR_MONTH.match(school.end) or YEAR.match(school.end)):
            problems.append(
                f"education {school.school}: end {school.end!r} should look like 2018 or 2018-05"
            )
    for role in bank.roles:
        if role.end and role.end < role.start:
            problems.append(f"role {role.id}: ends before it starts")
    for project in bank.projects:
        if project.status not in PROJECT_STATUSES:
            problems.append(
                f"project {project.id}: status {project.status!r} not in {PROJECT_STATUSES}"
            )

    skill_names = {skill.name for skill in bank.skills}
    for entry in bank.evidence:
        if entry.where not in places:
            problems.append(f"evidence {entry.id}: where {entry.where!r} is no role or project id")
        if entry.level not in LEVELS:
            problems.append(f"evidence {entry.id}: level {entry.level!r} not in {LEVELS}")
        if not entry.skills:
            problems.append(f"evidence {entry.id}: lists no skills")
        for name in entry.skills:
            if name in skill_names:
                continue
            known = bank.find_skill(name)
            if known:
                problems.append(f"evidence {entry.id}: use the name {known.name!r}, not {name!r}")
            else:
                problems.append(f"evidence {entry.id}: skill {name!r} is not in [skills]")

    seen: dict[str, str] = {}
    for skill in bank.skills:
        if skill.status not in SKILL_STATUSES:
            problems.append(f"skill {skill.name!r}: status {skill.status!r} is not have/learning")
        if not bank.evidence_for(skill.name):
            problems.append(f"skill {skill.name!r} has no evidence entry (then it's not covered)")
        for term in (skill.name, *skill.aliases):
            key = term.casefold()
            if key in seen and seen[key] != skill.name:
                problems.append(f"{term!r} names both {seen[key]!r} and {skill.name!r}")
            seen.setdefault(key, skill.name)
    return problems


def check_applicant_profile(applicant: dict[str, Any]) -> list[str]:
    problems = []
    pay = applicant["compensation"]
    if not 0 < pay["base_salary_floor"] <= pay["base_salary_target"]:
        problems.append("compensation: need 0 < base_salary_floor <= base_salary_target")
    modes = applicant["location"]["work_modes"]
    if not modes or any(mode not in WORK_MODES for mode in modes):
        problems.append(f"location: work_modes {modes!r} should be some of {WORK_MODES}")
    if applicant["availability"]["notice_period_weeks"] < 0:
        problems.append("availability: notice_period_weeks can't be negative")
    return problems


def check_resume(
    resume: str,
    bank: EvidenceBank,
    applicant: dict[str, Any],
    known_skill: Callable[[str], bool] | None = None,
) -> list[str]:
    """Everything on the resume that doesn't trace to the profile. `known_skill` says whether a
    Skills item counts; by default it must be an Evidence Bank name or alias."""
    is_known = known_skill or (lambda item: bank.find_skill(item) is not None)
    problems = []
    lines = resume.splitlines()
    name = applicant["contact"]["name"]
    if not lines or lines[0].strip() != f"# {name}":
        problems.append(f"resume: first line should be '# {name}'")
    if applicant["contact"]["email"] not in resume:
        problems.append("resume: the email from the Applicant Profile is missing")

    sections = resume_sections(resume)
    if tuple(sections) != RESUME_HEADINGS:
        problems.append(f"resume: headings should be {list(RESUME_HEADINGS)}, got {list(sections)}")

    for role in bank.roles:
        end = resume_month(role.end) if role.end else "Present"
        for expected in (role.title, role.employer, f"{resume_month(role.start)} - {end}"):
            if expected not in resume:
                problems.append(f"resume: role {role.id} needs {expected!r}")
    for school in bank.education:
        for expected in (school.degree, school.school):
            if expected not in resume:
                problems.append(f"resume: education needs {expected!r}")

    for item in sections.get("Skills", "").replace("\n", " ").split(","):
        if item.strip() and not is_known(item):
            problems.append(f"resume: skill {item.strip()!r} has no Evidence Bank entry")

    allowed = set().union(*(_numbers(m) for entry in bank.evidence for m in entry.metrics))
    claims = sections.get("Summary", "")
    claims += "".join(
        line + "\n"
        for heading in ("Experience", "Projects")
        for line in sections.get(heading, "").splitlines()
        if line.startswith("- ")
    )
    for number in sorted(_numbers(claims) - allowed):
        problems.append(f"resume: the number {number} is in no Evidence Bank metric")
    return problems


def validate_profile(profile: Profile) -> list[str]:
    """Everything wrong with a loaded profile, as readable lines; [] means it's good."""
    problems = check_evidence_bank(profile.bank) + check_applicant_profile(profile.applicant)
    if profile.bank.sample != profile.applicant["sample"]:
        problems.append("one file says sample = true and the other doesn't")
    return problems + check_resume(profile.resume, profile.bank, profile.applicant)


# ---------------------------------------------------------------- command line


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m agents.profile", description="Check a candidate profile folder."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="parse the three files and run every check")
    check.add_argument("folder", nargs="?", help="default: PROFILE_DIR from .env, else data/sample")
    args = parser.parse_args(argv)

    folder = Path(args.folder) if args.folder else profile_dir()
    try:
        profile = load_profile(folder)
    except ProfileError as exc:
        print(f"FAIL {exc}")
        return 1
    problems = validate_profile(profile)
    bank = profile.bank
    learning = sum(skill.status == "learning" for skill in bank.skills)
    print(
        f"{folder}: {len(bank.roles)} roles, {len(bank.projects)} projects, "
        f"{len(bank.evidence)} evidence entries, {len(bank.skills)} skills ({learning} learning)"
    )
    if bank.sample:
        print("note: this is the fictional sample profile")
    for problem in problems:
        print(f"  - {problem}")
    print("FAIL" if problems else "OK")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
