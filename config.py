import os
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


class Config:
    ENVIRONMENT = os.environ.get("APP_ENV", "development").lower()
    SECRET_KEY = os.environ.get("SECRET_KEY")
    ADMIN_USER = os.environ.get("ADMIN_USER")
    ADMIN_PASSWORD_HASH = os.environ.get("ADMIN_PASSWORD_HASH")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", f"sqlite:///{BASE_DIR / 'app.db'}")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_SQUAD_SIZE = 23
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = ENVIRONMENT == "production"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    WTF_CSRF_TIME_LIMIT = 3600
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
    RFU_SYNC_SECRET = os.environ.get("RFU_SYNC_SECRET")
    RFU_TEAM_ID = os.environ.get("RFU_TEAM_ID", "9045")
    RFU_GITHUB_WORKFLOW_URL = os.environ.get("RFU_GITHUB_WORKFLOW_URL", "")
    RFU_SYNC_MAX_BODY_BYTES = 524_288
    RFU_SYNC_MAX_MATCHES = 100
    RFU_SYNC_MAX_AGE_SECONDS = 300
    RFU_SYNC_STALE_HOURS = 36
    DATABASE_BACKUP_SECRET = os.environ.get("DATABASE_BACKUP_SECRET")
    DATABASE_BACKUP_MAX_AGE_SECONDS = 300
    DATABASE_BACKUP_MAX_BYTES = 134_217_728


class TestConfig(Config):
    TESTING = True
    ENVIRONMENT = "test"
    SECRET_KEY = "test-secret"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False
