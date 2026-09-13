"""FastAPI surface over the 5e SRD rules engine + authenticated campaign reads.

A thin HTTP layer that exposes the pure domain logic in :mod:`boor_service.dice`,
:mod:`boor_service.mechanics`, and :mod:`boor_service.combat` so the Next.js web
app (and the AI stand-in service) can call it. The rules endpoints are
stateless/unauthenticated (pure math); the campaign endpoints are gated by Clerk
auth (:mod:`boor_service.auth`) — token -> mirrored user -> per-campaign role.

The engine raises ``ValueError`` on bad input rather than swallowing it; we map
that to HTTP 400 so callers see the real failure. Missing/mistyped fields are
handled by Pydantic as 422 automatically.

Run locally with: ``uv run uvicorn boor_service.api:app --reload``.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.requests import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from boor_service import mechanics, realtime
from boor_service.ai.actions import ActionType
from boor_service.ai.guardrails import RedLine, RedLineKind
from boor_service.auth.dependencies import (
    CharacterForEditor,
    CharacterForMember,
    CurrentMembership,
    CurrentUser,
    GameSessionForDM,
    GameSessionForMember,
    RequireDM,
    SessionDep,
    VerifierDep,
)
from boor_service.character import Character as CharacterSheet
from boor_service.db import repository
from boor_service.db.models import (
    Campaign,
    Character,
    EventAudience,
    EventKind,
    GameSession,
    MembershipRole,
    RiskTolerance,
    SessionEvent,
    SessionStatus,
)
from boor_service.dice import RollResult, roll, roll_d20

logger = logging.getLogger(__name__)

app = FastAPI(
    title="boor rules service",
    version="0.1.0",
    summary="HTTP surface over the D&D 5e SRD rules engine.",
)


@app.exception_handler(ValueError)
async def _value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    """Surface engine ``ValueError``s (bad notation, out-of-range score) as 400."""
    logger.info("rejected request to %s: %s", request.url.path, exc)
    return JSONResponse(status_code=400, content={"detail": str(exc)})


# --- Response models -------------------------------------------------------


class RollOut(BaseModel):
    total: int
    dice: list[int]
    modifier: int
    notation: str
    dropped: list[int]


class CheckOut(BaseModel):
    roll: RollOut
    total: int
    dc: int | None
    is_success: bool | None


class AttackOut(BaseModel):
    roll: RollOut
    total: int
    ac: int
    is_hit: bool
    is_critical: bool
    is_fumble: bool


def _roll_out(result: RollResult) -> RollOut:
    return RollOut(
        total=result.total,
        dice=list(result.dice),
        modifier=result.modifier,
        notation=result.notation,
        dropped=list(result.dropped),
    )


def _check_out(result: mechanics.CheckResult) -> CheckOut:
    return CheckOut(
        roll=_roll_out(result.roll),
        total=result.total,
        dc=result.dc,
        is_success=result.is_success,
    )


# --- Request models --------------------------------------------------------


class RollIn(BaseModel):
    notation: str


class D20In(BaseModel):
    modifier: int = 0
    advantage: bool = False
    disadvantage: bool = False


class AbilityCheckIn(BaseModel):
    bonus: int = 0
    dc: int | None = None
    advantage: bool = False
    disadvantage: bool = False


class SkillCheckIn(BaseModel):
    ability_score: int
    proficient: bool = False
    expertise: bool = False
    level: int = 1
    dc: int | None = None
    advantage: bool = False
    disadvantage: bool = False


class SaveIn(BaseModel):
    ability_score: int
    proficient: bool = False
    level: int = 1
    dc: int | None = None
    advantage: bool = False
    disadvantage: bool = False


class AttackIn(BaseModel):
    bonus: int
    ac: int
    advantage: bool = False
    disadvantage: bool = False


class DamageIn(BaseModel):
    notation: str
    critical: bool = False


# --- Routes ----------------------------------------------------------------


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/dice/roll", response_model=RollOut)
def dice_roll(body: RollIn) -> RollOut:
    return _roll_out(roll(body.notation))


@app.post("/dice/d20", response_model=RollOut)
def dice_d20(body: D20In) -> RollOut:
    return _roll_out(
        roll_d20(body.modifier, advantage=body.advantage, disadvantage=body.disadvantage)
    )


@app.post("/checks/ability", response_model=CheckOut)
def check_ability(body: AbilityCheckIn) -> CheckOut:
    return _check_out(
        mechanics.ability_check(
            body.bonus, dc=body.dc, advantage=body.advantage, disadvantage=body.disadvantage
        )
    )


@app.post("/checks/skill", response_model=CheckOut)
def check_skill(body: SkillCheckIn) -> CheckOut:
    return _check_out(
        mechanics.skill_check(
            ability_score=body.ability_score,
            proficient=body.proficient,
            expertise=body.expertise,
            level=body.level,
            dc=body.dc,
            advantage=body.advantage,
            disadvantage=body.disadvantage,
        )
    )


@app.post("/checks/save", response_model=CheckOut)
def check_save(body: SaveIn) -> CheckOut:
    return _check_out(
        mechanics.saving_throw(
            ability_score=body.ability_score,
            proficient=body.proficient,
            level=body.level,
            dc=body.dc,
            advantage=body.advantage,
            disadvantage=body.disadvantage,
        )
    )


@app.post("/combat/attack", response_model=AttackOut)
def combat_attack(body: AttackIn) -> AttackOut:
    result = mechanics.attack_roll(
        body.bonus, body.ac, advantage=body.advantage, disadvantage=body.disadvantage
    )
    return AttackOut(
        roll=_roll_out(result.roll),
        total=result.total,
        ac=result.ac,
        is_hit=result.is_hit,
        is_critical=result.is_critical,
        is_fumble=result.is_fumble,
    )


@app.post("/combat/damage", response_model=RollOut)
def combat_damage(body: DamageIn) -> RollOut:
    return _roll_out(mechanics.roll_damage(body.notation, critical=body.critical))


# --- Authenticated BFF surface (Clerk, AUTH-03; DATA-01/02/04) --------------
# The service owns all data (D-02): every campaign/character route is gated by the
# auth dependencies, which resolve a Clerk token to a mirrored user and enforce
# per-campaign roles. Each handler is thin over boor_service.db.repository.


class MeOut(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str | None


class MemberOut(BaseModel):
    user_id: uuid.UUID
    role: MembershipRole
    display_name: str | None


class CampaignCreateIn(BaseModel):
    name: str


class CampaignOut(BaseModel):
    id: uuid.UUID
    name: str
    owner_id: uuid.UUID
    my_role: MembershipRole


class InviteCreateIn(BaseModel):
    email: str
    role: MembershipRole = MembershipRole.player


class InviteOut(BaseModel):
    id: uuid.UUID
    token: str
    email: str
    role: MembershipRole
    status: str


class AcceptOut(BaseModel):
    campaign_id: uuid.UUID
    role: MembershipRole


class CharacterCreateIn(BaseModel):
    name: str
    level: int = 1
    abilities: dict[str, int]
    max_hp: int
    skill_proficiencies: list[str] = []
    skill_expertise: list[str] = []
    save_proficiencies: list[str] = []
    base_armor_class: int | None = None
    resistances: list[str] = []
    immunities: list[str] = []
    vulnerabilities: list[str] = []


class CharacterOut(BaseModel):
    id: uuid.UUID
    campaign_id: uuid.UUID
    player_id: uuid.UUID | None
    name: str
    level: int
    sheet: dict


class ProfileIn(BaseModel):
    persona: str = ""
    standing_instructions: str = ""
    risk_tolerance: RiskTolerance = RiskTolerance.balanced
    traits: dict = {}


class ProfileOut(BaseModel):
    character_id: uuid.UUID
    persona: str
    standing_instructions: str
    risk_tolerance: RiskTolerance
    traits: dict


class RedLineIn(BaseModel):
    kind: RedLineKind
    entity_ids: list[str] = []
    action_types: list[ActionType] = []
    note: str = ""


class RedLineOut(BaseModel):
    kind: RedLineKind
    entity_ids: list[str]
    action_types: list[ActionType]
    note: str


class SessionCreateIn(BaseModel):
    title: str | None = None


class SessionOut(BaseModel):
    id: uuid.UUID
    campaign_id: uuid.UUID
    title: str | None
    status: SessionStatus
    started_at: datetime | None
    ended_at: datetime | None


class EventOut(BaseModel):
    seq: int
    kind: EventKind
    actor_user_id: uuid.UUID | None
    actor_label: str | None
    body: str | None
    payload: dict
    ai_generated: bool
    audience: EventAudience
    visible_to: list[str]
    created_at: datetime


# --- me + campaigns --------------------------------------------------------


@app.get("/me", response_model=MeOut)
async def me(user: CurrentUser) -> MeOut:
    """The authenticated caller's mirrored account (proves token -> user)."""
    return MeOut(id=user.id, email=user.email, display_name=user.display_name)


