"""Tests for the runnable stand-in demo.

The demo runs the *real* stand-in pipeline (decide_action -> guardrail -> engine)
over a scripted encounter, entirely in memory, with a canned client so no API key
or Postgres is needed. These tests assert the pipeline runs end to end and that
the refusal beat is genuinely blocked before the engine is touched.
"""

from __future__ import annotations

import io

from boor_service.demo import ENCOUNTER, ScriptedClient, run_demo


def test_scripted_demo_runs_every_beat() -> None:
    out = io.StringIO()
    decisions = run_demo(ScriptedClient(ENCOUNTER), out=out)

    assert len(decisions) == len(ENCOUNTER)
    text = out.getvalue()
    for beat in ENCOUNTER:
        assert beat.title in text


def test_demo_shows_an_engine_action_and_a_guardrail_refusal() -> None:
    out = io.StringIO()
    decisions = run_demo(ScriptedClient(ENCOUNTER), out=out)

    assert any(d.allowed for d in decisions), "expected at least one allowed action"
    assert any(
        not d.allowed and d.refusal is not None for d in decisions
    ), "expected at least one guardrail refusal"

    text = out.getvalue().lower()
    assert "refused" in text
    assert "ai_generated=true" in text  # attribution is surfaced


def test_refused_beats_never_touch_the_engine() -> None:
    decisions = run_demo(ScriptedClient(ENCOUNTER), out=io.StringIO())

    refused = [d for d in decisions if not d.allowed]
    assert refused, "the encounter should include a refusal beat"
    for decision in refused:
        assert decision.engine_result is None


def test_scripted_client_dispatches_canned_calls_in_order() -> None:
    decisions = run_demo(ScriptedClient(ENCOUNTER), out=io.StringIO())
    assert [d.tool_name for d in decisions] == [b.scripted_call[0] for b in ENCOUNTER]
