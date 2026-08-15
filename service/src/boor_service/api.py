"""FastAPI surface over the 5e SRD rules engine (SETUP-02).

A thin HTTP layer that exposes the pure domain logic in :mod:`boor_service.dice`,
:mod:`boor_service.mechanics`, and :mod:`boor_service.combat` so the Next.js web
app (and, later, the AI stand-in service) can call it. No persistence or auth yet
— those wait on the datastore/auth decisions (see ``boor/DECISIONS.md``).

The engine raises ``ValueError`` on bad input rather than swallowing it; we map
that to HTTP 400 so callers see the real failure. Missing/mistyped fields are
handled by Pydantic as 422 automatically.

Run locally with: ``uv run uvicorn boor_service.api:app --reload``.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.requests import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from boor_service import mechanics
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
