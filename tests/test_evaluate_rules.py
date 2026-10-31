"""The evaluation step of the rules loop: proposals that let an attack through must fail."""

import pytest

from pipeline.alarm_triage import RULE_SIGNATURES, RULES_FILE
from pipeline.evaluate_rules import evaluate

CURRENT = RULES_FILE.read_text(encoding="utf-8")


def write_rules(tmp_path, text: str):
    path = tmp_path / "proposed.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_the_current_rules_pass_against_themselves():
    ev = evaluate(RULES_FILE)

    assert ev.passed, ev.hard_failures
    assert ev.fp_benign[0] == ev.fp_benign[1]


def test_a_comment_only_change_passes_and_changes_nothing(tmp_path):
    proposed = write_rules(tmp_path, CURRENT + "\n# clarified wording, no rule change\n")

    ev = evaluate(proposed)

    assert ev.passed and ev.fp_benign[0] == ev.fp_benign[1]


def test_making_every_rule_weak_is_rejected(tmp_path):
    # The "let it all through" proposal: every instruction rule weak, no steering words.
    names = ", ".join(f'"{name}"' for name in RULE_SIGNATURES)
    proposed = write_rules(tmp_path, f"version = 2\nweak_rules = [{names}]\nsteering_terms = []\n")

    ev = evaluate(proposed)

    assert not ev.passed
    assert any("ATTACK would be benign" in failure for failure in ev.hard_failures)


def weaken(tmp_path, rule: str):
    return write_rules(
        tmp_path,
        CURRENT.replace("version = 1", "version = 2").replace(
            "weak_rules = [", f'weak_rules = [\n    "{rule}",', 1
        ),
    )


def test_weakening_one_strong_rule_is_caught(tmp_path):
    # "<|im_start|>system" has no steering word, so only its strong rule stands in the way.
    ev = evaluate(weaken(tmp_path, "chat_template_token"))

    assert not ev.passed
    assert any("ATTACK would be benign" in f and "im_start" in f for f in ev.hard_failures)


def test_steering_words_still_catch_an_attack_whose_rule_was_weakened(tmp_path):
    # Two layers: weakening "disregard_previous" alone lets nothing through, because the attack
    # lines it covers ("Forget your previous instructions.") also contain steering words.
    ev = evaluate(weaken(tmp_path, "disregard_previous"))

    assert ev.passed, ev.hard_failures


@pytest.mark.db
def test_postings_that_would_change_tier_are_listed(db, greenhouse_jobs, tmp_path):
    from tests.test_labels import SSH_LINE, load_and_gate

    greenhouse_jobs.append(dict(greenhouse_jobs[0], id=2001, content=SSH_LINE, title="SRE"))
    ids = load_and_gate(db, greenhouse_jobs)
    strict = write_rules(tmp_path, "version = 2\nweak_rules = []\nsteering_terms = []\n")

    ev = evaluate(strict, conn=db)

    assert [(c[0], c[3], c[4]) for c in ev.changed] == [(ids["2001"], "benign", "review")]
    assert ev.tier_counts["current"]["benign"] == 1
    assert ev.tier_counts["proposed"]["review"] == 1
