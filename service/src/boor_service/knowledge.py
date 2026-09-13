"""Per-character knowledge scoping (DATA-07 / build-primer §4.2).

Every fact in the campaign record carries a visibility set. A stand-in acts on
what *its character* knows, not on what the record contains. This module is the
pure enforcement of that rule: no I/O, no SQLAlchemy session — the repository,
the session log, the realtime hub, and the stand-in all call the same function
so they cannot drift.

Audience:

* ``table`` — everyone at the table knows this (the default; MILE-1 chat/dice).
* ``characters`` — only the characters in ``visible_to`` (and the human DM).
* ``dm`` — DM-only notes; stand-ins never see these.

The human DM is omniscient *as a viewer*. A stand-in is never a DM: it always
passes ``is_dm=False`` and a single character id, even when covering a DM's PC.
"""

from __future__ import annotations

import uuid
from collections.abc import Collection, Sequence

from boor_service.db.models import EventAudience, MembershipRole


def parse_audience(raw: object) -> EventAudience:
    """Coerce a wire value to :class:`EventAudience`; default ``table`` if omitted."""
    if raw is None:
        return EventAudience.table
    if isinstance(raw, EventAudience):
        return raw
    if isinstance(raw, str):
        try:
            return EventAudience(raw)
        except ValueError:
            raise ValueError(f"unknown audience: {raw!r}") from None
    raise ValueError(f"unknown audience: {raw!r}")


def normalize_visibility(
    audience: EventAudience | str | None = None,
    visible_to: Sequence[uuid.UUID | str] | None = None,
) -> tuple[EventAudience, list[str]]:
    """Validate and canonicalize an event's visibility for persistence.

    ``table`` and ``dm`` drop any supplied character ids (they aren't a character
    set). ``characters`` requires at least one id. Ids are stored as sorted
    unique strings so containment checks are deterministic.
    """
    parsed = parse_audience(audience)
    if visible_to is None:
        raw_ids: Sequence[uuid.UUID | str] = ()
    elif isinstance(visible_to, str | bytes) or not isinstance(visible_to, Sequence):
        raise ValueError("visible_to must be a list of character ids")
    else:
        raw_ids = visible_to
    ids = sorted({str(v) for v in raw_ids})
    if parsed is EventAudience.characters:
        if not ids:
            raise ValueError(
                "audience='characters' requires at least one character id in visible_to"
            )
        return parsed, ids
    return parsed, []


def is_visible(
    audience: EventAudience,
    visible_to: Sequence[str],
    *,
    character_ids: Collection[str] = (),
    is_dm: bool = False,
) -> bool:
    """Whether a viewer may know this event.

    Stand-ins pass the single character they play and ``is_dm=False`` — they
    never inherit DM omniscience. Human DMs pass ``is_dm=True`` and see everything.
    """
    if is_dm:
        return True
    if audience is EventAudience.table:
        return True
    if audience is EventAudience.dm:
        return False
    known = {str(c) for c in character_ids}
    return any(str(v) in known for v in visible_to)


def presence_may_receive(
    audience: EventAudience,
    visible_to: Sequence[str],
    *,
    role: MembershipRole,
    character_ids: Collection[str],
) -> bool:
    """Whether a live socket (a human at the table) should receive this event."""
    return is_visible(
        audience,
        visible_to,
        character_ids=character_ids,
        is_dm=role is MembershipRole.dm,
    )
