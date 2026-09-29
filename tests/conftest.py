from datetime import date

import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.models import Appearance, Match, Player
from config import TestConfig


class AppTestConfig(TestConfig):
    ADMIN_USER = "admin"
    ADMIN_PASSWORD_HASH = generate_password_hash("correct-password")
    RFU_SYNC_SECRET = "sync-test-secret"
    DATABASE_BACKUP_SECRET = "database-backup-test-secret-32-chars"


@pytest.fixture
def app():
    app = create_app(AppTestConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def login(client):
    def perform(next_url=""):
        return client.post(
            f"/login?next={next_url}",
            data={"username": "admin", "password": "correct-password", "next": next_url},
        )

    return perform


@pytest.fixture
def match_factory(app):
    def create(
        *,
        season="2025-26",
        match_date=date(2025, 9, 1),
        result="Win",
        guildford_points=20,
        opposition_points=10,
        opposition="Opposition",
    ):
        match = Match(
            league="League",
            season=season,
            date=match_date,
            opposition=opposition,
            location="Home",
            result=result,
            guildford_points=guildford_points,
            opposition_points=opposition_points,
        )
        db.session.add(match)
        db.session.commit()
        return match

    return create


@pytest.fixture
def appearance_factory(app):
    def create(match, name, position=1):
        player = Player.query.filter_by(name=name).first() or Player(name=name)
        appearance = Appearance(player=player, match=match, position=position)
        db.session.add(appearance)
        db.session.commit()
        return appearance

    return create
