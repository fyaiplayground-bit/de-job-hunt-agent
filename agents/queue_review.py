"""What a person reads for the approval queue (decision #40): one page per batch, and the submit
pack for the approved jobs. Everything from a posting or an LLM is escaped: it is data."""

import html
from datetime import date
from pathlib import Path
from typing import Any

from agents.application_queue import QueueRules, answer_questions, standard_answers

PAGE_FILE = "index.html"
STATUS_LABEL = {
    "awaiting_approval": "等你批准",
    "approved": "已批准",
    "passed": "跳过了",
    "applied": "已投",
}
SITE_LABEL = {
    "no_account": "不用账号",
    "account": "要账号（你注册和登录）",
    "aggregator": "聚合站（要找真实申请页）",
    "unknown": "没见过的网站（你看一下）",
}
DECISION_LABEL = {"apply_referral": "投 + 找内推", "apply": "投"}
STYLE = """
  body { margin: 0 auto; max-width: 1200px; padding: 16px; color: #222; background: #fff;
         font: 14px/1.55 system-ui, sans-serif; }
  h1 { font-size: 20px; margin: 0 0 8px; } h2 { font-size: 16px; margin-top: 24px; }
  table { border-collapse: collapse; width: 100%; }
  td, th { border: 1px solid #ccc; padding: 6px 8px; text-align: left; vertical-align: top; }
  th { background: #f4f4f4; }
  .sample { background: #fde8e8; border: 2px solid #a30000; color: #7a0000; padding: 10px 12px;
            margin-bottom: 12px; font-weight: 600; }
  .how { background: #f4f4f4; padding: 10px 12px; margin-bottom: 12px; }
  .bad { color: #a30000; } .note { color: #555; }
"""


def _link(path: str, text: str, base: Path) -> str:
    """A link that also works when the page is opened from disk."""
    return f'<a href="{html.escape(Path(path).as_uri())}">{html.escape(text)}</a>'


def _row_html(row: dict[str, Any], base: Path) -> str:
    snap = row["snapshot"]
    url = snap["url"]
    original = f' · <a href="{html.escape(url)}">原帖</a>' if url.startswith("http") else ""
    gaps = "、".join(snap["gaps"]) or "无"
    problems = ""
    if snap["problems"]:
        items = "".join(f"<li>{html.escape(p)}</li>" for p in snap["problems"])
        problems = f'<ul class="bad">{items}</ul>'
    reason = f'<br><span class="note">{html.escape(row["reason"])}</span>' if row["reason"] else ""
    return (
        f"<tr><td><b>{row['number']}</b></td>"
        f"<td>{STATUS_LABEL.get(row['status'], row['status'])}{reason}</td>"
        f"<td>{snap['score']}<br>{DECISION_LABEL.get(snap['decision'], snap['decision'])}</td>"
        f"<td><b>{html.escape(snap['company'])}</b><br>{html.escape(snap['title'])}<br>"
        f"{_link(snap['review_page'], '看简历对照', base)}{original}</td>"
        f"<td>{html.escape(snap['work_mode'])}<br>{html.escape(snap['location'])}</td>"
        f"<td>{SITE_LABEL[snap['site']]}</td>"
        f"<td>{html.escape(gaps)}</td>"
        f"<td>{html.escape(snap['seven_second'])}{problems}</td></tr>"
    )


