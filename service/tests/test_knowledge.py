"""Pure tests for per-character knowledge scoping (DATA-07 / primer §4.2).

No database: the visibility predicate is the load-bearing rule, and every
layer (repository, log, realtime, stand-in) must share it.
"""

from __future__ import annotations

import pytest

from boor_service.db.models import EventAudience, MembershipRole
from boor_service.knowledge import (
    is_visible,
    normalize_visibility,
    parse_audience,
    presence_may_receive,
)

ROGUE = "rogue-id"
PALADIN = "paladin-id"


def test_parse_audience_defaults_to_table() -> None:
    assert parse_audience(None) is EventAudience.table
    assert parse_audience("table") is EventAudience.table
    assert parse_audience(EventAudience.dm) is EventAudience.dm


def test_parse_audience_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="unknown audience"):
        parse_audience("party")


def test_normalize_table_and_dm_drop_character_ids() -> None:
    audience, visible = normalize_visibility(EventAudience.table, [ROGUE])
    assert audience is EventAudience.table
    assert visible == []

    audience, visible = normalize_visibility("dm", [ROGUE, PALADIN])
    assert audience is EventAudience.dm
    assert visible == []


def test_normalize_characters_requires_ids_and_dedupes() -> None:
    audience, visible = normalize_visibility("characters", [PALADIN, ROGUE, ROGUE])
    assert audience is EventAudience.characters
    assert visible == sorted([PALADIN, ROGUE])

    with pytest.raises(ValueError, match="at least one character id"):
        normalize_visibility(EventAudience.characters, [])


def test_normalize_rejects_a_string_visible_to() -> None:
    with pytest.raises(ValueError, match="must be a list"):
        normalize_visibility("characters", ROGUE)  # type: ignore[arg-type]


def test_table_event_is_visible_to_every_character() -> None:
    assert is_visible(EventAudience.table, [], character_ids=(PALADIN,))
    assert is_visible(EventAudience.table, [], character_ids=())


def test_dm_event_is_invisible_to_characters_and_visible_to_the_dm() -> None:
    assert not is_visible(EventAudience.dm, [], character_ids=(PALADIN,), is_dm=False)
    assert is_visible(EventAudience.dm, [], character_ids=(PALADIN,), is_dm=True)


def test_characters_event_is_visible_only_to_the_listed_set() -> None:
    visible_to = [ROGUE]
    assert is_visible(EventAudience.characters, visible_to, character_ids=(ROGUE,), is_dm=False)
    assert not is_visible(
        EventAudience.characters, visible_to, character_ids=(PALADIN,), is_dm=False
    )
    # the human DM still sees it
    assert is_visible(EventAudience.characters, visible_to, character_ids=(PALADIN,), is_dm=True)


def test_stand_in_never_inherits_dm_omniscience() -> None:
    """The primer's example: the paladin's stand-in must not see the rogue's bribe."""
    bribe = (EventAudience.characters, [ROGUE])
    assert not is_visible(*bribe, character_ids=(PALADIN,), is_dm=False)


def test_presence_fan_out_matches_viewer_rules() -> None:
    assert presence_may_receive(
        EventAudience.characters,
        [ROGUE],
        role=MembershipRole.player,
        character_ids=(ROGUE,),
    )
    assert not presence_may_receive(
        EventAudience.characters,
        [ROGUE],
        role=MembershipRole.player,
        character_ids=(PALADIN,),
    )
    assert presence_may_receive(
        EventAudience.characters,
        [ROGUE],
        role=MembershipRole.dm,
        character_ids=(),
    )
    assert not presence_may_receive(
        EventAudience.dm,
        [],
        role=MembershipRole.player,
        character_ids=(ROGUE,),
    )
