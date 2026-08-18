"""AI stand-in reasoning: persona + game state -> guarded, engine-adjudicated action.

The make-or-break slice of the agent. Given a character, its persona +
standing red lines, and the current session timeline, Claude reasons about the
scene and proposes its next in-character action **as a structured tool call**. The
tools wrap the deterministic rules engine — the model never invents a die result;
it declares intent, and :mod:`boor_service.mechanics` rolls. Every proposed action
is validated by :func:`boor_service.ai.guardrails.check_action` *before* dispatch,
so a red-lined action is refused and never reaches the engine.

Design: the LLM reasons, the engine adjudicates, the guardrail governs. The
Anthropic client is injected (a structural :class:`SupportsMessages`) so unit
tests mock the model and one env-gated test exercises the live API. Errors —
model refusal, no tool call, bad input — are raised, not swallowed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from boor_service import mechanics
from boor_service.ai.actions import ActionType, GameState, ProposedAction, SelfRisk
from boor_service.ai.guardrails import RedLine, Refused, check_action
from boor_service.character import ABILITIES
from boor_service.character import Character as CharacterSheet
from boor_service.db import repository
from boor_service.db.models import Character as CharacterRow
from boor_service.db.models import (
    EventKind,
    GameSession,
    PersonalityProfile,
    RiskTolerance,
    SessionEvent,
)
from boor_service.dice import SupportsRandint
from boor_service.mechanics import CheckResult

logger = logging.getLogger(__name__)

#: Default model for stand-in reasoning (see the claude-api reference).
DEFAULT_MODEL = "claude-opus-4-8"

_MAX_TOKENS = 4096


class SupportsMessages(Protocol):
    """Structural type for the Anthropic client's ``messages`` surface.

    ``anthropic.Anthropic()`` satisfies this; tests pass a fake with the same
    shape. Mirrors the injectable-RNG pattern the rules engine already uses.
    """

    @property
    def messages(self) -> _MessagesAPI: ...


class _MessagesAPI(Protocol):
    def create(self, **kwargs: Any) -> Any: ...


class StandInError(RuntimeError):
    """The stand-in could not produce an action (model refused, or no tool call)."""


#: Tool schemas exposed to the model — each wraps the deterministic rules engine.
ACTION_TOOLS: list[dict[str, Any]] = [
    {
        "name": "attack",
        "description": (
            "Make a weapon or spell attack against a target. The engine rolls to "
            "hit and, on a hit, rolls damage — you do not invent the numbers."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "target_id": {"type": "string", "description": "id of the entity to attack"},
                "attack_bonus": {"type": "integer", "description": "your total attack bonus"},
                "target_ac": {"type": "integer", "description": "the target's armor class"},
                "damage": {"type": "string", "description": "damage dice, e.g. '1d8+3'"},
                "self_risk": {
                    "type": "string",
                    "enum": ["none", "risky", "lethal"],
                    "description": "how dangerous this action is to you",
                },
                "narration": {
                    "type": "string",
                    "description": "one in-character sentence describing the action",
                },
            },
            "required": ["target_id", "attack_bonus", "target_ac", "damage", "narration"],
        },
    },
    {
        "name": "ability_check",
        "description": "Attempt an ability or skill check. The engine rolls the d20.",
        "input_schema": {
            "type": "object",
            "properties": {
                "skill": {"type": "string", "description": "the skill or ability, e.g. 'Stealth'"},
                "bonus": {"type": "integer", "description": "your total check bonus"},
                "dc": {"type": "integer", "description": "difficulty class, if known"},
                "narration": {"type": "string", "description": "one in-character sentence"},
            },
            "required": ["skill", "bonus", "narration"],
        },
    },
    {
        "name": "speak",
        "description": "Say something in character (no dice).",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "what your character says, in voice"},
            },
            "required": ["message"],
        },
    },
    {
        "name": "move",
        "description": "Move to a position or toward something (no dice).",
        "input_schema": {
            "type": "object",
            "properties": {
                "destination": {"type": "string", "description": "where you move to"},
                "self_risk": {
                    "type": "string",
                    "enum": ["none", "risky", "lethal"],
                    "description": "how dangerous the move is to you",
                },
                "narration": {"type": "string", "description": "one in-character sentence"},
            },
            "required": ["destination", "narration"],
        },
    },
]


@dataclass(frozen=True)
class StandInContext:
    """Everything the stand-in needs to decide a character's turn."""

    character_name: str
    character_sheet: str
    persona: str
    standing_instructions: str
    red_lines: tuple[RedLine, ...]
    game_state: GameState