@app.post("/campaigns", response_model=CampaignOut, status_code=201)
async def create_campaign(
    body: CampaignCreateIn, user: CurrentUser, session: SessionDep
) -> CampaignOut:
    """Create a campaign; the caller becomes its DM."""
    campaign = await repository.create_campaign_with_owner(session, name=body.name, owner=user)
    return CampaignOut(
        id=campaign.id, name=campaign.name, owner_id=campaign.owner_id, my_role=MembershipRole.dm
    )


@app.get("/campaigns", response_model=list[CampaignOut])
async def list_my_campaigns(user: CurrentUser, session: SessionDep) -> list[CampaignOut]:
    """Every campaign the caller belongs to, with their role in each."""
    memberships = await repository.campaigns_for_user(session, user_id=user.id)
    return [
        CampaignOut(
            id=m.campaign.id,
            name=m.campaign.name,
            owner_id=m.campaign.owner_id,
            my_role=m.role,
        )
        for m in memberships
    ]


@app.get("/campaigns/{campaign_id}/members", response_model=list[MemberOut])
async def list_members(
    campaign_id: uuid.UUID,
    _membership: CurrentMembership,
    session: SessionDep,
) -> list[MemberOut]:
    """Roster of a campaign the caller belongs to (any member may read)."""
    members = await repository.campaign_members(session, campaign_id=campaign_id)
    return [
        MemberOut(user_id=m.user_id, role=m.role, display_name=m.user.display_name) for m in members
    ]


