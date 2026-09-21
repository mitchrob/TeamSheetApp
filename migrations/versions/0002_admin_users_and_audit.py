"""Add named administrators and append-only activity history.

Revision ID: 0002_admin_users_and_audit
Revises: 0001_harden_schema
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_admin_users_and_audit"
down_revision = "0001_harden_schema"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "admin_user",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(80), nullable=False),
        sa.Column("normalized_username", sa.String(80), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("length(trim(username)) BETWEEN 1 AND 80", name="ck_admin_user_username_length"),
    )
    op.create_index("ix_admin_user_normalized_username", "admin_user", ["normalized_username"], unique=True)
    op.create_table(
        "audit_event",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("admin_user.id", ondelete="SET NULL")),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", sa.String(80)),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_event_actor_user_id", "audit_event", ["actor_user_id"])
    op.create_index("ix_audit_event_action", "audit_event", ["action"])
    op.create_index("ix_audit_event_created_at", "audit_event", ["created_at"])


def downgrade():
    op.drop_table("audit_event")
    op.drop_index("ix_admin_user_normalized_username", table_name="admin_user")
    op.drop_table("admin_user")
