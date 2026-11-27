"""Record missing half-scores as zero.

The original spreadsheet import stored a score of 0 as blank, so a few historical
matches have one side's score missing while the other is recorded (for example
Shelford 2018, lost 0-64). Both scores are now always entered together, so a lone
missing score can only mean nil.

Revision ID: 0004_fill_zero_scores
Revises: 0003_rfu_fixture_sync
"""

from alembic import op

revision = "0004_fill_zero_scores"
down_revision = "0003_rfu_fixture_sync"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "UPDATE match SET guildford_points = 0 "
        "WHERE guildford_points IS NULL AND opposition_points IS NOT NULL"
    )
    op.execute(
        "UPDATE match SET opposition_points = 0 "
        "WHERE opposition_points IS NULL AND guildford_points IS NOT NULL"
    )


def downgrade():
    # The original blanks cannot be told apart from genuine zeros, so this is one-way.
    pass
