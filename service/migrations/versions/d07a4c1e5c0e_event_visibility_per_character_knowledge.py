"""event visibility — per-character knowledge scoping (DATA-07)

Revision ID: d07a4c1e5c0e
Revises: 975c11e58f23
Create Date: 2026-09-12 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd07a4c1e5c0e'
down_revision: Union[str, Sequence[str], None] = '975c11e58f23'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Enum types are managed explicitly (create with checkfirst, create_type=False on
# columns, drop on downgrade) so downgrades leave no orphaned types behind —
# same convention as the DATA-03 / DATA-02/04 migrations.
event_audience = postgresql.ENUM(
    'table', 'characters', 'dm', name='event_audience', create_type=False,
)


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    event_audience.create(bind, checkfirst=True)

    op.add_column(
        'session_events',
        sa.Column(
            'audience',
            event_audience,
            nullable=False,
            server_default='table',
        ),
    )
    op.add_column(
        'session_events',
        sa.Column(
            'visible_to',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    # server_default was only needed to backfill existing rows
    op.alter_column('session_events', 'audience', server_default=None)
    op.alter_column('session_events', 'visible_to', server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('session_events', 'visible_to')
    op.drop_column('session_events', 'audience')

    bind = op.get_bind()
    event_audience.drop(bind, checkfirst=True)
