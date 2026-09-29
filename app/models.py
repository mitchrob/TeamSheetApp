from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, UniqueConstraint

from app.extensions import db


class Player(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    appearances = db.relationship(
        "Appearance", back_populates="player", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint("length(trim(name)) BETWEEN 1 AND 100", name="ck_player_name_length"),
    )


class Match(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    league = db.Column(db.String(100))
    season = db.Column(db.String(7), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False, index=True)
    opposition = db.Column(db.String(100), nullable=False)
    location = db.Column(db.String(50))
    result = db.Column(db.String(10))
    guildford_points = db.Column(db.Integer)
    opposition_points = db.Column(db.Integer)
    source_provider = db.Column(db.String(30), index=True)
    external_match_id = db.Column(db.String(40))
    source_url = db.Column(db.String(500))
    fixture_status = db.Column(db.String(20), nullable=False, default="unknown", index=True)
    source_updated_at = db.Column(db.DateTime(timezone=True))
    last_synced_at = db.Column(db.DateTime(timezone=True))
    appearances = db.relationship(
        "Appearance", back_populates="match", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint("length(trim(season)) = 7", name="ck_match_season_length"),
        CheckConstraint("length(trim(opposition)) BETWEEN 1 AND 100", name="ck_match_opposition_length"),
        CheckConstraint("result IN ('Win', 'Draw', 'Loss') OR result IS NULL", name="ck_match_result"),
        CheckConstraint("guildford_points >= 0 OR guildford_points IS NULL", name="ck_match_guildford_points"),
        CheckConstraint("opposition_points >= 0 OR opposition_points IS NULL", name="ck_match_opposition_points"),
        CheckConstraint(
            "fixture_status IN ('scheduled', 'completed', 'postponed', 'cancelled', 'unknown')",
            name="ck_match_fixture_status",
        ),
        UniqueConstraint("source_provider", "external_match_id", name="uq_match_source_external_id"),
    )


class Appearance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey("player.id", ondelete="CASCADE"), nullable=False)
    match_id = db.Column(db.Integer, db.ForeignKey("match.id", ondelete="CASCADE"), nullable=False)
    position = db.Column(db.Integer, nullable=False)
    player = db.relationship("Player", back_populates="appearances")
    match = db.relationship("Match", back_populates="appearances")

    __table_args__ = (
        UniqueConstraint("player_id", "match_id", name="uq_appearance_player_match"),
        UniqueConstraint("match_id", "position", name="uq_appearance_match_position"),
        CheckConstraint("position BETWEEN 1 AND 23", name="ck_appearance_position"),
    )


def utc_now():
    return datetime.now(timezone.utc)


class AdminUser(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False)
    normalized_username = db.Column(db.String(80), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    must_change_password = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    last_login_at = db.Column(db.DateTime(timezone=True))
    audit_events = db.relationship("AuditEvent", back_populates="actor", lazy="selectin")

    __table_args__ = (
        CheckConstraint("length(trim(username)) BETWEEN 1 AND 80", name="ck_admin_user_username_length"),
    )


class AuditEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    actor_user_id = db.Column(
        db.Integer, db.ForeignKey("admin_user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action = db.Column(db.String(50), nullable=False, index=True)
    entity_type = db.Column(db.String(50), nullable=False)
    entity_id = db.Column(db.String(80))
    description = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, index=True)
    actor = db.relationship("AdminUser", back_populates="audit_events")


class FixtureSyncRun(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    run_id = db.Column(db.String(100), nullable=False, unique=True, index=True)
    season = db.Column(db.String(7), nullable=False, index=True)
    status = db.Column(db.String(30), nullable=False, index=True)
    received_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, index=True)
    scraped_at = db.Column(db.DateTime(timezone=True), nullable=False)
    completed_at = db.Column(db.DateTime(timezone=True))
    created_count = db.Column(db.Integer, nullable=False, default=0)
    updated_count = db.Column(db.Integer, nullable=False, default=0)
    unchanged_count = db.Column(db.Integer, nullable=False, default=0)
    conflict_count = db.Column(db.Integer, nullable=False, default=0)
    missing_count = db.Column(db.Integer, nullable=False, default=0)
    error_summary = db.Column(db.String(255))
    items = db.relationship(
        "FixtureImportItem", back_populates="sync_run", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending_review', 'applied', 'superseded', 'failed')",
            name="ck_fixture_sync_run_status",
        ),
    )


class FixtureImportItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sync_run_id = db.Column(
        db.Integer, db.ForeignKey("fixture_sync_run.id", ondelete="CASCADE"), nullable=False, index=True
    )
    external_match_id = db.Column(db.String(40), nullable=False)
    season = db.Column(db.String(7), nullable=False)
    date = db.Column(db.Date, nullable=False)
    league = db.Column(db.String(100))
    opposition = db.Column(db.String(100), nullable=False)
    location = db.Column(db.String(50), nullable=False)
    result = db.Column(db.String(10))
    guildford_points = db.Column(db.Integer)
    opposition_points = db.Column(db.Integer)
    fixture_status = db.Column(db.String(20), nullable=False)
    source_url = db.Column(db.String(500), nullable=False)
    proposed_action = db.Column(db.String(20), nullable=False)
    matched_match_id = db.Column(db.Integer, db.ForeignKey("match.id", ondelete="SET NULL"))
    issue = db.Column(db.String(255))
    sync_run = db.relationship("FixtureSyncRun", back_populates="items")
    matched_match = db.relationship("Match")

    __table_args__ = (
        UniqueConstraint("sync_run_id", "external_match_id", name="uq_fixture_import_item_run_external"),
        CheckConstraint(
            "proposed_action IN ('create', 'link', 'conflict')",
            name="ck_fixture_import_item_action",
        ),
    )
