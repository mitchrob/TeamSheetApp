"""Create or harden the teamsheet schema.

Revision ID: 0001_harden_schema
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision = "0001_harden_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if not {"player", "match", "appearance"}.issubset(tables):
        _create_schema()
        return

    op.execute("UPDATE \"match\" SET season = substr(season, 1, 4) || '-' || substr(season, -2, 2) WHERE length(season) = 9")
    op.execute("UPDATE \"match\" SET season = '0000-01' WHERE season IS NULL OR length(trim(season)) != 7")
    op.execute("UPDATE \"match\" SET opposition = 'Unknown' WHERE opposition IS NULL OR trim(opposition) = ''")
    op.execute(
        """
        UPDATE "match" SET result = CASE
          WHEN guildford_points IS NOT NULL AND opposition_points IS NOT NULL AND guildford_points > opposition_points THEN 'Win'
          WHEN guildford_points IS NOT NULL AND opposition_points IS NOT NULL AND guildford_points < opposition_points THEN 'Loss'
          WHEN guildford_points IS NOT NULL AND opposition_points IS NOT NULL AND guildford_points = opposition_points THEN 'Draw'
          WHEN lower(trim(coalesce(result, ''))) IN ('w', 'win', 'won') THEN 'Win'
          WHEN lower(trim(coalesce(result, ''))) IN ('d', 'draw') THEN 'Draw'
          WHEN lower(trim(coalesce(result, ''))) IN ('l', 'lose', 'loss', 'lost') THEN 'Loss'
          ELSE NULL END
        """
    )
    op.execute(
        "DELETE FROM appearance WHERE id NOT IN (SELECT min(id) FROM appearance GROUP BY player_id, match_id)"
    )
    op.execute(
        "DELETE FROM appearance WHERE id NOT IN (SELECT min(id) FROM appearance GROUP BY match_id, position)"
    )

    with op.batch_alter_table("player") as batch:
        batch.create_check_constraint("ck_player_name_length", "length(trim(name)) BETWEEN 1 AND 100")
    with op.batch_alter_table("match") as batch:
        batch.alter_column("season", existing_type=sa.String(20), type_=sa.String(7), nullable=False)
        batch.alter_column("opposition", existing_type=sa.String(100), nullable=False)
        batch.alter_column("result", existing_type=sa.String(20), type_=sa.String(10))
        batch.create_check_constraint("ck_match_season_length", "length(trim(season)) = 7")
        batch.create_check_constraint("ck_match_opposition_length", "length(trim(opposition)) BETWEEN 1 AND 100")
        batch.create_check_constraint("ck_match_result", "result IN ('Win', 'Draw', 'Loss') OR result IS NULL")
        batch.create_check_constraint("ck_match_guildford_points", "guildford_points >= 0 OR guildford_points IS NULL")
        batch.create_check_constraint("ck_match_opposition_points", "opposition_points >= 0 OR opposition_points IS NULL")
    op.create_index("ix_match_season", "match", ["season"], unique=False)
    op.create_index("ix_match_date", "match", ["date"], unique=False)
    naming_convention = {
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    }
    with op.batch_alter_table(
        "appearance", recreate="always", naming_convention=naming_convention
    ) as batch:
        batch.drop_constraint("fk_appearance_player_id_player", type_="foreignkey")
        batch.drop_constraint("fk_appearance_match_id_match", type_="foreignkey")
        batch.create_foreign_key(
            "fk_appearance_player_id_player",
            "player",
            ["player_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch.create_foreign_key(
            "fk_appearance_match_id_match",
            "match",
            ["match_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch.create_unique_constraint("uq_appearance_player_match", ["player_id", "match_id"])
        batch.create_unique_constraint("uq_appearance_match_position", ["match_id", "position"])
        batch.create_check_constraint("ck_appearance_position", "position BETWEEN 1 AND 23")


def _create_schema():
    op.create_table(
        "player",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.CheckConstraint("length(trim(name)) BETWEEN 1 AND 100", name="ck_player_name_length"),
    )
    op.create_table(
        "match",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("league", sa.String(100)),
        sa.Column("season", sa.String(7), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("opposition", sa.String(100), nullable=False),
        sa.Column("location", sa.String(50)),
        sa.Column("result", sa.String(10)),
        sa.Column("guildford_points", sa.Integer()),
        sa.Column("opposition_points", sa.Integer()),
        sa.CheckConstraint("length(trim(season)) = 7", name="ck_match_season_length"),
        sa.CheckConstraint("length(trim(opposition)) BETWEEN 1 AND 100", name="ck_match_opposition_length"),
        sa.CheckConstraint("result IN ('Win', 'Draw', 'Loss') OR result IS NULL", name="ck_match_result"),
        sa.CheckConstraint("guildford_points >= 0 OR guildford_points IS NULL", name="ck_match_guildford_points"),
        sa.CheckConstraint("opposition_points >= 0 OR opposition_points IS NULL", name="ck_match_opposition_points"),
    )
    op.create_index("ix_match_season", "match", ["season"])
    op.create_index("ix_match_date", "match", ["date"])
    op.create_table(
        "appearance",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("player.id", ondelete="CASCADE"), nullable=False),
        sa.Column("match_id", sa.Integer(), sa.ForeignKey("match.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.UniqueConstraint("player_id", "match_id", name="uq_appearance_player_match"),
        sa.UniqueConstraint("match_id", "position", name="uq_appearance_match_position"),
        sa.CheckConstraint("position BETWEEN 1 AND 23", name="ck_appearance_position"),
    )


def downgrade():
    # This initial migration intentionally keeps application data and only relaxes added constraints.
    with op.batch_alter_table("appearance") as batch:
        batch.drop_constraint("ck_appearance_position", type_="check")
        batch.drop_constraint("uq_appearance_match_position", type_="unique")
        batch.drop_constraint("uq_appearance_player_match", type_="unique")
    op.drop_index("ix_match_date", table_name="match")
    op.drop_index("ix_match_season", table_name="match")
