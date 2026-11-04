---
name: ats-critic
description: How a tailored resume PDF is checked the way an ATS parser and a tired recruiter would. Not an LLM prompt: the measurable checks run as code (agents/resume_checks.py, agents/pdf_checks.py) and the judgment goes to resume-reviewer.
version: 2
---

# ATS + Recruiter Critic (Agent 5)

**This agent is no longer a separate LLM step** (decision #38). What can be measured runs as code, so the same resume always gets the same answer; what needs judgment went to `resume-reviewer`, which has fresh context. This file records which check lives where.

| Check | Where | Pass bar |
| --- | --- | --- |
| Parses cleanly | `agents/pdf_checks.py`: every line comes out of the text layer, in reading order, with no garbled characters | All lines present |
| One page, fonts embedded, ASCII dates | `agents/pdf_checks.py` | All true |
| Keyword coverage | `agents/resume_checks.py`: covered must-haves in the JD's wording | At least 80% |
| Evidence check | `agents/resume_checks.py`: every bullet cites evidence of its own role, every number is in the cited metrics, no skill without an entry | No exceptions |
| Layout habits | `agents/resume_checks.py`: headline names a role, numbers in at least half the bullets, no "Responsible for", short bullets | All true |
| 7-second test | `resume-reviewer` | Answer names the target role |
| Most relevant bullet first, framing, spelling, tense | `resume-reviewer` | Reviewer's verdict |

A resume that still fails after two review rounds is marked `needs_review` and goes to FL with the remaining problems.
