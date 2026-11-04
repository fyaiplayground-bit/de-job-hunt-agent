"""The resume path: resume.md → structured data → PDF → checks (decision #36)."""

from pathlib import Path

import pytest
import typst
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject

from agents.pdf_checks import (
    check_pdf,
    find_bad_characters,
    find_missing_lines,
    find_non_ascii_date_ranges,
    font_is_embedded,
)
from agents.profile import load_profile
from agents.render_resume import FONTS, main, pdf_file_name, render_pdf, render_profile
from agents.resume_doc import ResumeFormatError, parse_resume

SAMPLE = Path(__file__).parent.parent / "data" / "sample"
EN_DASH = chr(0x2013)
LIGATURE_FI = chr(0xFB01)
ZERO_WIDTH_SPACE = chr(0x200B)

SHORT_RESUME = """# Pat Doe

Pat Doe contact line

## Summary

One line of summary,
and a second.

## Experience

**Engineer** · Acme · Denver, CO
Jan 2020 - Present

- Built a thing
- Built another thing

**Analyst** · Beta
Jan 2018 - Dec 2019

## Skills

SQL, Python

## Education

**B.A. Math** · Front Range State University · May 2017
"""


@pytest.fixture
def sample_doc():
    return parse_resume(load_profile(SAMPLE).resume)


def compile_typst(tmp_path: Path, source: str) -> Path:
    """A small PDF from raw Typst source, to give a check something bad to find."""
    typ = tmp_path / "bad.typ"
    typ.write_text('#set text(font: "Liberation Sans")\n' + source, encoding="utf-8")
    pdf = tmp_path / "bad.pdf"
    pdf.write_bytes(typst.compile(str(typ), font_paths=[str(FONTS)], ignore_system_fonts=True))
    return pdf


# ---------------------------------------------------------------- reading resume.md


def test_parse_reads_the_whole_format():
    doc = parse_resume(SHORT_RESUME)
    assert (doc.name, doc.headline, doc.contact) == ("Pat Doe", "", "Pat Doe contact line")
    assert [s.heading for s in doc.sections] == ["Summary", "Experience", "Skills", "Education"]
    assert doc.sections[0].text == "One line of summary, and a second."
    engineer, analyst = doc.sections[1].entries
    assert engineer.title == "Engineer"
    assert engineer.detail == " · Acme · Denver, CO"
    assert engineer.dates == "Jan 2020 - Present"
    assert engineer.bullets == ("Built a thing", "Built another thing")
    assert analyst.bullets == ()
    assert doc.sections[3].entries[0].dates == ""


def test_parse_reads_an_optional_headline(sample_doc):
    assert sample_doc.headline == "Data Engineer · SQL / Python / AWS"
    assert sample_doc.contact.startswith("Denver, CO")


def test_lines_are_in_reading_order_without_markdown():
    lines = parse_resume(SHORT_RESUME).lines()
    assert lines[:4] == [
        "Pat Doe",
        "Pat Doe contact line",
        "Summary",
        "One line of summary, and a second.",
    ]
    assert "Engineer · Acme · Denver, CO" in lines
    assert not any("**" in line or line.startswith("- ") for line in lines)


@pytest.mark.parametrize(
    "resume, message",
    [
        ("no title\n## Summary\nText\n", "first line"),
        ("# Pat\ncontact\n", "no '## '"),
        ("# Pat\n## Summary\nText\n", "contact line"),
        ("# Pat\na\nb\nc\n## Summary\nText\n", "contact line"),
        ("# Pat\ncontact\n## Summary\n- a loose bullet\n", "bullet outside"),
        ("# Pat\ncontact\n## Experience\nsome text\n**Job** · Co\n", "mixed"),
        ("# Pat\ncontact\n## Experience\n**Job** · Co\n2020\nanother line\n", "where this line"),
        ("# Pat\ncontact\n## Experience\n**Job** · Co\n- bullet\nstray line\n", "where this line"),
    ],
)
def test_parse_refuses_what_it_cannot_place(resume, message):
    with pytest.raises(ResumeFormatError, match=message):
        parse_resume(resume)


# ---------------------------------------------------------------- rendering


def test_sample_renders_to_one_page_and_passes_every_check(sample_doc, tmp_path):
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(render_pdf(sample_doc))
    report = check_pdf(pdf, expected_lines=sample_doc.lines())
    assert report.failures == ()
    assert report.pages == 1


def test_same_input_gives_a_byte_identical_pdf(sample_doc):
    assert render_pdf(sample_doc) == render_pdf(sample_doc)


def test_markup_in_the_content_stays_plain_text(tmp_path):
    """Content is data: Typst markup in a bullet must print as written, never run."""
    bullet = "Saved $5 and #1 *rank* _here_ = [a] <b> @c 50% -- 2020"
    doc = parse_resume(f"# Pat\ncontact\n## Experience\n**Job** · Co\n- {bullet}\n")
    pdf = tmp_path / "markup.pdf"
    pdf.write_bytes(render_pdf(doc))
    report = check_pdf(pdf, expected_lines=[bullet])
    assert report.failures == ()
    assert bullet in report.text


