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
    appearances = db.relationship(
        "Appearance", back_populates="match", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint("length(trim(season)) = 7", name="ck_match_season_length"),
        CheckConstraint("length(trim(opposition)) BETWEEN 1 AND 100", name="ck_match_opposition_length"),
        CheckConstraint("result IN ('Win', 'Draw', 'Loss') OR result IS NULL", name="ck_match_result"),
        CheckConstraint("guildford_points >= 0 OR guildford_points IS NULL", name="ck_match_guildford_points"),
        CheckConstraint("opposition_points >= 0 OR opposition_points IS NULL", name="ck_match_opposition_points"),
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
