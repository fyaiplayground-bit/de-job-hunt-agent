"""Read a resume.md into structured data for the PDF template (decision #36).

Every resume, master or tailored, uses this one format:

    # Name

    Optional headline naming the target role
    Contact line

    ## Summary
    Plain text.

    ## Experience
    **Title** · Employer · City
    Mar 2021 - Present

    - Bullet

    ## Skills
    Plain text.

A section holds either plain text or entries that start with a **bold** line. Anything else is
an error rather than a guess, so a resume can't lose a line on its way to the PDF.
"""

import re
from dataclasses import asdict, dataclass

# "**Title** rest of the line"
ENTRY_START = re.compile(r"^\*\*(?P<title>[^*]+)\*\*(?P<detail>.*)$")


class ResumeFormatError(ValueError):
    """A resume.md doesn't follow the format above."""


@dataclass(frozen=True)
class Entry:
    title: str
    detail: str  # what follows the bold title on its line, as written
    dates: str
    bullets: tuple[str, ...]

    @property
    def title_line(self) -> str:
        return self.title + self.detail


@dataclass(frozen=True)
class Section:
    heading: str
    text: str
    entries: tuple[Entry, ...]


@dataclass(frozen=True)
class ResumeDoc:
    name: str
    headline: str
    contact: str
    sections: tuple[Section, ...]

    def lines(self) -> list[str]:
        """Every piece of text the PDF must show, in reading order."""
        lines = [self.name, *filter(None, [self.headline]), self.contact]
        for section in self.sections:
            lines.append(section.heading)
            if section.text:
                lines.append(section.text)
            for entry in section.entries:
                lines.append(entry.title_line)
                if entry.dates:
                    lines.append(entry.dates)
                lines.extend(entry.bullets)
        return lines

    def to_data(self) -> dict:
        """The JSON-ready shape templates/resume.typ reads."""
        return asdict(self)


def _parse_section(heading: str, lines: list[str]) -> Section:
    text: list[str] = []
    entries: list[Entry] = []
    title = detail = dates = ""
    bullets: list[str] = []

    def finish_entry() -> None:
        if title:
            entries.append(Entry(title, detail, dates, tuple(bullets)))

    for line in lines:
        start = ENTRY_START.match(line)
        if start:
            if text:
                raise ResumeFormatError(f"{heading}: text and entries are mixed: {line!r}")
            finish_entry()
            title, detail = start["title"].strip(), start["detail"].rstrip()
            dates, bullets = "", []
        elif line.startswith("- "):
            if not title:
                raise ResumeFormatError(f"{heading}: a bullet outside any entry: {line!r}")
            bullets.append(line[2:].strip())
        elif title:
            if dates or bullets:
                raise ResumeFormatError(f"{heading}: don't know where this line goes: {line!r}")
            dates = line.strip()
        else:
            text.append(line.strip())
    finish_entry()
    return Section(heading, " ".join(text), tuple(entries))


def parse_resume(resume: str) -> ResumeDoc:
    lines = [line.rstrip() for line in resume.splitlines() if line.strip()]
    if not lines or not lines[0].startswith("# "):
        raise ResumeFormatError("the first line should be '# Name'")
    name = lines[0][2:].strip()

    first_heading = next((i for i, line in enumerate(lines) if line.startswith("## ")), None)
    if first_heading is None:
        raise ResumeFormatError("no '## ' section headings")
    top = lines[1:first_heading]
    if len(top) not in (1, 2):
        raise ResumeFormatError(
            f"above the first section there should be a contact line, optionally with a headline "
            f"above it; found {len(top)} lines"
        )
    headline, contact = ("", top[0]) if len(top) == 1 else (top[0], top[1])

    starts = [i for i, line in enumerate(lines) if line.startswith("## ")]
    sections = [
        _parse_section(lines[start][3:].strip(), lines[start + 1 : end])
        for start, end in zip(starts, [*starts[1:], len(lines)], strict=True)
    ]
    return ResumeDoc(name, headline, contact, tuple(sections))