def test_render_profile_writes_the_pdf_and_review_page(tmp_path):
    result = render_profile(SAMPLE, tmp_path)
    assert result.ok
    assert result.pdf == tmp_path / "Alex_Sample.pdf"
    page = result.review.read_text(encoding="utf-8")
    assert 'href="Alex_Sample.pdf"' in page
    assert "data:image/png;base64," in page
    assert "Quillfeather Outdoor" in page
    assert "ATS" in page


def test_render_profile_reports_a_claim_the_evidence_bank_cannot_back(tmp_path):
    folder = tmp_path / "profile"
    folder.mkdir()
    for path in SAMPLE.iterdir():
        (folder / path.name).write_bytes(path.read_bytes())
    resume = folder / "resume.md"
    resume.write_text(
        resume.read_text(encoding="utf-8").replace("6 source systems", "60 source systems"),
        encoding="utf-8",
    )
    result = render_profile(folder, tmp_path / "out")
    assert not result.ok
    assert result.profile_problems == ("resume: the number 60 is in no Evidence Bank metric",)


def test_command_exit_codes(tmp_path, capsys):
    assert main(["--folder", str(SAMPLE), "--out", str(tmp_path)]) == 0
    assert "OK: 1 page(s)" in capsys.readouterr().out
    assert main(["--folder", str(tmp_path / "nothing"), "--out", str(tmp_path)]) == 1
    assert "FAIL" in capsys.readouterr().out


def test_pdf_file_name():
    assert pdf_file_name("Alex Sample") == "Alex_Sample.pdf"
    assert pdf_file_name("  ") == "resume.pdf"


# ---------------------------------------------------------------- each check catches its defect


def test_two_pages_fail(tmp_path):
    pdf = compile_typst(tmp_path, "Page one\n#pagebreak()\nPage two\n")
    report = check_pdf(pdf)
    assert report.pages == 2
    assert report.failures == ("expected 1 page(s), found 2",)


def test_a_pdf_without_text_fails(tmp_path):
    writer = PdfWriter()
    writer.add_blank_page(612, 792)
    pdf = tmp_path / "blank.pdf"
    with pdf.open("wb") as handle:
        writer.write(handle)
    report = check_pdf(pdf, expected_lines=["anything"])
    assert report.failures == ("no text layer: an ATS would read an empty resume",)


def test_an_unreadable_file_fails_without_raising(tmp_path):
    pdf = tmp_path / "broken.pdf"
    pdf.write_bytes(b"this is not a pdf")
    assert check_pdf(pdf).failures[0].startswith("can't read the PDF")
    assert check_pdf(tmp_path / "absent.pdf").failures[0].startswith("can't read the PDF")


def test_a_missing_line_fails(tmp_path):
    pdf = compile_typst(tmp_path, "Built a pipeline\n")
    report = check_pdf(pdf, expected_lines=["Built a pipeline", "Led a migration"])
    assert report.failures == ("missing from the text layer: 'Led a migration'",)


def test_lines_out_of_order_are_named():
    problems = find_missing_lines("Experience\nSummary\n", ["Summary", "Experience"])
    assert problems == ["out of reading order: 'Experience'"]


def test_line_wraps_do_not_count_as_missing():
    text = "reports for carrier-\ncost at example.com/\nalex and more\nwords here"
    assert find_missing_lines(text, ["carrier-cost at example.com/alex and more words here"]) == []


def test_required_text_is_checked(tmp_path):
    pdf = compile_typst(tmp_path, "Apache Airflow DAGs\n")
    report = check_pdf(pdf, required=["Apache Airflow", "dbt"])
    assert report.failures == ("required text is missing: 'dbt'",)


def test_a_date_with_a_long_dash_fails(tmp_path):
    pdf = compile_typst(tmp_path, f'#"Mar 2021 {EN_DASH} Present"\n')
    report = check_pdf(pdf)
    assert len(report.failures) == 1
    assert "non-ASCII dash (U+2013)" in report.failures[0]


def test_a_date_with_a_hyphen_passes_and_a_quantity_with_a_long_dash_is_left_alone():
    assert find_non_ascii_date_ranges("Mar 2021 - Present") == []
    assert find_non_ascii_date_ranges(f"2000{EN_DASH}5000 requests/s") == []


def test_ligature_and_invisible_characters_are_named():
    assert find_bad_characters(f"of{LIGATURE_FI}ce") == ["U+FB01"]
    assert find_bad_characters(f"da{ZERO_WIDTH_SPACE}ta") == ["U+200B"]
    assert find_bad_characters("plain text · with • bullets\n") == []


def test_font_embedded_check(tmp_path):
    bare = DictionaryObject({NameObject("/BaseFont"): NameObject("/Helvetica")})
    assert not font_is_embedded(bare)
    # The template's fonts are all embedded: the sample check above would fail otherwise.
    pdf = compile_typst(tmp_path, "Some text\n")
    assert check_pdf(pdf).failures == ()


def test_a_thin_page_warns_but_does_not_fail(tmp_path):
    report = check_pdf(compile_typst(tmp_path, "Just one line\n"))
    assert report.ok
    assert report.fill < 0.8
    assert "looks thin" in report.warnings[0]


def test_a_full_page_does_not_warn(tmp_path):
    pdf = compile_typst(tmp_path, "#v(1fr)\nLast line at the bottom\n")
    report = check_pdf(pdf)
    assert report.warnings == ()
    assert report.fill > 0.8
