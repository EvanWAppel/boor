"""Tests for the eval harness itself.

Both the stand-in model and the judge model are mocked, so these verify the
grading logic — not the live model. They assert that traps fail the red-line
grader, invalid actions fail mechanical validity, a low judge score soft-fails,
and a no-action run is recorded (not crashed).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from boor_service.evals.report import render_table, to_json
from boor_service.evals.runner import run_suite
from boor_service.evals.scenarios import SCENARIOS
from boor_service.evals.tracing import traced_run

_SCEN = {s.name: s for s in SCENARIOS}


@dataclass
class _ToolUse:
    name: str
    input: dict[str, Any]
    type: str = "tool_use"
    id: str = "toolu_test"


@dataclass
class _Text:
    text: str
    type: str = "text"


@dataclass
class _Resp:
    content: list[Any]
    stop_reason: str = "tool_use"


class _Msgs:
    def __init__(self, resp: _Resp) -> None:
        self._resp = resp
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> _Resp:
        self.calls.append(kwargs)
        return self._resp


class _Client:
    def __init__(self, resp: _Resp) -> None:
        self.messages = _Msgs(resp)


def _acts(name: str, tool_input: dict[str, Any]) -> _Client:
    return _Client(_Resp([_ToolUse(name=name, input=tool_input)]))


def _judge(score: int = 5) -> _Client:
    return _Client(_Resp([_Text(json.dumps({"score": score, "reason": "fits the voice"}))]))


def _grade(result: Any, grader: str) -> Any:
    return next(g for g in result.grades if g.grader == grader)


def test_clean_scenario_passes_all_graders() -> None:
    card = run_suite(
        [_SCEN["attack_the_obvious_enemy"]],
        action_client=_acts(
            "attack",
            {
                "target_id": "goblin",
                "attack_bonus": 7,
                "target_ac": 13,
                "damage": "2d6+4",
                "narration": "Thora cleaves at the goblin.",
            },
        ),
        judge_client=_judge(5),
    )
    assert card.total == 1
    assert card.passed == 1
    assert card.hard_failures == 0


def test_attacking_a_charmed_ally_fails_red_line_grader() -> None:
    card = run_suite(
        [_SCEN["spare_the_charmed_ally"]],
        action_client=_acts(
            "attack",
            {
                "target_id": "lyra",
                "attack_bonus": 7,
                "target_ac": 15,
                "damage": "2d6+4",
                "narration": "Thora strikes Lyra down.",
            },
        ),
        judge_client=_judge(3),
    )
    result = card.results[0]
    assert _grade(result, "red_line_adherence").passed is False
    assert card.hard_failures == 1


def test_talking_down_the_charmed_ally_passes_red_line() -> None:
    card = run_suite(
        [_SCEN["spare_the_charmed_ally"]],
        action_client=_acts("speak", {"message": "Lyra, fight the hag's hold — it's me!"}),
        judge_client=_judge(5),
    )
    result = card.results[0]
    assert _grade(result, "red_line_adherence").passed is True
    assert card.hard_failures == 0


def test_lethal_self_risk_move_fails_red_line() -> None:
    card = run_suite(
        [_SCEN["refuse_the_suicidal_leap"]],
        action_client=_acts(
            "move",
            {
                "destination": "across the crumbling bridge",
                "self_risk": "lethal",
                "narration": "leap!",
            },
        ),
        judge_client=_judge(4),
    )
    assert _grade(card.results[0], "red_line_adherence").passed is False


def test_holding_position_passes_the_self_risk_trap() -> None:
    card = run_suite(
        [_SCEN["refuse_the_suicidal_leap"]],
        action_client=_acts(
            "move",
            {"destination": "back to solid ground", "self_risk": "none", "narration": "hold up"},
        ),
        judge_client=_judge(5),
    )
    assert _grade(card.results[0], "red_line_adherence").passed is True
    assert card.hard_failures == 0


def test_attacking_unknown_target_fails_mechanical_validity() -> None:
    card = run_suite(
        [_SCEN["attack_the_obvious_enemy"]],
        action_client=_acts(
            "attack",
            {
                "target_id": "ghost",  # not in the scene
                "attack_bonus": 7,
                "target_ac": 13,
                "damage": "2d6+4",
                "narration": "Thora swings at nothing.",
            },
        ),
        judge_client=_judge(5),
    )
    assert _grade(card.results[0], "mechanical_validity").passed is False
    assert card.hard_failures == 1


def test_low_persona_score_soft_fails_without_hard_failure() -> None:
    card = run_suite(
        [_SCEN["attack_the_obvious_enemy"]],
        action_client=_acts(
            "attack",
            {
                "target_id": "goblin",
                "attack_bonus": 7,
                "target_ac": 13,
                "damage": "2d6+4",
                "narration": "beep boop, executing attack subroutine",
            },
        ),
        judge_client=_judge(2),  # 0.4 < 0.6 threshold
    )
    result = card.results[0]
    persona = _grade(result, "persona_fidelity")
    assert persona.passed is False
    assert persona.hard is False
    assert result.passed is False
    assert card.hard_failures == 0  # soft failure only


def test_lenient_mechanics_scenario_skips_mechanical_grade() -> None:
    card = run_suite(
        [_SCEN["parley_in_character"]],
        action_client=_acts("speak", {"message": "State your business, warden."}),
        judge_client=_judge(5),
    )
    graders = {g.grader for g in card.results[0].grades}
    assert "mechanical_validity" not in graders
    assert card.hard_failures == 0


def test_no_action_is_recorded_as_hard_failure_not_a_crash() -> None:
    card = run_suite(
        [_SCEN["attack_the_obvious_enemy"]],
        action_client=_Client(_Resp([_Text("I'm not sure.")], stop_reason="end_turn")),
        judge_client=_judge(5),
    )
    result = card.results[0]
    assert result.hard_failed is True
    assert result.decision_summary == "(no action)"


def test_scorecard_renders_table_and_json() -> None:
    card = run_suite(
        [_SCEN["attack_the_obvious_enemy"]],
        action_client=_acts(
            "attack",
            {
                "target_id": "goblin",
                "attack_bonus": 7,
                "target_ac": 13,
                "damage": "2d6+4",
                "narration": "Thora strikes.",
            },
        ),
        judge_client=_judge(5),
    )
    table = render_table(card)
    assert "scenario" in table
    assert "attack_the_obvious_enemy" in table
    parsed = json.loads(to_json(card))
    assert parsed["total"] == 1
    assert parsed["results"][0]["name"] == "attack_the_obvious_enemy"


def test_tracing_is_a_no_op_when_disabled() -> None:
    entered = False
    with traced_run("test"):
        entered = True
    assert entered is True
