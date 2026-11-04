# Adapted from ai-job-search (https://github.com/ai-job-search-dev/ai-job-search),
# tools/verify_pdf.py at commit 83c788d.
# Copyright (c) 2026 Mads Lorentzen. MIT License; full text in LICENSES/ai-job-search-MIT.txt
#
# Changes from the original: kept the text folding and the date-range check (TYPOGRAPHIC_FOLDS
# through find_non_ascii_date_ranges) unchanged; removed the command line, the --dump-text file
# writing and the Poppler fallback. Everything after the "our checks" line is ours; the layout
# idea comes from their tools/verify_layout.py, rebuilt on pypdf's text positions.
"""Check a finished resume PDF the way an ATS will read it (decision #36).

The checks read the PDF, not the source: what matters is what a parser gets out of the file.
A failure means the PDF must not go out; a warning is for a person to look at.

    report = check_pdf(path, expected_lines=doc.lines(), required=["Apache Airflow"])
"""

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PyPdfError

# Typographic substitutions the moderncv/cover.cls templates produce from plain
# source text, mapped back to what a user types into --contains. LaTeX ligatures
# ' into U+2019 and -- into U+2013, so "Master's degree" and "2016-2024" are
# absent from the text layer of a CV that plainly contains them (#385). Applied
# to both sides of the comparison; the extracted dump is never rewritten.
TYPOGRAPHIC_FOLDS = str.maketrans(
    {
        "\u2018": "'",  # ` -> quoteleft
        "\u2019": "'",  # ' -> quoteright (the possessive apostrophe)
        "\u201c": '"',  # `` -> quotedblleft
        "\u201d": '"',  # '' -> quotedblright
        "\u2013": "-",  # -- -> endash (the \cventry date-range case)
        "\u2014": "-",  # --- -> emdash
        "\u00a0": " ",  # ~ -> no-break space
    }
)


def normalize_text(text):
    """Fold a string for comparison: NFC, typographic punctuation, whitespace.

    NFC covers the pdflatex text layer, which without T1 font encoding stores
    accented letters decomposed (`e` + U+0300) while a user types them
    precomposed (U+00E8); both forms fold to the same string (#384). The fold
    applies to what is compared, never to what is dumped: the date-range rule in
    `05-cv-templates.md` still needs the raw en-dash visible in `--dump-text`.
    """
    text = unicodedata.normalize("NFC", text).translate(TYPOGRAPHIC_FOLDS)
    return " ".join(text.split())


# Dash-like code points a year must never be joined to in a date range. U+2013 is
# what LaTeX makes from `--` and what the documented Workday import dropped; the
# rest are the other Unicode dashes and the minus sign, which a parser that splits
# a range only on U+002D treats the same way.
NON_ASCII_DASHES = "\u2010\u2011\u2012\u2013\u2014\u2015\u2212"
# A year is four digits standing alone: without the digit boundaries, `2000`
# inside `120000` or `12000` made a budget or throughput range read as a date.
_YEAR = r"(?<!\d)(?:19|20)\d{2}(?!\d)"
# Horizontal whitespace only between the year and the dash: `\s*` also matched
# a newline, so a year ending one line joined a dash opening the next (a bullet,
# a wrapped prose line) and an ASCII date was reported as U+2013.
NON_ASCII_DATE_RANGE = re.compile(
    rf"{_YEAR}[^\S\n]*[{NON_ASCII_DASHES}]|[{NON_ASCII_DASHES}][^\S\n]*{_YEAR}"
)
# The whitespace-delimited tokens touching the dash on either side. A range whose
# two ends are both BARE numbers is a date only when both are years: `EUR 1500-2000`
# and `2000-5000 requests/s` are quantities that happen to contain a year-shaped
# number, and the guide tells users to keep `--` in exactly those. A composite
# token (`03/2016`, `01.2016`, `2016-03`, `2016/17`) is not a bare number, so a
# numerically formatted date range still falls through to the year rule.
_TOKEN_BEFORE = re.compile(r"(\S+)[^\S\n]*$")
_TOKEN_AFTER = re.compile(r"^[^\S\n]*(\S+)")
_BARE_NUMBER = re.compile(r"\d+(?:[.,]\d+)*[kKmM%]?")
_BARE_YEAR = re.compile(r"(?:19|20)\d{2}")
_OUTER_PUNCTUATION = ".,;:!?()[]{}\"'"