@dataclass(frozen=True)
class StandInDecision:
    """The outcome of one stand-in turn.

    ``allowed`` is False when a red line refused the action — in that case the
    engine was never called (``engine_result`` is None) and ``refusal`` explains.
    """

    tool_name: str
    tool_input: dict[str, Any]
    action: ProposedAction
    allowed: bool
    summary: str
    refusal: Refused | None = None
    engine_result: object | None = field(default=None)


def decide_action(
    client: SupportsMessages,
    context: StandInContext,
    *,
    timeline_text: str,
    rng: SupportsRandint | None = None,
    model: str = DEFAULT_MODEL,
) -> StandInDecision:
    """Ask the model for the character's next action, guard it, and adjudicate it.

    Raises :class:`StandInError` if the model refuses or declines to call a tool.
    """
    response = client.messages.create(
        model=model,
        max_tokens=_MAX_TOKENS,
        thinking={"type": "adaptive"},
        system=_system_prompt(context),
        tools=ACTION_TOOLS,
        tool_choice={"type": "auto"},
        messages=[{"role": "user", "content": _turn_prompt(context, timeline_text)}],
    )

    if getattr(response, "stop_reason", None) == "refusal":
        raise StandInError("model refused to produce a stand-in action")

    tool_use = next(
        (b for b in response.content if getattr(b, "type", None) == "tool_use"), None
    )
    if tool_use is None:
        raise StandInError("stand-in did not choose an action (no tool call)")

    return _resolve(tool_use.name, dict(tool_use.input), context, rng)


def _resolve(
    name: str,
    tool_input: dict[str, Any],
    context: StandInContext,
    rng: SupportsRandint | None,
) -> StandInDecision:
    action = _to_action(name, tool_input, context.game_state.actor_id)

    decision = check_action(action, context.red_lines, context.game_state)
    if isinstance(decision, Refused):
        logger.info("stand-in action refused: %s", decision.reason)
        return StandInDecision(
            tool_name=name,
            tool_input=tool_input,
            action=action,
            allowed=False,
            summary=f"declined to {name}: {decision.reason}",
            refusal=decision,
        )

    engine_result = _dispatch(name, tool_input, rng)
    return StandInDecision(
        tool_name=name,
        tool_input=tool_input,
        action=action,
        allowed=True,
        summary=_summarize(name, tool_input, engine_result),
        engine_result=engine_result,
    )


def _to_action(name: str, tool_input: dict[str, Any], actor_id: str) -> ProposedAction:
    if name == "attack":
        return ProposedAction(
            type=ActionType.attack,
            actor_id=actor_id,
            target_ids=(tool_input["target_id"],),
            offensive=True,
            self_risk=SelfRisk(tool_input.get("self_risk", "none")),
            description=tool_input.get("narration", ""),
        )
    if name == "ability_check":
        return ProposedAction(
            type=ActionType.skill_check,
            actor_id=actor_id,
            description=tool_input.get("narration", ""),
        )
    if name == "speak":
        return ProposedAction(
            type=ActionType.speak, actor_id=actor_id, description=tool_input["message"]
        )
    if name == "move":
        return ProposedAction(
            type=ActionType.move,
            actor_id=actor_id,
            self_risk=SelfRisk(tool_input.get("self_risk", "none")),
            description=tool_input.get("narration", ""),
        )
    raise StandInError(f"unknown action tool: {name!r}")


