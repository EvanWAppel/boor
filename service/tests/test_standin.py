"""Tests for the AI stand-in slice.

The model is mocked in unit tests (a fake client returning canned tool calls),
so these are fast and deterministic and assert the two things that matter: the
tool call is dispatched to the *real* rules engine, and a red-lined action is
refused before the engine is ever touched. One env-gated test hits the live API.
"""

from __future__ import annotations

import os
import random
from dataclasses import dataclass
from typing import Any, cast

import pytest

from boor_service.ai.actions import Disposition, Entity, GameState
from boor_service.ai.guardrails import RedLine, RedLineKind
from boor_service.ai.standin import (
    ACTION_TOOLS,
    DEFAULT_MODEL,
    StandInContext,
    StandInError,
    act_on_turn,
    act_on_turn_for_character,
    decide_action,
    event_kind_for,
    event_payload,
    scoped_timeline_text,
)
from boor_service.db.models import EventAudience, EventKind
from boor_service.db.repository import (
    append_event,
    create_campaign_with_owner,
    create_character,
    create_session,
)
from boor_service.mechanics import CheckResult

HERO = "hero"
GOBLIN = "goblin"
ALLY = "cleric"


# --- Fakes for the injected Anthropic client --------------------------------


@dataclass
class _FakeToolUse:
    name: str
    input: dict[str, Any]
    type: str = "tool_use"
    id: str = "toolu_test"


@dataclass
class _FakeText:
    text: str = "..."
    type: str = "text"


@dataclass
class _FakeResponse:
    content: list[Any]
    stop_reason: str = "tool_use"


class _FakeMessages:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> _FakeResponse:
        self.calls.append(kwargs)
        return self._response


class _FakeClient:
    def __init__(self, response: _FakeResponse) -> None:
        self.messages = _FakeMessages(response)


def _client_calling(name: str, tool_input: dict[str, Any]) -> _FakeClient:
    return _FakeClient(_FakeResponse(content=[_FakeToolUse(name=name, input=tool_input)]))


def _scene(goblin_disposition: Disposition = Disposition.enemy) -> GameState:
    return GameState(
        actor_id=HERO,
        entities={
            HERO: Entity(HERO, "Hero", Disposition.self),
            GOBLIN: Entity(GOBLIN, "Goblin", goblin_disposition),
            ALLY: Entity(ALLY, "Cleric", Disposition.ally),
        },
    )


def _context(*red_lines: RedLine, game_state: GameState | None = None) -> StandInContext:
    return StandInContext(
        character_name="Thora",
        character_sheet="Level 5 fighter, STR 18, AC 18.",
        persona="Blunt, brave, protective of the party.",
        standing_instructions="Protect the healer. Don't flee a winnable fight.",
        red_lines=red_lines,
        game_state=game_state if game_state is not None else _scene(),
    )


# --- decide_action -----------------------------------------------------------


def test_attack_is_dispatched_to_the_real_engine() -> None:
    client = _client_calling(
        "attack",
        {
            "target_id": GOBLIN,
            "attack_bonus": 10,
            "target_ac": 5,  # bonus >> AC, so any roll hits
            "damage": "1d6+3",
            "narration": "Thora swings her greatsword.",
        },
    )
    decision = decide_action(
        client, _context(), timeline_text="Combat begins.", rng=random.Random(1)
    )
    assert decision.allowed is True
    assert decision.tool_name == "attack"
    result = decision.engine_result
    assert isinstance(result, dict)
    assert result["attack"].is_hit is True
    assert result["damage"] is not None and result["damage"].total > 0


def test_red_line_refuses_before_engine_is_touched() -> None:
    # Goblin is an ally here; a "never attack allies" red line must block the attack.
    client = _client_calling(
        "attack",
        {
            "target_id": ALLY,
            "attack_bonus": 10,
            "target_ac": 5,
            "damage": "1d6+3",
            "narration": "Thora turns on the cleric.",
        },
    )
    context = _context(RedLine(kind=RedLineKind.no_attacking_allies, note="never hurt the party"))
    decision = decide_action(client, context, timeline_text="...", rng=random.Random(1))
    assert decision.allowed is False
    assert decision.engine_result is None  # engine never rolled
    assert decision.refusal is not None
    assert decision.refusal.red_line.kind is RedLineKind.no_attacking_allies


def test_lethal_self_risk_red_line_blocks_attack() -> None:
    client = _client_calling(
        "attack",
        {
            "target_id": GOBLIN,
            "attack_bonus": 10,
            "target_ac": 5,
            "damage": "1d6",
            "self_risk": "lethal",
            "narration": "A reckless lunge into the fire.",
        },
    )
    context = _context(RedLine(kind=RedLineKind.no_lethal_self_risk, note="don't let me die"))
    decision = decide_action(client, context, timeline_text="...", rng=random.Random(1))
    assert decision.allowed is False
    assert decision.engine_result is None


def test_ability_check_dispatches_to_engine() -> None:
    client = _client_calling(
        "ability_check",
        {"skill": "Perception", "bonus": 5, "dc": 12, "narration": "Thora scans the room."},
    )
    decision = decide_action(client, _context(), timeline_text="...", rng=random.Random(2))
    assert decision.allowed is True
    assert isinstance(decision.engine_result, CheckResult)
    assert decision.engine_result.dc == 12


