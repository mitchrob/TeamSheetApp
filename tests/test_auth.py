import re

import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from config import TestConfig


def test_protected_route_redirects_to_login(client):
    response = client.get("/add")
    assert response.status_code == 302
    assert "/login?next=/add" in response.location


def test_login_and_post_logout(client, login):
    response = login()
    assert response.status_code == 302
    assert response.location.endswith("/add")
    assert client.get("/add").status_code == 200
    assert client.get("/logout").status_code == 405
    assert client.post("/logout").status_code == 302
    assert client.get("/add").status_code == 302


def test_external_next_url_is_rejected(client, login):
    response = login("https://example.invalid/phishing")
    assert response.location.endswith("/add")


def test_invalid_credentials_do_not_authenticate(client):
    response = client.post("/login", data={"username": "admin", "password": "wrong"})
    assert response.status_code == 200
    assert b"Invalid credentials" in response.data
    assert client.get("/add").status_code == 302


def test_csrf_rejects_missing_token():
    class CsrfConfig(TestConfig):
        SECRET_KEY = "csrf-test"
        ADMIN_USER = "admin"
        ADMIN_PASSWORD_HASH = generate_password_hash("password")
        SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
        WTF_CSRF_ENABLED = True

    app = create_app(CsrfConfig)
    with app.app_context():
        db.create_all()
    response = app.test_client().post("/login", data={"username": "admin", "password": "password"})
    assert response.status_code == 400
    assert b"Request expired" in response.data


def test_csrf_accepts_valid_login_token():
    class CsrfConfig(TestConfig):
        SECRET_KEY = "csrf-test"
        ADMIN_USER = "admin"
        ADMIN_PASSWORD_HASH = generate_password_hash("password")
        SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
        WTF_CSRF_ENABLED = True
        WTF_CSRF_TIME_LIMIT = 3600

    app = create_app(CsrfConfig)
    client = app.test_client()
    page = client.get("/login")
    token = re.search(rb'name="csrf_token" value="([^"]+)', page.data).group(1).decode()
    response = client.post(
        "/login",
        data={"csrf_token": token, "username": "admin", "password": "password"},
    )
    assert response.status_code == 302
    assert response.location.endswith("/add")


def test_production_requires_security_configuration():
    class UnsafeProductionConfig:
        ENVIRONMENT = "production"
        SECRET_KEY = None
        ADMIN_USER = None
        ADMIN_PASSWORD_HASH = None
        SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
        SQLALCHEMY_TRACK_MODIFICATIONS = False

    with pytest.raises(RuntimeError, match="Missing required production configuration"):
        create_app(UnsafeProductionConfig)


def test_production_can_use_database_admins_without_shared_credentials():
    class DatabaseAdminProductionConfig:
        ENVIRONMENT = "production"
        SECRET_KEY = "a-production-secret"
        ADMIN_USER = None
        ADMIN_PASSWORD_HASH = None
        SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
        SQLALCHEMY_TRACK_MODIFICATIONS = False
        SESSION_COOKIE_SECURE = True
        RATELIMIT_STORAGE_URI = "memory://"

    app = create_app(DatabaseAdminProductionConfig)
    assert app.config["ADMIN_USER"] is None
