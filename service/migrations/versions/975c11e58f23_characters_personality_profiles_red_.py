"""characters, personality profiles, red lines (DATA-02/04)

Revision ID: 975c11e58f23
Revises: 67d54ac429fa
Create Date: 2026-08-17 19:18:14.411119

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '975c11e58f23'
down_revision: Union[str, Sequence[str], None] = '67d54ac429fa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Enum types are managed explicitly (create with checkfirst, create_type=False on
# columns, drop on downgrade) so downgrades leave no orphaned types behind — same
# convention as the DATA-03 migration. red_line_kind reuses the exact values the
# pure guardrail checker evaluates.
risk_tolerance = postgresql.ENUM(
    'cautious', 'balanced', 'bold', 'reckless', name='risk_tolerance',
    create_type=False,
)
red_line_kind = postgresql.ENUM(
    'no_attacking_allies', 'no_attacking_the_helpless', 'no_targeting_named',
    'no_lethal_self_risk', 'forbid_action_types', name='red_line_kind',
    create_type=False,
)


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    risk_tolerance.create(bind, checkfirst=True)
    red_line_kind.create(bind, checkfirst=True)

    op.create_table('characters',
    sa.Column('campaign_id', sa.Uuid(), nullable=False),
    sa.Column('player_id', sa.Uuid(), nullable=True),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('level', sa.Integer(), nullable=False),
    sa.Column('sheet', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['player_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_characters_campaign_id'), 'characters', ['campaign_id'], unique=False)
    op.create_index(op.f('ix_characters_player_id'), 'characters', ['player_id'], unique=False)
    op.create_table('character_red_lines',
    sa.Column('character_id', sa.Uuid(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('kind', red_line_kind, nullable=False),
    sa.Column('entity_ids', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('action_types', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('note', sa.String(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['character_id'], ['characters.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_character_red_lines_character_id'), 'character_red_lines', ['character_id'], unique=False)
    op.create_table('personality_profiles',
    sa.Column('character_id', sa.Uuid(), nullable=False),
    sa.Column('persona', sa.String(), nullable=False),
    sa.Column('standing_instructions', sa.String(), nullable=False),
    sa.Column('risk_tolerance', risk_tolerance, nullable=False),
    sa.Column('traits', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['character_id'], ['characters.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_personality_profiles_character_id'), 'personality_profiles', ['character_id'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_personality_profiles_character_id'), table_name='personality_profiles')
    op.drop_table('personality_profiles')
    op.drop_index(op.f('ix_character_red_lines_character_id'), table_name='character_red_lines')
    op.drop_table('character_red_lines')
    op.drop_index(op.f('ix_characters_player_id'), table_name='characters')
    op.drop_index(op.f('ix_characters_campaign_id'), table_name='characters')
    op.drop_table('characters')

    bind = op.get_bind()
    red_line_kind.drop(bind, checkfirst=True)
    risk_tolerance.drop(bind, checkfirst=True)
