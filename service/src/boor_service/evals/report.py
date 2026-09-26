"""Render a scorecard as a printed table and JSON."""

from __future__ import annotations

import json

from boor_service.evals.runner import ScenarioResult, Scorecard

_GRADERS = ("mechanical_validity", "red_line_adherence", "persona_fidelity")


def _cell(result: ScenarioResult, grader: str) -> str:
    grade = next((g for g in result.grades if g.grader == grader), None)
    if grade is None:
        return "  -  "
    mark = "PASS" if grade.passed else "FAIL"
    if grade.score is not None:
        return f"{mark} {grade.score:.2f}"
    return mark


def render_table(scorecard: Scorecard) -> str:
    """A human-readable scorecard table."""
    name_w = max((len(r.name) for r in scorecard.results), default=8)
    name_w = max(name_w, len("scenario"))
    header = (
        f"{'scenario':<{name_w}}  {'mechanical':<10}  {'red-line':<10}  "
        f"{'persona':<10}  overall"
    )
    lines = [header, "-" * len(header)]
    for r in scorecard.results:
        overall = "PASS" if r.passed else "FAIL"
        lines.append(
            f"{r.name:<{name_w}}  {_cell(r, _GRADERS[0]):<10}  "
            f"{_cell(r, _GRADERS[1]):<10}  {_cell(r, _GRADERS[2]):<10}  {overall}"
        )
    lines.append("-" * len(header))
    lines.append(
        f"{scorecard.passed}/{scorecard.total} scenarios passed; "
        f"{scorecard.hard_failures} hard failure(s)"
    )
    return "\n".join(lines)


def to_json(scorecard: Scorecard, *, indent: int = 2) -> str:
    return json.dumps(scorecard.to_dict(), indent=indent)
