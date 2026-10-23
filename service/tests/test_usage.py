"""X-02: every model call emits exactly one structured usage record.

The model is mocked (fake clients returning canned responses with a ``usage``
block). Each path — stand-in, adjudicator, recap — must log one record with the
call kind, the model that answered, input/output tokens and latency, and never
the prompt text. A call that raises still emits a record (outcome ``error``).
"""

from __future__ import annotations

import json
import logging
import random
from types import SimpleNamespace
from typing import Any

import pytest

from boor_service.ai.actions import Disposition, Entity, GameState
from boor_service.ai.adjudicator import AdjudicationError, ProposalContext, adjudicate
from boor_service.ai.recap import RecapContext, RecapError, write_recap
from boor_service.ai.standin import StandInContext, StandInError, decide_action
from boor_service.ai.usage import ModelUsage, track_usage

USAGE_LOGGER = "boor_service.ai.usage"


class _Messages:
    def __init__(self, response: Any = None, exc: Exception | None = None) -> None:
        self.response = response
        self.exc = exc

    def create(self, **_kwargs: Any) -> Any:
        if self.exc is not None:
            raise self.exc
        return self.response


def _usage(inp: int, out: int) -> SimpleNamespace:
    return SimpleNamespace(input_tokens=inp, output_tokens=out)


def _records(caplog: pytest.LogCaptureFixture) -> list[ModelUsage]:
    out: list[ModelUsage] = []
    for r in caplog.records:
        rec = getattr(r, "model_usage", None)
        if r.name == USAGE_LOGGER and isinstance(rec, ModelUsage):
            out.append(rec)
    return out


# --- stand-in ----------------------------------------------------------------


def _standin_context() -> StandInContext:
    return StandInContext(
        character_name="Thora",
        character_sheet="Level 5 fighter.",
        persona="SECRET-PERSONA-TEXT",
        standing_instructions="Protect the healer.",
        red_lines=(),
        game_state=GameState(
            actor_id="hero",
            entities={
                "hero": Entity("hero", "Hero", Disposition.self),
                "goblin": Entity("goblin", "Goblin", Disposition.enemy),
            },
        ),
    )


def test_standin_call_emits_one_usage_record(caplog: pytest.LogCaptureFixture) -> None:
    tool = SimpleNamespace(
        type="tool_use",
        name="attack",
        input={
            "target_id": "goblin",
            "attack_bonus": 10,
            "target_ac": 5,
            "damage": "1d6+3",
            "narration": "Thora swings.",
        },
    )
    response = SimpleNamespace(
        content=[tool], stop_reason="tool_use", model="claude-opus-4-8", usage=_usage(1200, 85)
    )
    client = SimpleNamespace(messages=_Messages(response))
    caplog.set_level(logging.INFO, logger=USAGE_LOGGER)

    decide_action(client, _standin_context(), timeline_text="Combat.", rng=random.Random(1))

    [record] = _records(caplog)
    assert record.call == "standin"
    assert record.model == "claude-opus-4-8"
    assert record.input_tokens == 1200
    assert record.output_tokens == 85
    assert record.latency_ms >= 0
    assert record.outcome == "ok"
    assert "SECRET-PERSONA-TEXT" not in caplog.text


def test_standin_refusal_still_records_usage(caplog: pytest.LogCaptureFixture) -> None:
    response = SimpleNamespace(content=[], stop_reason="refusal", usage=_usage(900, 3))
    client = SimpleNamespace(messages=_Messages(response))
    caplog.set_level(logging.INFO, logger=USAGE_LOGGER)

    with pytest.raises(StandInError):
        decide_action(client, _standin_context(), timeline_text="Combat.")

    [record] = _records(caplog)
    assert record.call == "standin"
    assert (record.input_tokens, record.output_tokens) == (900, 3)


# --- adjudicator -------------------------------------------------------------


def _proposal() -> ProposalContext:
    return ProposalContext(
        scene_title="The stuck cart",
        scene_intro="Mud.",
        goal="Free the cart.",
        approaches=[{"id": "lift", "label": "Lift", "skill": "athletics", "hint": "str"}],
        character_name="Rowan",
        proposal="SECRET-PROPOSAL-TEXT",
    )


