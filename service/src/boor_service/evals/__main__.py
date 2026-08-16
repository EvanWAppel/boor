"""CLI: run the stand-in eval suite against the live model and print a scorecard.

    uv run python -m boor_service.evals

Requires ANTHROPIC_API_KEY. Exit code is non-zero if any hard grade fails, so the
suite can gate CI. Set BOOR_LANGSMITH=1 (with langsmith installed) to trace.
"""

from __future__ import annotations

import os
import sys
from typing import Any, cast

from boor_service.evals.report import render_table, to_json
from boor_service.evals.runner import run_suite
from boor_service.evals.scenarios import SCENARIOS
from boor_service.evals.tracing import traced_run

_SCORECARD_PATH = "evals-scorecard.json"


def main() -> int:
    if not os.getenv("ANTHROPIC_API_KEY"):
        print(
            "ANTHROPIC_API_KEY is not set — cannot run the live eval suite.",
            file=sys.stderr,
        )
        return 2

    import anthropic

    client = cast("Any", anthropic.Anthropic())
    with traced_run("boor-standin-evals"):
        scorecard = run_suite(SCENARIOS, action_client=client, judge_client=client)

    print(render_table(scorecard))
    with open(_SCORECARD_PATH, "w") as handle:
        handle.write(to_json(scorecard))
    print(f"\nwrote {_SCORECARD_PATH}")
    return 1 if scorecard.hard_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