def queue_page(
    rows: list[dict[str, Any]],
    skipped: list[tuple[Any, str]],
    batch_date: date,
    base: Path,
    pack: Path | None,
) -> str:
    banner = ""
    if any(row["sample"] for row in rows):
        banner = (
            '<div class="sample">这一批用的是虚构档案（Alex Sample）。'
            "简历是假的，绝不能投给真公司。"
            "代码已经锁住：这些职位不能标记为已投。</div>"
        )
    body = "".join(_row_html(row, base) for row in rows)
    left_out = ""
    if skipped:
        items = "".join(
            f"<tr><td>{job.fit['score']}</td><td>{html.escape(job.brief['company'])} — "
            f"{html.escape(job.brief['title'])}</td><td>{html.escape(why)}</td></tr>"
            for job, why in skipped
        )
        left_out = (
            "<h2>这次没排进来的（生成这批时的记录）</h2>"
            f"<table><tr><th>分数</th><th>职位</th><th>原因</th></tr>{items}</table>"
        )
    pack_line = ""
    if pack:
        pack_line = f"<p>提交包：{_link(str(pack), pack.name, base)}</p>"
    return f"""<!doctype html>
<html lang="zh"><head><meta charset="utf-8"><title>待投队列</title><style>{STYLE}</style></head>
<body>
<h1>待投队列 {batch_date}（{len(rows)} 个）</h1>
{banner}
<div class="how">看完跟 Claude 说就行，比如：<b>批准 1、3、5，跳过 2，原因是行业不合适</b>。
批准只代表简历可以用，还不会提交。真正提交前会再问你一次。</div>
<table><tr><th>号</th><th>状态</th><th>分数</th><th>职位</th><th>工作方式和地点</th><th>申请网站</th>
<th>缺的必备技能</th><th>审稿 AI 的 7 秒印象</th></tr>{body}</table>
{pack_line}
{left_out}
</body></html>
"""


def write_page(
    rows: list[dict[str, Any]],
    skipped: list[tuple[Any, str]],
    batch_date: date,
    out: Path,
    pack: Path | None,
) -> Path:
    folder = out / str(batch_date)
    folder.mkdir(parents=True, exist_ok=True)
    page = folder / PAGE_FILE
    if not skipped and page.is_file():
        previous = page.read_text(encoding="utf-8")
        marker = "<h2>这次没排进来的"
        kept = previous[previous.index(marker) :] if marker in previous else ""
        kept = kept.replace("</body></html>", "").strip()
        text = queue_page(rows, [], batch_date, folder, pack).replace(
            "</body></html>", f"{kept}\n</body></html>"
        )
    else:
        text = queue_page(rows, skipped, batch_date, folder, pack)
    page.write_text(text, encoding="utf-8")
    return page


def _lines(title: str, values: dict[str, Any]) -> list[str]:
    return [f"**{title}**", ""] + [f"- {key}: {value}" for key, value in values.items()] + [""]


def pack_markdown(
    approved: list[dict[str, Any]],
    batch_date: date,
    applicant: dict[str, Any],
    rules: QueueRules,
) -> str:
    """The approved jobs and the answers for their forms. Nothing here came from an LLM's guess:
    answers are read from the Applicant Profile, and any other question is left for FL."""
    lines = [f"# Submit pack {batch_date}", ""]
    if any(row["sample"] for row in approved):
        lines += [
            "**SAMPLE: built from a fictional profile. Never send any of this to a real company.**",
            "",
        ]
    lines += [
        "Fill each form up to its final review page, then stop and ask FL. Never submit without "
        "FL's yes for that batch. Never enter a password, create an account or solve a CAPTCHA: "
        "if a site asks, pause for FL.",
        "",
        "## Answers for every form",
        "",
    ]
    for section, values in standard_answers(applicant).items():
        lines += _lines(section, values)
    lines += ["## Jobs", ""]
    for row in approved:
        snap = row["snapshot"]
        answered, for_fl = answer_questions(snap["questions"], applicant, rules)
        lines += [
            f"### {row['number']}. {snap['company']} | {snap['title']}",
            "",
            f"- Apply: {snap['url']}",
            f"- Site: {snap['site']}",
            f"- Resume: {Path(snap['pdf']).name}",
            "",
        ]
        if answered:
            lines += ["Likely questions, answered from the profile:", ""]
            lines += [f"- {a['question']} -> {a['answer']}" for a in answered]
            lines += [""]
        if for_fl:
            lines += ["**Ask FL, don't guess:**", ""]
            lines += [f"- {question}" for question in for_fl]
            lines += [""]
    return "\n".join(lines) + "\n"