def test_adjudicator_call_emits_one_usage_record(caplog: pytest.LogCaptureFixture) -> None:
    text = SimpleNamespace(
        type="text", text=json.dumps({"decision": "run", "approach": "lift", "reason": "ok"})
    )
    response = SimpleNamespace(
        stop_reason="end_turn",
        content=[text],
        stop_details=None,
        model="claude-sonnet-5",
        usage=_usage(400, 40),
    )
    client = SimpleNamespace(beta=SimpleNamespace(messages=_Messages(response)))
    caplog.set_level(logging.INFO, logger=USAGE_LOGGER)

    adjudicate(client, _proposal())

    [record] = _records(caplog)
    assert record.call == "adjudicator"
    assert record.model == "claude-sonnet-5"
    assert (record.input_tokens, record.output_tokens) == (400, 40)
    assert record.outcome == "ok"
    assert "SECRET-PROPOSAL-TEXT" not in caplog.text


def test_api_error_emits_an_error_record(caplog: pytest.LogCaptureFixture) -> None:
    client = SimpleNamespace(beta=SimpleNamespace(messages=_Messages(exc=TimeoutError("slow"))))
    caplog.set_level(logging.INFO, logger=USAGE_LOGGER)

    with pytest.raises(TimeoutError):
        adjudicate(client, _proposal(), model="claude-x")

    [record] = _records(caplog)
    assert record.call == "adjudicator"
    assert record.model == "claude-x"  # requested model; nothing answered
    assert record.input_tokens is None and record.output_tokens is None
    assert record.outcome == "error"
    assert record.latency_ms >= 0


def test_adjudicator_bad_stop_still_records_usage(caplog: pytest.LogCaptureFixture) -> None:
    response = SimpleNamespace(
        stop_reason="max_tokens", content=[], stop_details=None, usage=_usage(10, 4000)
    )
    client = SimpleNamespace(beta=SimpleNamespace(messages=_Messages(response)))
    caplog.set_level(logging.INFO, logger=USAGE_LOGGER)

    with pytest.raises(AdjudicationError):
        adjudicate(client, _proposal())

    [record] = _records(caplog)
    assert record.output_tokens == 4000
    assert record.outcome == "ok"  # the call itself returned; validation failed later


# --- recap -------------------------------------------------------------------


def _recap_context() -> RecapContext:
    return RecapContext(
        character_name="Pip",
        persona="A cautious scout.",
        standing_instructions="Protect the party.",
        session_title="The river road",
        timeline="SECRET-TIMELINE-TEXT",
        own_actions=["Warn the party"],
    )


def test_recap_call_emits_one_usage_record(caplog: pytest.LogCaptureFixture) -> None:
    text = SimpleNamespace(type="text", text=json.dumps({"recap": "I kept watch."}))
    response = SimpleNamespace(
        stop_reason="end_turn",
        content=[text],
        stop_details=None,
        model="claude-opus-5",
        usage=_usage(2500, 300),
    )
    client = SimpleNamespace(beta=SimpleNamespace(messages=_Messages(response)))
    caplog.set_level(logging.INFO, logger=USAGE_LOGGER)

    write_recap(client, _recap_context())

    [record] = _records(caplog)
    assert record.call == "recap"
    assert record.model == "claude-opus-5"
    assert (record.input_tokens, record.output_tokens) == (2500, 300)
    assert "SECRET-TIMELINE-TEXT" not in caplog.text


def test_recap_without_usage_block_records_none(caplog: pytest.LogCaptureFixture) -> None:
    # Older fakes / unusual responses may omit ``usage``; the record still lands.
    text = SimpleNamespace(type="text", text=json.dumps({"recap": ""}))
    response = SimpleNamespace(stop_reason="end_turn", content=[text], stop_details=None)
    client = SimpleNamespace(beta=SimpleNamespace(messages=_Messages(response)))
    caplog.set_level(logging.INFO, logger=USAGE_LOGGER)

    with pytest.raises(RecapError):
        write_recap(client, _recap_context(), model="claude-req")

    [record] = _records(caplog)
    assert record.model == "claude-req"
    assert record.input_tokens is None and record.output_tokens is None


# --- the tracker itself ------------------------------------------------------


def test_log_line_is_structured(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger=USAGE_LOGGER)
    with track_usage("recap", "m") as t:
        t.response = SimpleNamespace(model="m2", usage=_usage(7, 8))
    [log] = [r for r in caplog.records if r.name == USAGE_LOGGER]
    msg = log.getMessage()
    for part in ("call=recap", "model=m2", "input_tokens=7", "output_tokens=8", "latency_ms="):
        assert part in msg