def test_speak_produces_in_character_action() -> None:
    client = _client_calling("speak", {"message": "Stay behind me!"})
    decision = decide_action(client, _context(), timeline_text="...")
    assert decision.allowed is True
    assert decision.tool_name == "speak"
    assert decision.summary == "Stay behind me!"
    assert decision.engine_result is None


def test_no_tool_call_raises() -> None:
    client = _FakeClient(_FakeResponse(content=[_FakeText()], stop_reason="end_turn"))
    with pytest.raises(StandInError, match="no tool call"):
        decide_action(client, _context(), timeline_text="...")


def test_model_refusal_raises() -> None:
    client = _FakeClient(_FakeResponse(content=[], stop_reason="refusal"))
    with pytest.raises(StandInError, match="refused"):
        decide_action(client, _context(), timeline_text="...")


def test_request_uses_configured_model_and_tools() -> None:
    client = _client_calling("speak", {"message": "hi"})
    decide_action(client, _context(), timeline_text="...")
    call = client.messages.calls[0]
    assert call["model"] == DEFAULT_MODEL
    assert call["tools"] is ACTION_TOOLS
    assert call["thinking"] == {"type": "adaptive"}
    assert call["tool_choice"] == {"type": "auto"}
    assert "temperature" not in call  # removed on this model family


# --- timeline mapping --------------------------------------------------------


def test_event_kind_and_payload_are_json_safe() -> None:
    client = _client_calling(
        "attack",
        {
            "target_id": GOBLIN,
            "attack_bonus": 10,
            "target_ac": 5,
            "damage": "1d6+3",
            "narration": "swings",
        },
    )
    decision = decide_action(client, _context(), timeline_text="...", rng=random.Random(1))
    assert event_kind_for(decision) is EventKind.action
    payload = event_payload(decision)
    assert payload["tool"] == "attack"
    assert payload["attack"]["hit"] is True
    # payload must be JSON-serializable (it lands in a JSONB column)
    import json

    json.dumps(payload)


# --- act_on_turn (end-to-end against real Postgres) --------------------------


async def test_act_on_turn_appends_ai_attributed_event(session, make_user) -> None:  # type: ignore[no-untyped-def]
    owner = await make_user()
    campaign = await create_campaign_with_owner(session, name="Camp", owner=owner)
    game_session = await create_session(session, campaign=campaign)

    client = _client_calling(
        "attack",
        {
            "target_id": GOBLIN,
            "attack_bonus": 10,
            "target_ac": 5,
            "damage": "1d6+3",
            "narration": "Thora charges the goblin.",
        },
    )
    decision, event = await act_on_turn(
        session,
        game_session=game_session,
        client=client,
        context=_context(),
        timeline_text="The goblin snarls.",
        rng=random.Random(1),
    )
    assert decision.allowed is True
    assert event.ai_generated is True  # AI-08 attribution
    assert event.actor_label == "Thora"
    assert event.kind is EventKind.action
    assert event.seq == 1
    assert event.audience is EventAudience.table  # the table sees what the stand-in does


async def test_standin_timeline_excludes_secrets_another_pc_knows(
    session,
    make_user,  # type: ignore[no-untyped-def]
) -> None:
    """Primer §4.2: the paladin's stand-in must not act on the rogue's private bribe."""
    owner = await make_user()
    campaign = await create_campaign_with_owner(session, name="Camp", owner=owner)
    game_session = await create_session(session, campaign=campaign)
    paladin = await create_character(session, campaign=campaign, name="Paladin")
    rogue = await create_character(session, campaign=campaign, name="Rogue")

    await append_event(
        session,
        game_session=game_session,
        kind=EventKind.narration,
        body="The duke greets the party.",
    )
    await append_event(
        session,
        game_session=game_session,
        kind=EventKind.in_character,
        actor_label="Rogue",
        body="I'll take the gold. Tell no one.",
        audience=EventAudience.characters,
        visible_to=[rogue.id],
    )

    paladin_text = await scoped_timeline_text(session, game_session=game_session, character=paladin)
    rogue_text = await scoped_timeline_text(session, game_session=game_session, character=rogue)
    assert "I'll take the gold" not in paladin_text
    assert "The duke greets the party." in paladin_text
    assert "I'll take the gold" in rogue_text

    client = _client_calling("speak", {"message": "Well met, my lord."})
    _decision, event = await act_on_turn_for_character(
        session,
        game_session=game_session,
        character=paladin,
        client=client,
        context=_context(),
        rng=random.Random(1),
    )
    # the prompt the model saw is the paladin-scoped one (no bribe)
    user_message = client.messages.calls[0]["messages"][0]["content"]
    assert "I'll take the gold" not in user_message
    assert "The duke greets the party." in user_message
    # the action itself is table-public
    assert event.audience is EventAudience.table
    assert event.ai_generated is True


# --- live model (opt-in) -----------------------------------------------------


@pytest.mark.skipif(
    not os.getenv("BOOR_LIVE_AI"),
    reason="set BOOR_LIVE_AI=1 (and ANTHROPIC_API_KEY) to run the live model test",
)
def test_live_standin_chooses_an_action() -> None:
    import anthropic

    client = anthropic.Anthropic()
    context = _context(RedLine(kind=RedLineKind.no_attacking_allies, note="never hurt the party"))
    decision = decide_action(
        cast("Any", client),
        context,
        timeline_text="A goblin (id: goblin) blocks the corridor and raises its scimitar.",
        rng=random.Random(0),
    )
    assert decision.tool_name in {"attack", "ability_check", "speak", "move"}