@app.delete("/campaigns/{campaign_id}/members/{user_id}", status_code=204)
async def remove_member(
    campaign_id: uuid.UUID,
    user_id: uuid.UUID,
    _dm: RequireDM,
    session: SessionDep,
) -> None:
    """Remove a member from a campaign — DM only."""
    members = await repository.campaign_members(session, campaign_id=campaign_id)
    target = next((m for m in members if m.user_id == user_id), None)
    if target is None:
        return
    await session.delete(target)


# --- invites (AUTH-02) -----------------------------------------------------


@app.post("/campaigns/{campaign_id}/invites", response_model=InviteOut, status_code=201)
async def create_invite(
    campaign_id: uuid.UUID,
    body: InviteCreateIn,
    user: CurrentUser,
    _dm: RequireDM,
    session: SessionDep,
) -> InviteOut:
    """Invite a player to the campaign by email — DM only."""
    invite = await repository.invite_player(
        session,
        campaign=await _require_campaign(session, campaign_id),
        email=body.email,
        invited_by=user,
        role=body.role,
    )
    return InviteOut(
        id=invite.id,
        token=invite.token,
        email=invite.email,
        role=invite.role,
        status=invite.status.value,
    )


@app.post("/invites/{token}/accept", response_model=AcceptOut)
async def accept_invite(token: str, user: CurrentUser, session: SessionDep) -> AcceptOut:
    """Redeem an invite token, joining the caller to the campaign."""
    membership = await repository.accept_invite(session, token=token, user=user)
    return AcceptOut(campaign_id=membership.campaign_id, role=membership.role)


# --- characters (DATA-02) --------------------------------------------------


