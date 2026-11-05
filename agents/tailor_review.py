"""The files a person reads for each tailored resume (decision #38): changes.md, not_covered.md
and review.html (the posting, the page, and what was changed and checked, side by side), plus an
index of the run. Everything from the posting or an LLM is escaped: it is data."""

import base64
import html
from pathlib import Path

from agents.render_resume import render_preview
from agents.resume_doc import parse_resume
from agents.tailor import Tailored

STATUS_LABEL = {"ready": "可以看了", "needs_review": "有问题，要你看"}
VERDICT_LABEL = {"pass": "通过", "revise": "要修改"}
EDIT_LABEL = {
    "add_bullet": "加一条经历",
    "add_skill": "加技能",
    "remove_bullet": "删掉这条",
    "move_first": "调到最前面",
}
REVIEW_FILE = "review.html"
INDEX_FILE = "index.html"
STYLE = """
  body { margin: 0; font: 14px/1.5 system-ui, sans-serif; color: #222; background: #fff; }
  header { padding: 8px 16px; border-bottom: 1px solid #ccc; }
  h1 { font-size: 16px; margin: 0; } h2 { font-size: 14px; margin: 12px 0 4px; }
  main { display: flex; height: calc(100vh - 80px); min-height: 500px; }
  main > * { flex: 1; min-width: 0; overflow: auto; padding: 8px 12px;
             border-right: 1px solid #ccc; }
  main > :last-child { border-right: 0; }
  pre { white-space: pre-wrap; margin: 0; font: 13px/1.5 system-ui, sans-serif; }
  img { display: block; width: 100%; background: #fff; border: 1px solid #ddd; }
  .page { background: #eee; }
  ul { margin: 0; padding-left: 18px; } li { margin-bottom: 4px; }
  .bad { color: #a30000; } .note { color: #555; }
  table { border-collapse: collapse; width: 100%; max-width: 1100px; }
  td, th { border: 1px solid #ccc; padding: 4px 8px; text-align: left; }
"""


def _items(lines: list[str], css: str = "") -> str:
    if not lines:
        return '<p class="note">无</p>'
    style = f' class="{css}"' if css else ""
    return f"<ul{style}>" + "".join(f"<li>{html.escape(line)}</li>" for line in lines) + "</ul>"


def _edit_line(edit: dict) -> str:
    kind = edit["kind"]
    if kind == "replace":
        body = f"改写：原来“{edit['old']}”，改成“{edit['new']}”"
    elif kind in EDIT_LABEL:
        body = f"{EDIT_LABEL[kind]}：{edit['new'] or edit['old']}"
    else:
        body = f"{kind}：{edit['new'] or edit['old']}"
    return f"{body}（原因：{edit['reason']}）"


def changes_md(tailored: Tailored) -> str:
    lines = [f"# Changes: {tailored.job.brief['company']} | {tailored.job.brief['title']}", ""]
    lines += ["## Draft", ""]
    lines += [f"- {c['edit']} (serves: {c['serves']})" for c in tailored.changes]
    for entry in tailored.history:
        if "round" in entry:
            lines += ["", f"## Review round {entry['round']}: {entry['verdict']}", ""]
            lines += [f"- {_edit_line(edit)}" for edit in entry["applied"]]
            lines += [
                f"- REFUSED {_edit_line(edit)}: {edit['refused_because']}"
                for edit in entry["rejected"]
            ]
        else:
            lines += ["", "## Cut to fit one page", ""]
            lines += [f"- {text}" for text in entry["trimmed_to_fit_one_page"]]
    return "\n".join(lines) + "\n"


def not_covered_md(tailored: Tailored) -> str:
    fit = tailored.job.fit
    lines = [f"# Not covered: {tailored.job.brief['company']} | {tailored.job.brief['title']}", ""]
    lines += ["No Evidence Bank entry, so these stay off the resume.", "", "## Must-haves", ""]
    lines += [f"- {name}" for name in fit["not_covered"]] or ["- none"]
    lines += ["", "## Nice-to-haves", ""]
    lines += [f"- {name}" for name in fit["nice_missing"]] or ["- none"]
    return "\n".join(lines) + "\n"


