"""Evaluation harness for the AI stand-in (RECRUITER-PRIMER.md #2).

Scripted game states + graders that score the stand-in on three axes:

1. **Mechanical validity** — did it choose a legal action for the scene?
2. **Red-line adherence** — faced with a tempting forbidden target, does it avoid
   it on its own (with the guardrail as the safety net)?
3. **Persona fidelity** — LLM-as-judge: does the action read like the character?

Deterministic graders (1, 2) assert hard; the judge grader (3) is scored against
a threshold. Run the suite against the live model with ``python -m
boor_service.evals``; the harness itself is unit-tested with mocked models.
"""

from __future__ import annotations

from boor_service.evals.graders import GradeResult
from boor_service.evals.runner import ScenarioResult, Scorecard, run_suite
from boor_service.evals.scenarios import SCENARIOS, EvalScenario, RedLineTrap

__all__ = [
    "SCENARIOS",
    "EvalScenario",
    "GradeResult",
    "RedLineTrap",
    "ScenarioResult",
    "Scorecard",
    "run_suite",
]
