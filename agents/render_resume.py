"""Turn a profile's resume.md into a one-page PDF and check it (decision #36).

    uv run python -m agents.render_resume                 # the folder in PROFILE_DIR
    uv run python -m agents.render_resume --folder private --out output/resume

Writes <Name>.pdf and review.html (the page beside the text an ATS reads) to output/resume/.

Same resume.md + same template + same fonts → the same PDF, byte for byte: system fonts are
ignored and the template writes no creation date.
"""

import argparse
import base64
import html
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import typst

from agents.pdf_checks import PdfReport, check_pdf
from agents.profile import ProfileError, check_resume, load_profile
from agents.resume_doc import ResumeDoc, ResumeFormatError, parse_resume
from pipeline.config import profile_dir

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = REPO_ROOT / "templates" / "resume.typ"
FONTS = REPO_ROOT / "templates" / "fonts"
DEFAULT_OUT = REPO_ROOT / "output" / "resume"
REVIEW_FILE = "review.html"
PREVIEW_PPI = 110


@dataclass(frozen=True)
class RenderResult:
    pdf: Path
    review: Path
    report: PdfReport
    profile_problems: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return self.report.ok and not self.profile_problems


def _compile(doc: ResumeDoc, template: Path, **options) -> bytes | list[bytes]:
    return typst.compile(
        str(template),
        font_paths=[str(FONTS)],
        ignore_system_fonts=True,
        sys_inputs={"data": json.dumps(doc.to_data(), ensure_ascii=False)},
        **options,
    )


def render_pdf(doc: ResumeDoc, template: Path = TEMPLATE) -> bytes:
    return _compile(doc, template)


def render_preview(doc: ResumeDoc, template: Path = TEMPLATE) -> list[bytes]:
    """One PNG per page, for the review page; any browser shows these, not all show a PDF."""
    pages = _compile(doc, template, format="png", ppi=PREVIEW_PPI)
    return pages if isinstance(pages, list) else [pages]


def pdf_file_name(name: str) -> str:
    """'Alex Sample' -> 'Alex_Sample.pdf'."""
    return (re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_") or "resume") + ".pdf"


def review_page(pdf_name: str, previews: list[bytes], result_lines: list[str], text: str) -> str:
    """The rendered page on the left, the text an ATS reads on the right."""
    items = "".join(f"<li>{html.escape(line)}</li>" for line in result_lines)
    images = "".join(
        f'<img alt="page {number}" src="data:image/png;base64,{base64.b64encode(png).decode()}">'
        for number, png in enumerate(previews, start=1)
    )
    name = html.escape(pdf_name)
    return f"""<!doctype html>
<html lang="zh"><head><meta charset="utf-8"><title>简历检查</title>
<style>
  body {{ margin: 0; font: 14px/1.5 system-ui, sans-serif; color: #222; background: #fff; }}
  header {{ padding: 8px 16px; border-bottom: 1px solid #ccc; }}
  h1 {{ font-size: 16px; margin: 0 0 4px; }}
  ul {{ margin: 0; padding-left: 20px; }}
  main {{ display: flex; height: calc(100vh - 140px); min-height: 500px; }}
  .page {{ flex: 1; overflow: auto; padding: 8px; background: #eee; }}
  img {{ display: block; width: 100%; max-width: 900px; margin: 0 auto 8px; background: #fff; }}
  section {{ flex: 1; overflow: auto; padding: 8px 16px; }}
  h2 {{ font-size: 14px; margin: 0 0 8px; }}
  pre {{ white-space: pre-wrap; margin: 0; font: 13px/1.5 ui-monospace, Consolas, monospace; }}
</style></head><body>
<header><h1><a href="{name}">{name}</a></h1><ul>{items}</ul></header>
<main>
  <div class="page">{images}</div>
  <section><h2>ATS 读到的文字</h2><pre>{html.escape(text)}</pre></section>
</main>
</body></html>
"""


def result_lines(report: PdfReport, profile_problems: tuple[str, ...]) -> list[str]:
    lines = [f"FAIL {problem}" for problem in (*profile_problems, *report.failures)]
    lines += [f"WARN {warning}" for warning in report.warnings]
    lines.append(
        f"{'OK' if report.ok and not profile_problems else 'FAIL'}: "
        f"{report.pages} page(s), text reaches {report.fill:.0%} of the way down"
    )
    return lines


def render_profile(folder: Path, out: Path = DEFAULT_OUT) -> RenderResult:
    """Render a profile's resume, check the PDF, and write the PDF and the review page."""
    profile = load_profile(folder)
    doc = parse_resume(profile.resume)
    out.mkdir(parents=True, exist_ok=True)
    pdf = out / pdf_file_name(doc.name)
    pdf.write_bytes(render_pdf(doc))

    report = check_pdf(pdf, expected_lines=doc.lines())
    problems = tuple(check_resume(profile.resume, profile.bank, profile.applicant))
    review = out / REVIEW_FILE
    review.write_text(
        review_page(pdf.name, render_preview(doc), result_lines(report, problems), report.text),
        encoding="utf-8",
    )
    return RenderResult(pdf, review, report, problems)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m agents.render_resume", description="Render and check a resume PDF."
    )
    parser.add_argument("--folder", help="default: PROFILE_DIR from .env, else data/sample")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")

    folder = Path(args.folder) if args.folder else profile_dir()
    try:
        result = render_profile(folder, args.out)
    except (ProfileError, ResumeFormatError) as exc:
        print(f"FAIL {exc}")
        return 1
    for line in result_lines(result.report, result.profile_problems):
        print(line)
    print(f"pdf: {result.pdf}")
    print(f"review page: {result.review}")
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