def _dispatch(
    name: str, tool_input: dict[str, Any], rng: SupportsRandint | None
) -> object | None:
    """Run the allowed action through the real rules engine."""
    if name == "attack":
        attack = mechanics.attack_roll(
            tool_input["attack_bonus"], tool_input["target_ac"], rng=rng
        )
        damage = (
            mechanics.roll_damage(tool_input["damage"], critical=attack.is_critical, rng=rng)
            if attack.is_hit
            else None
        )
        return {"attack": attack, "damage": damage}
    if name == "ability_check":
        return mechanics.ability_check(
            tool_input.get("bonus", 0), dc=tool_input.get("dc"), rng=rng
        )
    return None  # speak / move have no dice


def _summarize(name: str, tool_input: dict[str, Any], engine_result: object | None) -> str:
    if name == "attack" and isinstance(engine_result, dict):
        attack = engine_result["attack"]
        if not attack.is_hit:
            return f"{tool_input.get('narration', 'attacks')} — misses (rolled {attack.total})"
        damage = engine_result["damage"]
        crit = " critically" if attack.is_critical else ""
        return (
            f"{tool_input.get('narration', 'attacks')} —{crit} hits (rolled "
            f"{attack.total}) for {damage.total} damage"
        )
    if name == "ability_check" and isinstance(engine_result, CheckResult):
        outcome = "" if engine_result.is_success is None else (
            " (success)" if engine_result.is_success else " (failure)"
        )
        narration = tool_input.get("narration", "attempts a check")
        return f"{narration} — rolled {engine_result.total}{outcome}"
    if name == "speak":
        return tool_input["message"]
    if name == "move":
        return tool_input.get("narration", f"moves to {tool_input.get('destination', '?')}")
    return tool_input.get("narration", name)


# --- Building context from persisted data (DATA-02/04 -> the stand-in) -------

#: How each risk-tolerance setting is phrased as guidance in the prompt.
_RISK_GUIDANCE: dict[RiskTolerance, str] = {
    RiskTolerance.cautious: "Play cautiously; avoid unnecessary danger.",
    RiskTolerance.balanced: "Take sensible risks appropriate to the moment.",
    RiskTolerance.bold: "Lean into bold, decisive action.",
    RiskTolerance.reckless: "Court danger; act with abandon.",
}


def render_character_sheet(sheet: CharacterSheet) -> str:
    """A compact text rendering of a character's derived stats, for the prompt."""
    abilities = ", ".join(
        f"{ability.upper()} {sheet.abilities[ability]} ({sheet.ability_modifier(ability):+d})"
        for ability in ABILITIES
    )
    lines = [
        f"Level {sheet.level}, proficiency +{sheet.proficiency_bonus}",
        (
            f"AC {sheet.armor_class}, max HP {sheet.max_hp}, "
            f"initiative {sheet.initiative_bonus:+d}, "
            f"passive perception {sheet.passive_perception}"
        ),
        abilities,
    ]
    if sheet.skill_proficiencies:
        lines.append("Proficient skills: " + ", ".join(sorted(sheet.skill_proficiencies)))
    if sheet.skill_expertise:
        lines.append("Expertise: " + ", ".join(sorted(sheet.skill_expertise)))
    if sheet.save_proficiencies:
        lines.append("Saving throws: " + ", ".join(sorted(sheet.save_proficiencies)))
    return "\n".join(lines)


def _standing_instructions_text(profile: PersonalityProfile | None) -> str:
    """Fold the player's free-text guidance and risk-tolerance into one block."""
    if profile is None:
        return ""
    parts: list[str] = []
    if profile.standing_instructions:
        parts.append(profile.standing_instructions)
    parts.append(_RISK_GUIDANCE[profile.risk_tolerance])
    return "\n".join(parts)


