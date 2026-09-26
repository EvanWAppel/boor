"""initial schema: users, campaigns, memberships, invites

Revision ID: cbc5dcf80b3d
Revises:
Create Date: 2026-08-15 15:45:48.772644

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'cbc5dcf80b3d'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The two enum types are shared across tables (membership_role by both invites and
# memberships), so we manage them explicitly: create once (checkfirst) and drop on
# downgrade. create_type=False keeps create_table from re-emitting CREATE TYPE,
# which would otherwise fail on the second table — and leaving the types behind on
# downgrade would break a later re-upgrade.
membership_role = postgresql.ENUM(
    'dm', 'player', name='membership_role', create_type=False
)
invite_status = postgresql.ENUM(
    'pending', 'accepted', 'revoked', 'expired', name='invite_status', create_type=False
)


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    membership_role.create(bind, checkfirst=True)
    invite_status.create(bind, checkfirst=True)

    op.create_table('users',
    sa.Column('clerk_user_id', sa.String(length=255), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('display_name', sa.String(length=120), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_clerk_user_id'), 'users', ['clerk_user_id'], unique=True)
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_table('campaigns',
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('owner_id', sa.Uuid(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_campaigns_owner_id'), 'campaigns', ['owner_id'], unique=False)
    op.create_table('invites',
    sa.Column('campaign_id', sa.Uuid(), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('token', sa.String(length=64), nullable=False),
    sa.Column('role', membership_role, nullable=False),
    sa.Column('status', invite_status, nullable=False),
    sa.Column('invited_by_id', sa.Uuid(), nullable=False),
    sa.Column('accepted_by_id', sa.Uuid(), nullable=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['accepted_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['invited_by_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_invites_campaign_id'), 'invites', ['campaign_id'], unique=False)
    op.create_index(op.f('ix_invites_email'), 'invites', ['email'], unique=False)
    op.create_index(op.f('ix_invites_token'), 'invites', ['token'], unique=True)
    op.create_table('memberships',
    sa.Column('campaign_id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('role', membership_role, nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('campaign_id', 'user_id', name='uq_membership_campaign_user')
    )
    op.create_index(op.f('ix_memberships_campaign_id'), 'memberships', ['campaign_id'], unique=False)
    op.create_index(op.f('ix_memberships_user_id'), 'memberships', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_memberships_user_id'), table_name='memberships')
    op.drop_index(op.f('ix_memberships_campaign_id'), table_name='memberships')
    op.drop_table('memberships')
    op.drop_index(op.f('ix_invites_token'), table_name='invites')
    op.drop_index(op.f('ix_invites_email'), table_name='invites')
    op.drop_index(op.f('ix_invites_campaign_id'), table_name='invites')
    op.drop_table('invites')
    op.drop_index(op.f('ix_campaigns_owner_id'), table_name='campaigns')
    op.drop_table('campaigns')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_index(op.f('ix_users_clerk_user_id'), table_name='users')
    op.drop_table('users')

    bind = op.get_bind()
    invite_status.drop(bind, checkfirst=True)
    membership_role.drop(bind, checkfirst=True)
