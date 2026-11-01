"""Agent rules as versioned prompts (decisions #14, #30): each `.claude/skills/<name>/SKILL.md`
is the system prompt for one agent, with a `version:` line in its front matter.

    uv run python -m agents.skills check     # every skill's text matches its locked version
    uv run python -m agents.skills lock      # record new versions after a bump

`config/prompt_lock.toml` records each skill's version and a fingerprint of its text. Changing a
skill's text without bumping its version fails the check, so a prompt can only change through
the same loop as the triage rules (decision #22): propose, evaluate against the golden set, FL
approves, bump the version, record it in DECISIONS.md.
"""

import argparse
import hashlib
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

from pipeline.config import REPO_ROOT

SKILLS_DIR = REPO_ROOT / ".claude" / "skills"
PROMPT_LOCK = REPO_ROOT / "config" / "prompt_lock.toml"
LOCK_HEADER = """\
# Version and text fingerprint of every agent prompt (.claude/skills/*/SKILL.md), decision #30.
# A test fails when a skill's text changes without a version bump. Written by:
#   uv run python -m agents.skills lock
"""


class SkillError(ValueError):
    """A skill file is missing or its front matter is incomplete."""


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    version: int
    body: str  # the prompt: everything after the front matter, line endings normalized

    @property
    def prompt_version(self) -> str:
        return f"{self.name}@{self.version}"

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(self.body.encode("utf-8")).hexdigest()


def parse_skill(text: str, where: str) -> Skill:
    """Front matter between the first two '---' lines (`key: value`), then the prompt body."""
    lines = text.replace("\r\n", "\n").split("\n")
    if not lines or lines[0].strip() != "---" or "---" not in (line.strip() for line in lines[1:]):
        raise SkillError(f"{where}: should start with front matter between '---' lines")
    end = next(i for i, line in enumerate(lines[1:], start=1) if line.strip() == "---")
    meta = {}
    for line in lines[1:end]:
        key, sep, value = line.partition(":")
        if sep:
            meta[key.strip()] = value.strip()
    for key in ("name", "description", "version"):
        if not meta.get(key):
            raise SkillError(f"{where}: front matter needs '{key}'")
    if not meta["version"].isdigit():
        raise SkillError(f"{where}: version should be a whole number, got {meta['version']!r}")
    return Skill(
        name=meta["name"], description=meta["description"], version=int(meta["version"]),
        body="\n".join(lines[end + 1:]).strip() + "\n",
    )


def load_skill(name: str, skills_dir: Path = SKILLS_DIR) -> Skill:
    path = skills_dir / name / "SKILL.md"
    if not path.is_file():
        raise SkillError(f"{path} not found")
    skill = parse_skill(path.read_text(encoding="utf-8"), str(path))
    if skill.name != name:
        raise SkillError(f"{path}: name {skill.name!r} should match its folder {name!r}")
    return skill


def load_all_skills(skills_dir: Path = SKILLS_DIR) -> dict[str, Skill]:
    return {
        path.parent.name: load_skill(path.parent.name, skills_dir)
        for path in sorted(skills_dir.glob("*/SKILL.md"))
    }


def read_lock(path: Path = PROMPT_LOCK) -> dict[str, dict]:
    if not path.is_file():
        return {}
    return tomllib.loads(path.read_text(encoding="utf-8")).get("skills", {})


def lock_problems(skills: dict[str, Skill], lock: dict[str, dict]) -> list[str]:
    """What stops the lock from matching the skills; [] means every prompt is at its version."""
    problems = []
    for name, skill in skills.items():
        entry = lock.get(name)
        if entry is None:
            problems.append(f"{name}: not in the prompt lock (run: python -m agents.skills lock)")
        elif skill.version < entry["version"]:
            problems.append(f"{name}: version {skill.version} is below locked {entry['version']}")
        elif skill.version == entry["version"] and skill.fingerprint != entry["sha256"]:
            problems.append(
                f"{name}: text changed but version is still {skill.version} (bump it, and record "
                "the change through the rules loop)"
            )
        elif skill.version > entry["version"]:
            problems.append(f"{name}: version bumped to {skill.version}, lock not updated yet")
    for name in sorted(set(lock) - set(skills)):
        problems.append(f"{name}: in the prompt lock but the skill file is gone")
    return problems


def write_lock(skills: dict[str, Skill], path: Path = PROMPT_LOCK) -> None:
    """Record every skill's version and fingerprint. Refuses a text change without a bump."""
    stale = [p for p in lock_problems(skills, read_lock(path)) if "text changed" in p]
    if stale:
        raise SkillError("; ".join(stale))
    parts = [LOCK_HEADER]
    for name in sorted(skills):
        skill = skills[name]
        parts.append(f"\n[skills.{name}]\nversion = {skill.version}\n")
        parts.append(f'sha256 = "{skill.fingerprint}"\n')
    path.write_text("".join(parts), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m agents.skills", description="Check or update the prompt lock."
    )
    parser.add_argument("command", choices=("check", "lock"), nargs="?", default="check")
    args = parser.parse_args(argv)
    skills = load_all_skills()
    if args.command == "lock":
        try:
            write_lock(skills)
        except SkillError as exc:
            print(f"FAIL {exc}")
            return 1
        print(f"locked {len(skills)} skills: "
              + ", ".join(s.prompt_version for s in skills.values()))
        return 0
    problems = lock_problems(skills, read_lock())
    for problem in problems:
        print(f"  - {problem}")
    print("FAIL" if problems else f"OK: {', '.join(s.prompt_version for s in skills.values())}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
