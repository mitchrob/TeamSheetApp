import hashlib
import hmac
import sqlite3
import time

from app.extensions import db
from app.models import Match


def _headers(secret, *, timestamp=None, run_id="test-run-1", signature=None):
    timestamp_text = str(timestamp if timestamp is not None else int(time.time()))
    message = f"{timestamp_text}\n{run_id}\nPOST\n/internal/database-backup\n".encode()
    signed = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    return {
        "X-Backup-Run-ID": run_id,
        "X-Backup-Timestamp": timestamp_text,
        "X-Backup-Signature": signature or f"sha256={signed}",
    }


def test_database_backup_requires_configuration(client, app):
    app.config["DATABASE_BACKUP_SECRET"] = None

    response = client.post("/internal/database-backup")

    assert response.status_code == 503


def test_database_backup_rejects_invalid_and_expired_authentication(client, app):
    secret = app.config["DATABASE_BACKUP_SECRET"]

    invalid = client.post(
        "/internal/database-backup",
        headers=_headers(secret, signature="sha256=invalid"),
    )
    expired = client.post(
        "/internal/database-backup",
        headers=_headers(secret, timestamp=int(time.time()) - 301, run_id="expired-run"),
    )

    assert invalid.status_code == 401
    assert expired.status_code == 401


def test_database_backup_returns_verified_sqlite_snapshot(client, app, match_factory, tmp_path):
    match_factory(opposition="Backup RFC")
    secret = app.config["DATABASE_BACKUP_SECRET"]

    response = client.post("/internal/database-backup", headers=_headers(secret))

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store, max-age=0"
    assert response.headers["X-Backup-SHA256"] == hashlib.sha256(response.data).hexdigest()

    snapshot = response.data
    response.close()
    snapshot_path = tmp_path / "snapshot.db"
    snapshot_path.write_bytes(snapshot)
    connection = sqlite3.connect(snapshot_path)
    try:
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("SELECT COUNT(*) FROM match").fetchone() == (1,)
        assert connection.execute("SELECT opposition FROM match").fetchone() == ("Backup RFC",)
    finally:
        connection.close()

    with app.app_context():
        assert db.session.query(Match).count() == 1


def test_database_backup_rejects_request_body(client, app):
    response = client.post(
        "/internal/database-backup",
        data=b"unexpected",
        headers=_headers(app.config["DATABASE_BACKUP_SECRET"]),
    )

    assert response.status_code == 400