def _bare_number(token):
    """The token with outer punctuation stripped, if it is a bare number, else None.

    A dotted or comma-separated token whose groups include a year (`01.2016`,
    `31.07.2024`) is a date written numerically, not a quantity, and is left to
    the year rule; `1,234.56` and `2.0M` have no year group and stay numbers.
    """
    core = token.strip(_OUTER_PUNCTUATION)
    if not _BARE_NUMBER.fullmatch(core):
        return None
    groups = re.split(r"[.,]", core.rstrip("kKmM%"))
    if len(groups) > 1 and any(_BARE_YEAR.fullmatch(g) for g in groups):
        return None
    return core


_TWO_DIGIT_YEAR = re.compile(r"\d{2}")


def _quantity_range(line, dash_index):
    """True when both sides of the dash are bare numbers and not a date pair.

    A date pair is two years (`2016-2024`) or a year and a two-digit year
    (`2016-17`, `2019-20`): the short form is how academic years and seasons
    are written, and it was caught before the quantity rule existed. Anything
    else with bare numbers on both sides is a quantity (`1500-2000`,
    `2000-5000`) and is left alone.
    """
    before = _TOKEN_BEFORE.search(line[:dash_index])
    after = _TOKEN_AFTER.search(line[dash_index + 1 :])
    if not before or not after:
        return False
    left, right = _bare_number(before.group(1)), _bare_number(after.group(1))
    if left is None or right is None:
        return False
    if _BARE_YEAR.fullmatch(left) and (_BARE_YEAR.fullmatch(right) or _TWO_DIGIT_YEAR.fullmatch(right)):
        return False
    return True


def find_non_ascii_date_ranges(text):
    """Return (line, dash) for every year joined to a non-ASCII dash in raw text.

    Works on the raw text layer, never on `normalize_text()` output: the fold
    maps U+2013 back to `-` so `--contains "2016-2024"` can match what the
    template renders, which is exactly why `--contains` cannot see this defect.
    A year on either side of the dash is enough ("Mar 2016 - Jul 2016",
    "2016 - Present"), so the check is locale-agnostic. A range whose two ends
    are both bare numbers is a date only when both are years: "EUR 600k-1M",
    "EUR 1500-2000" and "2000-5000 requests/s" are quantities and are left
    alone, while a numerically formatted date ("03/2016-07/2024", "2016-03-2024-07")
    is not a bare number on either side and is still caught.
    """
    hits = []
    for match in NON_ASCII_DATE_RANGE.finditer(text):
        dash = next(c for c in match.group(0) if c in NON_ASCII_DASHES)
        line_start = text.rfind("\n", 0, match.start()) + 1
        line_end = text.find("\n", match.end())
        line_end = line_end if line_end != -1 else len(text)
        line = text[line_start:line_end]
        if _quantity_range(line, match.start() + match.group(0).index(dash) - line_start):
            continue
        hits.append((" ".join(line.split()), dash))
    return hits


# ---------------------------------------------------------------- our checks


EXPECTED_PAGES = 1
# Below this the page looks unfinished: text should reach 80% of the way down.
MIN_FILL = 0.8
FONT_FILE_KEYS = ("/FontFile", "/FontFile2", "/FontFile3")
# A line break after these leaves a space in the text layer that the source doesn't have.
BREAK_AFTER = re.compile(r"([-/])\s+")
# Invisible, unassigned or private-use characters; a parser can't search for them.
BAD_CATEGORIES = {"Cc", "Cf", "Cn", "Co", "Cs"}
LIGATURES = range(0xFB00, 0xFB07)
REPLACEMENT_CHARACTER = chr(0xFFFD)


@dataclass(frozen=True)
class PdfReport:
    pages: int
    text: str  # the raw text layer: what an ATS reads
    fill: float  # how far down the last page the text reaches, 0 to 1
    failures: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.failures


