"""AI guide for v5 "try something else" proposals (host can always override).

After a proposal is saved, :func:`run` asks the model (outside any DB transaction),
then re-locks the session and applies the decision only if that same proposal is
still open, still marked ``thinking``, and play is not paused. If the host already
answered, the late decision is dropped. On any model failure, or a pause, the
proposal is marked ``unavailable`` and stays open for the host — never silently
resolved. Enabled by ``ENABLE_AI_ADJUDICATION=1`` plus ``ANTHROPIC_API_KEY``.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from typing import Any, cast

import anthropic
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from boor_service import guided, guided_scenes
from boor_service.ai.adjudicator import (
    DEFAULT_MODEL,
    Adjudication,
    AdjudicationError,
    ProposalContext,
    SupportsBetaMessages,
    adjudicate,
)
from boor_service.db.models import GameSession, SessionStatus

logger = logging.getLogger(__name__)

LABEL = "AI guide"


def get_client() -> SupportsBetaMessages | None:
    """The model client, or ``None`` when AI adjudication is not enabled."""
    if os.environ.get("ENABLE_AI_ADJUDICATION") != "1" or not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    return cast(SupportsBetaMessages, anthropic.Anthropic(timeout=20, max_retries=0))


def context_for(state: dict[str, Any]) -> ProposalContext:
    proposal = state["proposal"]
    return ProposalContext(
        scene_title=state["scene_title"],
        scene_intro=state["scene_intro"],
        goal=state["goal"],
        approaches=state["actions"],
        character_name=proposal["name"],
        proposal=proposal["text"],
    )


async def decide(client: SupportsBetaMessages, ctx: ProposalContext) -> Adjudication:
    model = os.environ.get("ADJUDICATOR_MODEL", DEFAULT_MODEL)
    return await asyncio.wait_for(
        asyncio.to_thread(adjudicate, client, ctx, model=model), timeout=25
    )


async def run(
    sessions: async_sessionmaker,
    session_id: uuid.UUID,
    client: SupportsBetaMessages,
    snapshot: dict[str, Any],
) -> None:
    """Background task: adjudicate the proposal in ``snapshot`` and record the outcome."""
    decision: Adjudication | None
    try:
        decision = await decide(client, context_for(snapshot))
    except (
        TimeoutError,
        anthropic.APIError,
        AdjudicationError,
        ValueError,
        KeyError,
        TypeError,
    ) as exc:
        logger.warning("AI adjudication failed for session %s: %r", session_id, exc)
        decision = None
    async with sessions() as db:
        await apply_decision(db, session_id, snapshot["proposal"], decision)


async def apply_decision(
    db: AsyncSession,
    session_id: uuid.UUID,
    proposal: dict[str, Any],
    decision: Adjudication | None,
) -> None:
    game = await db.scalar(
        select(GameSession).where(GameSession.id == session_id).with_for_update()
    )
    if game is None or game.status != SessionStatus.active:
        return
    await db.refresh(game)
    state = await guided.latest_state(db, session_id)
    current = state.get("proposal") if state else None
    if (
        state is None
        or not current
        or current.get("ai") != "thinking"
        or (current["user_id"], current["text"]) != (proposal["user_id"], proposal["text"])
    ):
        logger.info("AI adjudication discarded: the proposal was already answered")
        await db.commit()
        return
    narration: str | None = None
    if decision is not None and not state.get("paused"):
        try:
            if decision.approach:
                narration = await guided_scenes.accept_proposal(
                    db, state, decision.approach, by="The AI guide"
                )
                narration = f"{narration} {decision.reason}"
            else:
                narration = guided_scenes.decline_proposal(
                    state, decision.reason, by="The AI guide"
                )
        except HTTPException as exc:
            # The helpers raise before mutating, so ``state`` is still the open proposal.
            logger.warning("AI adjudication could not be applied: %s", exc.detail)
    if narration is None:
        state["proposal"]["ai"] = "unavailable"
        narration = f"The AI guide couldn't settle {current['name']}'s idea. The host will respond."
    await guided.record_state(
        db,
        game,
        state,
        narration,
        actor=None,
        label=LABEL,
        request_id=str(uuid.uuid4()),
        command={"action": "ai_adjudicate"},
        extra={"ai_adjudicated": True},
    )
