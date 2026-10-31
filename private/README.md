# private/

Everything in this folder except this README is gitignored. It never goes to GitHub.

The agents read the profile from the folder in `PROFILE_DIR` (`.env`). Until Milestone 5 that is the fictional sample in `data/sample/`; then it becomes `private` (decision #28). The three profile files here use **exactly** the sample's formats, so look at `data/sample/` for the layout.

## The profile (what the agents read)

| File | What it is |
| --- | --- |
| `evidence_bank.toml` | Work history, projects, education, one entry per thing done (skills, level, numbers, interview story), and the skill list with aliases and have / learning status. The only source of facts for the agents |
| `applicant_profile.toml` | Contact info, links, work authorization, sponsorship, notice period, salary floor and target, work modes and cities, EEO choices. Used for knockout questions and fit-scoring dealbreakers |
| `resume.md` | The current master resume as plain text with standard headings. Every skill and number on it must trace to the Evidence Bank |

Check them after every edit:

```
uv run python -m agents.profile check private
```

## Raw material and other inputs

| File | What it is |
| --- | --- |
| `resume_current.pdf` (or .docx) | FL's current resume as she has it; transcribed into `resume.md` and the Evidence Bank. Agents don't read it |
| `project_summaries/` | Resume-material summaries of GH Archive, Python Practice, Data Engineer career; distilled into Evidence Bank entries. Agents don't read them |
| `target_companies.md` | Small-company practice list + big-tech target list + exclusions (Milestone 5) |
| `output/` | Generated resumes, critic reports, outreach drafts, per job |

Before every commit, check `git status` shows nothing from this folder except this README.