def review_page(tailored: Tailored) -> str:
    job, fit = tailored.job, tailored.job.fit
    brief = job.brief
    images = "".join(
        f'<img alt="page {number}" src="data:image/png;base64,{base64.b64encode(png).decode()}">'
        for number, png in enumerate(render_preview(parse_resume(tailored.resume)), start=1)
    )
    rounds = ""
    for entry in tailored.history:
        if "round" not in entry:
            rounds += "<h2>为了放进一页删掉的</h2>" + _items(entry["trimmed_to_fit_one_page"])
            continue
        rounds += (
            f"<h2>审稿第 {entry['round']} 轮："
            f"{VERDICT_LABEL.get(entry['verdict'], entry['verdict'])}</h2>"
            f"<p>7 秒印象：{html.escape(entry['seven_second_answer'])}</p>"
            + _items([_edit_line(edit) for edit in entry["applied"]])
        )
        if entry["rejected"]:
            refused = [f"{_edit_line(e)}：{e['refused_because']}" for e in entry["rejected"]]
            rounds += "<p>审稿 AI 提了、但被代码拒绝的修改：</p>" + _items(refused, "note")
        if entry["notes"]:
            rounds += "<p>审稿备注：</p>" + _items(entry["notes"], "note")
    link = ""
    if brief.get("url", "").startswith("http"):
        link = f' · <a href="{html.escape(brief["url"])}">原帖</a>'
    covered = [f"{m['asked']} ← {m['skill']}（{m['level']}）" for m in fit["covered"]]
    return f"""<!doctype html>
<html lang="zh"><head><meta charset="utf-8"><title>简历对照</title><style>{STYLE}</style></head>
<body>
<header><h1>#{job.posting_version_id} {html.escape(brief["company"])} —
{html.escape(brief["title"])}
{link} · {STATUS_LABEL[tailored.status]}</h1>
<a href="{html.escape(tailored.pdf.name)}">打开 PDF</a> · 分数 {fit["score"]} · 这份简历的 AI 费用
${tailored.cost_usd:.3f} · 文字排到页面 {tailored.report.fill:.0%}</header>
<main>
  <section><h2>职位原文</h2><pre>{html.escape(job.text)}</pre></section>
  <section class="page">{images}</section>
  <section>
    <h2>检查还没过的</h2>{_items(tailored.all_problems, "bad")}
    <h2>警告</h2>{_items(list(tailored.report.warnings))}
    <h2>JD 要求但没有证据（不写）</h2>{_items(fit["not_covered"])}
    <h2>对上的必备技能</h2>{_items(covered)}
    <h2>起草 AI 的说明（不会上简历）</h2>
    {_items([f"{c['edit']}（对应 JD：{c['serves']}）" for c in tailored.changes])}
    {rounds}
  </section>
</main></body></html>
"""


def write_job_files(tailored: Tailored, out: Path) -> Path:
    folder = tailored.pdf.parent
    (folder / "resume.md").write_text(tailored.resume, encoding="utf-8")
    (folder / "changes.md").write_text(changes_md(tailored), encoding="utf-8")
    (folder / "not_covered.md").write_text(not_covered_md(tailored), encoding="utf-8")
    page = folder / REVIEW_FILE
    page.write_text(review_page(tailored), encoding="utf-8")
    return page


def write_index(results: list[Tailored], out: Path) -> Path:
    rows = "".join(
        f"<tr><td>{STATUS_LABEL[t.status]}</td><td>{t.job.fit['score']}</td>"
        f'<td><a href="{html.escape(t.pdf.parent.name)}/{REVIEW_FILE}">'
        f"{html.escape(t.job.brief['company'])} — {html.escape(t.job.brief['title'])}</a></td>"
        f"<td>{len(t.all_problems)}</td><td>${t.cost_usd:.3f}</td></tr>"
        for t in results
    )
    index = out / INDEX_FILE
    out.mkdir(parents=True, exist_ok=True)
    index.write_text(
        f"""<!doctype html>
<html lang="zh"><head><meta charset="utf-8"><title>改写结果</title><style>{STYLE}
  body {{ padding: 16px; }}</style></head><body>
<h1>这次改写的简历（{len(results)} 份）</h1><p>点职位名，打开对照页。</p>
<table><tr><th>状态</th><th>分数</th><th>职位</th><th>问题数</th><th>AI 费用</th></tr>{rows}</table>
</body></html>
""",
        encoding="utf-8",
    )
    return index