async def build_standin_context(
    session: AsyncSession,
    *,
    character: CharacterRow,
    game_state: GameState,
) -> StandInContext:
    """Assemble a :class:`StandInContext` from a character's persisted record.

    Reconstructs the domain sheet from the JSONB blob, loads the personality
    profile and standing red lines, and renders the sheet text the prompt needs.
    The live ``game_state`` (current scene) is supplied by the caller — it is not
    part of the durable character record. A character with no profile yet still
    yields a usable, mechanically-driven context with an empty persona.
    """
    sheet = CharacterSheet.from_sheet(character.sheet)
    profile = await repository.personality_profile_for(session, character=character)
    red_lines = await repository.red_lines_for(session, character=character)
    if profile is None:
        logger.warning(
            "character %s has no personality profile; standing in with empty persona",
            character.id,
        )
    return StandInContext(
        character_name=character.name,
        character_sheet=render_character_sheet(sheet),
        persona=profile.persona if profile is not None else "",
        standing_instructions=_standing_instructions_text(profile),
        red_lines=red_lines,
        game_state=game_state,
    )


# --- Timeline persistence (AI-08 attribution) -------------------------------

_EVENT_KIND = {
    "attack": EventKind.action,
    "ability_check": EventKind.roll,
    "speak": EventKind.in_character,
    "move": EventKind.move,
}


def event_kind_for(decision: StandInDecision) -> EventKind:
    return _EVENT_KIND.get(decision.tool_name, EventKind.action)


def event_payload(decision: StandInDecision) -> dict[str, Any]:
    """A JSON-safe payload for the timeline entry."""
    payload: dict[str, Any] = {
        "tool": decision.tool_name,
        "input": dict(decision.tool_input),
        "allowed": decision.allowed,
    }
    if decision.refusal is not None:
        payload["refusal"] = decision.refusal.reason
    result = decision.engine_result
    if isinstance(result, dict):
        attack = result["attack"]
        payload["attack"] = {
            "total": attack.total,
            "hit": attack.is_hit,
            "critical": attack.is_critical,
            "fumble": attack.is_fumble,
            "ac": attack.ac,
        }
        if result["damage"] is not None:
            payload["damage"] = {"total": result["damage"].total}
    elif isinstance(result, CheckResult):
        payload["check"] = {
            "total": result.total,
            "dc": result.dc,
            "success": result.is_success,
        }
    return payload


async def act_on_turn(
    session: AsyncSession,
    *,
    game_session: GameSession,
    client: SupportsMessages,
    context: StandInContext,
    timeline_text: str,
    rng: SupportsRandint | None = None,
    model: str = DEFAULT_MODEL,
) -> tuple[StandInDecision, SessionEvent]:
    """Decide the stand-in's action and append it to the timeline, AI-attributed.

    The persisted event always carries ``ai_generated=True`` (AI-08), including
    refusals — the log makes clear the AI acted and, when it declined, why.
    """
    decision = decide_action(client, context, timeline_text=timeline_text, rng=rng, model=model)
    event = await repository.append_event(
        session,
        game_session=game_session,
        kind=event_kind_for(decision),
        actor_label=context.character_name,
        body=decision.summary,
        payload=event_payload(decision),
        ai_generated=True,
    )
    logger.info(
        "stand-in for %s acted (%s, allowed=%s) -> event %s",
        context.character_name,
        decision.tool_name,
        decision.allowed,
        event.id,
    )
    return decision, event


def _system_prompt(context: StandInContext) -> str:
    red_lines = (
        "\n".join(f"- {rl.note or rl.kind.value}" for rl in context.red_lines)
        or "- (none)"
    )
    return (
        f"You are playing {context.character_name} in a live Dungeons & Dragons "
        "session, standing in for an absent player. Act and speak in character, "
        "true to their persona and the standing instructions their player left.\n\n"
        f"CHARACTER SHEET:\n{context.character_sheet}\n\n"
        f"PERSONA / VOICE:\n{context.persona}\n\n"
        f"STANDING INSTRUCTIONS:\n{context.standing_instructions}\n\n"
        f"RED LINES (never cross these):\n{red_lines}\n\n"
        "It is your turn. Choose exactly one action by calling one of the provided "
        "tools. Do not narrate dice results yourself — the tools roll for you via "
        "the game's rules engine. Stay within your character's abilities and the "
        "red lines above."
    )


def _turn_prompt(context: StandInContext, timeline_text: str) -> str:
    return (
        "Here is what has happened so far this session:\n\n"
        f"{timeline_text}\n\n"
        f"It is {context.character_name}'s turn. Decide your single action now."
    )
