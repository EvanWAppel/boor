"""Runs scenarios through the stand-in and grades them into a scorecard.

A scenario that produces no action (model refused / no tool call) is recorded as a
hard failure rather than aborting the suite — an eval run should score every case.
Unexpected errors still propagate.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from boor_service.ai.standin import (
    DEFAULT_MODEL,
    StandInError,
    SupportsMessages,
    decide_action,
)
from boor_service.evals.graders import (
    GradeResult,
    mechanical_validity,
    persona_fidelity,
    red_line_adherence,
)
from boor_service.evals.scenarios import EvalScenario


@dataclass(frozen=True)
class ScenarioResult:
    """The graded outcome of one scenario."""

    name: str
    protects: str
    decision_summary: str
    grades: list[GradeResult]

    @property
    def passed(self) -> bool:
        """Pass = every hard grade passes and every soft grade meets its threshold."""
        return all(g.passed for g in self.grades)

    @property
    def hard_failed(self) -> bool:
        return any(g.hard and not g.passed for g in self.grades)


@dataclass(frozen=True)
class Scorecard:
    """Aggregate results across a suite run."""

    results: list[ScenarioResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def hard_failures(self) -> int:
        return sum(1 for r in self.results if r.hard_failed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "passed": self.passed,
            "hard_failures": self.hard_failures,
            "results": [
                {
                    "name": r.name,
                    "protects": r.protects,
                    "decision": r.decision_summary,
                    "passed": r.passed,
                    "grades": [
                        {
                            "grader": g.grader,
                            "passed": g.passed,
                            "hard": g.hard,
                            "score": g.score,
                            "detail": g.detail,
                        }
                        for g in r.grades
                    ],
                }
                for r in self.results
            ],
        }


def run_scenario(
    scenario: EvalScenario,
    *,
    action_client: SupportsMessages,
    judge_client: SupportsMessages,
    model: str = DEFAULT_MODEL,
) -> ScenarioResult:
    """Run one scenario through the stand-in and grade it."""
    try:
        decision = decide_action(
            action_client,
            scenario.context,
            timeline_text=scenario.timeline_text,
            rng=random.Random(scenario.rng_seed),
            model=model,
        )
    except StandInError as exc:
        grade = GradeResult("produced_action", False, True, f"no action produced: {exc}")
        return ScenarioResult(scenario.name, scenario.protects, "(no action)", [grade])

    grades = [
        mechanical_validity(scenario, decision),
        red_line_adherence(scenario, decision),
        persona_fidelity(scenario, decision, judge_client=judge_client, model=model),
    ]
    if scenario.lenient_mechanics:
        grades = [g for g in grades if g.grader != "mechanical_validity"]
    return ScenarioResult(scenario.name, scenario.protects, decision.summary, grades)


def run_suite(
    scenarios: Sequence[EvalScenario],
    *,
    action_client: SupportsMessages,
    judge_client: SupportsMessages,
    model: str = DEFAULT_MODEL,
) -> Scorecard:
    """Run every scenario and collect a scorecard."""
    return Scorecard(
        results=[
            run_scenario(
                s, action_client=action_client, judge_client=judge_client, model=model
            )
            for s in scenarios
        ]
    )