@app.post("/campaigns/{campaign_id}/characters", response_model=CharacterOut, status_code=201)
async def create_character(
    campaign_id: uuid.UUID,
    body: CharacterCreateIn,
    user: CurrentUser,
    _membership: CurrentMembership,
    session: SessionDep,
) -> CharacterOut:
    """Create a character in a campaign, owned by the caller (any member may)."""
    # Build the domain sheet so it is validated (bad scores/levels -> 400) before
    # it is persisted as the JSONB blob.
    sheet = CharacterSheet(
        name=body.name,
        level=body.level,
        abilities=body.abilities,
        max_hp=body.max_hp,
        skill_proficiencies=frozenset(body.skill_proficiencies),
        skill_expertise=frozenset(body.skill_expertise),
        save_proficiencies=frozenset(body.save_proficiencies),
        base_armor_class=body.base_armor_class,
        resistances=frozenset(body.resistances),
        immunities=frozenset(body.immunities),
        vulnerabilities=frozenset(body.vulnerabilities),
    ).to_sheet()
    character = await repository.create_character(
        session,
        campaign=await _require_campaign(session, campaign_id),
        name=body.name,
        level=body.level,
        sheet=sheet,
        player=user,
    )
    return _character_out(character)


@app.get("/campaigns/{campaign_id}/characters", response_model=list[CharacterOut])
async def list_characters(
    campaign_id: uuid.UUID, _membership: CurrentMembership, session: SessionDep
) -> list[CharacterOut]:
    """Every character in a campaign the caller belongs to."""
    characters = await repository.characters_in_campaign(session, campaign_id=campaign_id)
    return [_character_out(c) for c in characters]


@app.get("/characters/{character_id}", response_model=CharacterOut)
async def get_character(character: CharacterForMember) -> CharacterOut:
    """A single character (any member of its campaign may read)."""
    return _character_out(character)


# --- personality profile + red lines (DATA-04) -----------------------------


@app.put("/characters/{character_id}/profile", response_model=ProfileOut)
async def set_profile(
    body: ProfileIn, character: CharacterForEditor, session: SessionDep
) -> ProfileOut:
    """Set/replace a character's stand-in personality profile (player or DM)."""
    profile = await repository.set_personality_profile(
        session,
        character=character,
        persona=body.persona,
        standing_instructions=body.standing_instructions,
        risk_tolerance=body.risk_tolerance,
        traits=body.traits,
    )
    return ProfileOut(
        character_id=character.id,
        persona=profile.persona,
        standing_instructions=profile.standing_instructions,
        risk_tolerance=profile.risk_tolerance,
        traits=profile.traits,
    )


@app.get("/characters/{character_id}/profile", response_model=ProfileOut)
async def get_profile(character: CharacterForMember, session: SessionDep) -> ProfileOut:
    """A character's personality profile (empty defaults if none set yet)."""
    profile = await repository.personality_profile_for(session, character=character)
    if profile is None:
        return ProfileOut(
            character_id=character.id,
            persona="",
            standing_instructions="",
            risk_tolerance=RiskTolerance.balanced,
            traits={},
        )
    return ProfileOut(
        character_id=character.id,
        persona=profile.persona,
        standing_instructions=profile.standing_instructions,
        risk_tolerance=profile.risk_tolerance,
        traits=profile.traits,
    )


@app.post("/characters/{character_id}/red-lines", response_model=RedLineOut, status_code=201)
async def add_red_line(
    body: RedLineIn, character: CharacterForEditor, session: SessionDep
) -> RedLineOut:
    """Append a standing red line to a character's stand-in (player or DM)."""
    row = await repository.add_red_line(
        session,
        character=character,
        red_line=RedLine(
            kind=body.kind,
            entity_ids=frozenset(body.entity_ids),
            action_types=frozenset(body.action_types),
            note=body.note,
        ),
    )
    return _red_line_out(row.as_red_line())


@app.get("/characters/{character_id}/red-lines", response_model=list[RedLineOut])
async def list_red_lines(character: CharacterForMember, session: SessionDep) -> list[RedLineOut]:
    """A character's standing red lines, in evaluation order."""
    red_lines = await repository.red_lines_for(session, character=character)
    return [_red_line_out(rl) for rl in red_lines]


# --- play sessions + timeline (DATA-03; the theater-of-the-mind table) ------
# A session is the live room friends join for MILE-1. The DM opens one; any member
# lists/reads them and replays the timeline to catch up on join. Realtime frames
# (chat, dice) append to this same timeline in boor_service.realtime.


