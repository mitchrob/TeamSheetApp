"""Add RFU fixture synchronization metadata and staging.

Revision ID: 0003_rfu_fixture_sync
Revises: 0002_admin_users_and_audit
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_rfu_fixture_sync"
down_revision = "0002_admin_users_and_audit"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("match") as batch:
        batch.add_column(sa.Column("source_provider", sa.String(30)))
        batch.add_column(sa.Column("external_match_id", sa.String(40)))
        batch.add_column(sa.Column("source_url", sa.String(500)))
        batch.add_column(sa.Column("fixture_status", sa.String(20), nullable=False, server_default="unknown"))
        batch.add_column(sa.Column("source_updated_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("last_synced_at", sa.DateTime(timezone=True)))
        batch.create_check_constraint(
            "ck_match_fixture_status",
            "fixture_status IN ('scheduled', 'completed', 'postponed', 'cancelled', 'unknown')",
        )
        batch.create_unique_constraint(
            "uq_match_source_external_id", ["source_provider", "external_match_id"]
        )
    op.create_index("ix_match_source_provider", "match", ["source_provider"])
    op.create_index("ix_match_fixture_status", "match", ["fixture_status"])

    op.create_table(
        "fixture_sync_run",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.String(100), nullable=False),
        sa.Column("season", sa.String(7), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scraped_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unchanged_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("conflict_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("missing_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_summary", sa.String(255)),
        sa.CheckConstraint(
            "status IN ('pending_review', 'applied', 'superseded', 'failed')",
            name="ck_fixture_sync_run_status",
        ),
    )
    op.create_index("ix_fixture_sync_run_run_id", "fixture_sync_run", ["run_id"], unique=True)
    op.create_index("ix_fixture_sync_run_season", "fixture_sync_run", ["season"])
    op.create_index("ix_fixture_sync_run_status", "fixture_sync_run", ["status"])
    op.create_index("ix_fixture_sync_run_received_at", "fixture_sync_run", ["received_at"])

    op.create_table(
        "fixture_import_item",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "sync_run_id",
            sa.Integer(),
            sa.ForeignKey("fixture_sync_run.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_match_id", sa.String(40), nullable=False),
        sa.Column("season", sa.String(7), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("league", sa.String(100)),
        sa.Column("opposition", sa.String(100), nullable=False),
        sa.Column("location", sa.String(50), nullable=False),
        sa.Column("result", sa.String(10)),
        sa.Column("guildford_points", sa.Integer()),
        sa.Column("opposition_points", sa.Integer()),
        sa.Column("fixture_status", sa.String(20), nullable=False),
        sa.Column("source_url", sa.String(500), nullable=False),
        sa.Column("proposed_action", sa.String(20), nullable=False),
        sa.Column("matched_match_id", sa.Integer(), sa.ForeignKey("match.id", ondelete="SET NULL")),
        sa.Column("issue", sa.String(255)),
        sa.UniqueConstraint(
            "sync_run_id", "external_match_id", name="uq_fixture_import_item_run_external"
        ),
        sa.CheckConstraint(
            "proposed_action IN ('create', 'link', 'conflict')",
            name="ck_fixture_import_item_action",
        ),
    )
    op.create_index("ix_fixture_import_item_sync_run_id", "fixture_import_item", ["sync_run_id"])


def downgrade():
    op.drop_table("fixture_import_item")
    op.drop_table("fixture_sync_run")
    op.drop_index("ix_match_fixture_status", table_name="match")
    op.drop_index("ix_match_source_provider", table_name="match")
    with op.batch_alter_table("match") as batch:
        batch.drop_constraint("uq_match_source_external_id", type_="unique")
        batch.drop_constraint("ck_match_fixture_status", type_="check")
        batch.drop_column("last_synced_at")
        batch.drop_column("source_updated_at")
        batch.drop_column("fixture_status")
        batch.drop_column("source_url")
        batch.drop_column("external_match_id")
        batch.drop_column("source_provider")
