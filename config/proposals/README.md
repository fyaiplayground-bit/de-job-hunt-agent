# Rule proposals

A proposed change to `config/triage_rules.toml` is written here first, as a full copy of the rules file with the change and a higher `version`. The real rules file is not touched until FL approves (decision #22, #23).

1. Write the proposal, e.g. `config/proposals/triage_rules.v2.toml`, with a comment at the top saying what changes and which labels motivated it.
2. Evaluate it: `uv run python -m pipeline.evaluate_rules config/proposals/triage_rules.v2.toml`. Hard checks must PASS (every hand-written golden case in its tier, no attack benign or clean, no labeled false positive blocked).
3. FL reads the report and approves.
4. Copy the proposal over `config/triage_rules.toml`, recompute with `uv run python -m pipeline.ingest --gate-only`, and record the change in `docs/DECISIONS.md`. Keep the proposal file in this folder as history.