@app.post("/campaigns/{campaign_id}/sessions", response_model=SessionOut, status_code=201)
async def create_game_session(
    campaign_id: uuid.UUID,
    body: SessionCreateIn,
    _dm: RequireDM,
    session: SessionDep,
) -> SessionOut:
    """Open a new play session for the campaign, started immediately — DM only."""
    game_session = await repository.create_session(
        session,
        campaign=await _require_campaign(session, campaign_id),
        title=body.title,
        status=SessionStatus.active,
    )
    return _session_out(game_session)


@app.get("/campaigns/{campaign_id}/sessions", response_model=list[SessionOut])
async def list_game_sessions(
    campaign_id: uuid.UUID, _membership: CurrentMembership, session: SessionDep
) -> list[SessionOut]:
    """Every play session of a campaign the caller belongs to, newest first."""
    sessions = await repository.sessions_for_campaign(session, campaign_id=campaign_id)
    return [_session_out(s) for s in sessions]


@app.get("/sessions/{session_id}", response_model=SessionOut)
async def get_game_session(game_session: GameSessionForMember) -> SessionOut:
    """A single play session (any member of its campaign may read)."""
    return _session_out(game_session)


@app.get("/sessions/{session_id}/log", response_model=list[EventOut])
async def get_session_log(
    game_session: GameSessionForMember, user: CurrentUser, session: SessionDep
) -> list[EventOut]:
    """The viewer's scoped timeline of a session, for replay on join.

    The DM sees the full record. A player sees table-public events plus
    whispers their own characters know (DATA-07). A late joiner cannot
    replay a private channel they weren't in.
    """
    events = await repository.timeline_for_viewer(session, game_session=game_session, viewer=user)
    return [_event_out(e) for e in events]


@app.post("/sessions/{session_id}/end", response_model=SessionOut)
async def end_game_session(game_session: GameSessionForDM, session: SessionDep) -> SessionOut:
    """Mark a session ended — DM only."""
    ended = await repository.end_session(session, game_session=game_session)
    return _session_out(ended)


# --- helpers ---------------------------------------------------------------


async def _require_campaign(session: AsyncSession, campaign_id: uuid.UUID) -> Campaign:
    """Load a campaign or 404. (Callers past the auth gate imply it exists; be safe.)"""
    campaign = await session.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="campaign not found")
    return campaign


def _character_out(character: Character) -> CharacterOut:
    return CharacterOut(
        id=character.id,
        campaign_id=character.campaign_id,
        player_id=character.player_id,
        name=character.name,
        level=character.level,
        sheet=character.sheet,
    )


def _session_out(game_session: GameSession) -> SessionOut:
    return SessionOut(
        id=game_session.id,
        campaign_id=game_session.campaign_id,
        title=game_session.title,
        status=game_session.status,
        started_at=game_session.started_at,
        ended_at=game_session.ended_at,
    )


def _event_out(event: SessionEvent) -> EventOut:
    return EventOut(
        seq=event.seq,
        kind=event.kind,
        actor_user_id=event.actor_user_id,
        actor_label=event.actor_label,
        body=event.body,
        payload=event.payload,
        ai_generated=event.ai_generated,
        audience=event.audience,
        visible_to=list(event.visible_to),
        created_at=event.created_at,
    )


def _red_line_out(red_line: RedLine) -> RedLineOut:
    return RedLineOut(
        kind=red_line.kind,
        entity_ids=sorted(red_line.entity_ids),
        action_types=sorted(red_line.action_types),
        note=red_line.note,
    )


# --- Realtime session room (WebSocket, VTT-01) -----------------------------


@app.websocket("/ws/sessions/{session_id}")
async def session_ws(
    websocket: WebSocket,
    session_id: uuid.UUID,
    session: SessionDep,
    verifier: VerifierDep,
) -> None:
    """Join a game session's shared realtime room.

    Authenticate with ``?token=<clerk-jwt>`` (browsers can't set WS headers). The
    handshake verifies the token and campaign membership before joining the room;
    see :mod:`boor_service.realtime`.
    """
    await realtime.handle_connection(websocket, session_id, session, verifier, realtime.hub)