def _comparable(text: str) -> str:
    return BREAK_AFTER.sub(r"\1", normalize_text(text))


def find_missing_lines(text: str, lines: Iterable[str]) -> list[str]:
    """Problems with lines that should appear in this order in the text layer."""
    layer = _comparable(text)
    problems = []
    position = 0
    for line in lines:
        wanted = _comparable(line)
        found = layer.find(wanted, position)
        if found != -1:
            position = found + len(wanted)
        elif wanted in layer:
            problems.append(f"out of reading order: {line!r}")
        else:
            problems.append(f"missing from the text layer: {line!r}")
    return problems


def find_bad_characters(text: str) -> list[str]:
    """Characters in the text layer a parser would trip on, as U+XXXX, one entry per character."""
    bad = {
        c for c in text
        if c not in "\n\r\t"
        and (unicodedata.category(c) in BAD_CATEGORIES
             or ord(c) in LIGATURES
             or c == REPLACEMENT_CHARACTER)
    }
    return [f"U+{ord(c):04X}" for c in sorted(bad)]


def font_is_embedded(font) -> bool:
    """True when the font's own file travels inside the PDF (composite fonts keep it one level
    down, in their descendant font)."""
    if "/DescendantFonts" in font:
        font = font["/DescendantFonts"][0].get_object()
    descriptor = font.get("/FontDescriptor")
    return descriptor is not None and any(key in descriptor.get_object() for key in FONT_FILE_KEYS)


def _unembedded_fonts(reader: PdfReader) -> list[str]:
    names = set()
    for page in reader.pages:
        fonts = page.get("/Resources", {}).get("/Font", {})
        for font in fonts.values():
            font = font.get_object()
            if not font_is_embedded(font):
                names.add(str(font.get("/BaseFont", "unnamed font")))
    return sorted(names)


def _text_and_fill(page) -> tuple[str, float]:
    """The page's text, and how far down the page its lowest text sits (0 top, 1 bottom)."""
    lowest: list[float] = []

    def visit(text, cm, tm, _font, _size) -> None:
        if text.strip():
            lowest.append(tm[4] * cm[1] + tm[5] * cm[3] + cm[5])

    text = page.extract_text(visitor_text=visit) or ""
    height = float(page.mediabox.height)
    return text, (height - min(lowest)) / height if lowest else 0.0


def check_pdf(
    pdf: Path,
    expected_lines: Iterable[str] = (),
    required: Iterable[str] = (),
    pages: int = EXPECTED_PAGES,
    min_fill: float = MIN_FILL,
) -> PdfReport:
    """Everything wrong with a PDF. Never raises on a bad file: an unreadable PDF is a failure."""
    try:
        reader = PdfReader(pdf)
        parts = [_text_and_fill(page) for page in reader.pages]
    except (OSError, PyPdfError) as exc:
        return PdfReport(0, "", 0.0, (f"can't read the PDF: {exc}",), ())
    text = "\n".join(part for part, _ in parts)
    fill = parts[-1][1] if parts else 0.0

    failures = []
    if len(parts) != pages:
        failures.append(f"expected {pages} page(s), found {len(parts)}")
    if not normalize_text(text):
        failures.append("no text layer: an ATS would read an empty resume")
        return PdfReport(len(parts), text, fill, tuple(failures), ())

    failures += find_missing_lines(text, expected_lines)
    failures += [
        f"required text is missing: {item!r}"
        for item in required
        if _comparable(item) not in _comparable(text)
    ]
    failures += [
        f"date joined by a non-ASCII dash (U+{ord(dash):04X}): {line!r}"
        for line, dash in find_non_ascii_date_ranges(text)
    ]
    failures += [f"font not embedded: {name}" for name in _unembedded_fonts(reader)]
    bad = find_bad_characters(text)
    if bad:
        failures.append(f"characters a parser can't search: {', '.join(bad)}")

    warnings = []
    if len(parts) == pages and fill < min_fill:
        warnings.append(f"the page looks thin: text reaches {fill:.0%} of the way down")
    return PdfReport(len(parts), text, fill, tuple(failures), tuple(warnings))
