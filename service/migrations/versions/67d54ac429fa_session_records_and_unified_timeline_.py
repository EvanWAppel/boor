"""session records and unified timeline (DATA-03)

Revision ID: 67d54ac429fa
Revises: cbc5dcf80b3d
Create Date: 2026-08-15 17:27:28.327517

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '67d54ac429fa'
down_revision: Union[str, Sequence[str], None] = 'cbc5dcf80b3d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Enum types are managed explicitly (create with checkfirst, create_type=False on
# columns, drop on downgrade) so downgrades leave no orphaned types behind.
session_status = postgresql.ENUM(
    'scheduled', 'active', 'ended', name='session_status', create_type=False
)
event_kind = postgresql.ENUM(
    'roll', 'action', 'move', 'turn', 'narration', 'in_character',
    'out_of_character', 'system', name='event_kind', create_type=False,
)


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    session_status.create(bind, checkfirst=True)
    event_kind.create(bind, checkfirst=True)

    op.create_table('game_sessions',
    sa.Column('campaign_id', sa.Uuid(), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=True),
    sa.Column('status', session_status, nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_game_sessions_campaign_id'), 'game_sessions', ['campaign_id'], unique=False)
    op.create_table('session_events',
    sa.Column('session_id', sa.Uuid(), nullable=False),
    sa.Column('seq', sa.Integer(), nullable=False),
    sa.Column('kind', event_kind, nullable=False),
    sa.Column('actor_user_id', sa.Uuid(), nullable=True),
    sa.Column('actor_label', sa.String(length=120), nullable=True),
    sa.Column('body', sa.String(), nullable=True),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('ai_generated', sa.Boolean(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['session_id'], ['game_sessions.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('session_id', 'seq', name='uq_session_event_seq')
    )
    op.create_index(op.f('ix_session_events_actor_user_id'), 'session_events', ['actor_user_id'], unique=False)
    op.create_index(op.f('ix_session_events_session_id'), 'session_events', ['session_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_session_events_session_id'), table_name='session_events')
    op.drop_index(op.f('ix_session_events_actor_user_id'), table_name='session_events')
    op.drop_table('session_events')
    op.drop_index(op.f('ix_game_sessions_campaign_id'), table_name='game_sessions')
    op.drop_table('game_sessions')

    bind = op.get_bind()
    event_kind.drop(bind, checkfirst=True)
    session_status.drop(bind, checkfirst=True)
