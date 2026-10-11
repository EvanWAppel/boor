"""character recaps and "not my character" flags (AI-09)

Revision ID: a09c3e7b1f42
Revises: d07a4c1e5c0e
Create Date: 2026-10-10 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a09c3e7b1f42'
down_revision: Union[str, Sequence[str], None] = 'd07a4c1e5c0e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Enum types are managed explicitly (create with checkfirst, create_type=False on
# columns, drop on downgrade) — same convention as the earlier migrations.
recap_status = postgresql.ENUM(
    'pending', 'ready', 'failed', name='recap_status', create_type=False,
)


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    recap_status.create(bind, checkfirst=True)

    op.create_table(
        'character_recaps',
        sa.Column('session_id', sa.Uuid(), nullable=False),
        sa.Column('character_id', sa.Uuid(), nullable=False),
        sa.Column('status', recap_status, nullable=False),
        sa.Column('body', sa.String(), nullable=False),
        sa.Column('error', sa.String(), nullable=False),
        sa.Column('model', sa.String(), nullable=False),
        sa.Column('shared_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'attempted_at', sa.DateTime(timezone=True),
            server_default=sa.text('now()'), nullable=False,
        ),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column(
            'created_at', sa.DateTime(timezone=True),
            server_default=sa.text('now()'), nullable=False,
        ),
        sa.ForeignKeyConstraint(['character_id'], ['characters.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['session_id'], ['game_sessions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('session_id', 'character_id'),
    )
    op.create_index(
        op.f('ix_character_recaps_session_id'), 'character_recaps', ['session_id'],
    )
    op.create_index(
        op.f('ix_character_recaps_character_id'), 'character_recaps', ['character_id'],
    )

    op.create_table(
        'recap_flags',
        sa.Column('recap_id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('quote', sa.String(), nullable=False),
        sa.Column('note', sa.String(), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column(
            'created_at', sa.DateTime(timezone=True),
            server_default=sa.text('now()'), nullable=False,
        ),
        sa.ForeignKeyConstraint(['recap_id'], ['character_recaps.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_recap_flags_recap_id'), 'recap_flags', ['recap_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_recap_flags_recap_id'), table_name='recap_flags')
    op.drop_table('recap_flags')
    op.drop_index(op.f('ix_character_recaps_character_id'), table_name='character_recaps')
    op.drop_index(op.f('ix_character_recaps_session_id'), table_name='character_recaps')
    op.drop_table('character_recaps')
    recap_status.drop(op.get_bind(), checkfirst=True)
