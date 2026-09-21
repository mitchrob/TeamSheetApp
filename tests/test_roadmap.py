from datetime import date

from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models import AdminUser, AuditEvent, Match
from app.utils import normalize_username


def _account(username="Mitch Admin", password="a-strong-password"):
    user = AdminUser(
        username=username,
        normalized_username=normalize_username(username),
        password_hash=generate_password_hash(password),
        must_change_password=False,
    )
    db.session.add(user)
    db.session.commit()
    return user


def _login_named(client, username="Mitch Admin", password="a-strong-password"):
    return client.post("/login", data={"username": username, "password": password})


def test_first_database_admin_replaces_environment_login(client, login):
    login()
    response = client.post("/admin/users", data={"username": "First Admin"})
    assert response.status_code == 302
    user = AdminUser.query.one()
    assert user.must_change_password is True
    with client.session_transaction() as session:
        assert session["admin_user_id"] == user.id
        assert "legacy_admin" not in session
    page = client.get("/admin/password")
    assert page.status_code == 200
    assert b"Temporary password for First Admin" in page.data


def test_database_accounts_disable_environment_fallback(client):
    _account()
    response = client.post("/login", data={"username": "admin", "password": "correct-password"})
    assert b"Invalid credentials" in response.data


def test_temporary_password_requires_change(client):
    user = _account(password="temporary-password")
    user.must_change_password = True
    db.session.commit()
    response = _login_named(client, password="temporary-password")
    assert response.location.endswith("/admin/password")
    assert client.get("/add").location.endswith("/admin/password")
    changed = client.post(
        "/admin/password",
        data={
            "current_password": "temporary-password",
            "new_password": "new-password-123",
            "confirmation": "new-password-123",
        },
    )
    assert changed.location.endswith("/add")
    assert user.must_change_password is False


def test_inactive_user_cannot_login(client):
    user = _account()
    user.is_active = False
    db.session.commit()
    response = _login_named(client)
    assert b"Invalid credentials" in response.data


def test_cannot_deactivate_current_admin(client):
    user = _account()
    _login_named(client)
    response = client.post(f"/admin/users/{user.id}/toggle", follow_redirects=True)
    assert b"cannot deactivate your own account" in response.data
    assert user.is_active is True


def test_match_mutations_are_attributed(client):
    user = _account()
    _login_named(client)
    response = client.post(
        "/add",
        data={
            "league": "League",
            "season": "2026-27",
            "date": "2026-09-12",
            "opposition": "Audit Rivals",
            "location": "Home",
            "guildford_points": "12",
            "opposition_points": "10",
            "player1": "Audit Player",
        },
    )
    assert response.status_code == 302
    event = AuditEvent.query.filter_by(action="create", entity_type="match").one()
    assert event.actor_user_id == user.id
    assert "Audit Rivals" in event.description


def test_recent_lineups_returns_ordered_23_slots(client, login, match_factory, appearance_factory):
    match = match_factory(opposition="Copy Source")
    appearance_factory(match, "Prop Player", 1)
    appearance_factory(match, "Bench Player", 23)
    login()
    response = client.get("/admin/recent-lineups")
    payload = response.get_json()
    assert len(payload) == 1
    assert len(payload[0]["players"]) == 23
    assert payload[0]["players"][0] == "Prop Player"
    assert payload[0]["players"][22] == "Bench Player"


def test_new_match_remembers_context_but_not_match_or_lineup(client, login, match_factory, appearance_factory):
    match = match_factory(season="2025-26", opposition="Do Not Copy")
    match.league = "Remembered League"
    match.location = "Away"
    db.session.commit()
    appearance_factory(match, "Do Not Prefill", 1)
    login()
    page = client.get("/add")
    assert b'value="Remembered League"' in page.data
    assert b'value="2025-26"' in page.data
    assert b'value="Away"' in page.data
    assert b'value="Do Not Copy"' not in page.data
    assert b'value="Do Not Prefill"' not in page.data


def test_csv_exports_are_authorized_and_canonical(client, login, match_factory, appearance_factory):
    match = match_factory(result="Win", opposition="Comma, Rivals")
    appearance_factory(match, "CSV Player", 1)
    assert client.get("/admin/export/matches.csv").status_code == 302
    login()
    matches = client.get("/admin/export/matches.csv")
    appearances = client.get("/admin/export/appearances.csv")
    players = client.get("/admin/export/players.csv")
    assert matches.status_code == appearances.status_code == players.status_code == 200
    assert matches.data.startswith(b"id,date,season")
    assert b'"Comma, Rivals"' in matches.data
    assert b"CSV Player" in appearances.data
    assert b"appearances,starts,replacements" in players.data


def test_data_quality_locates_incomplete_match(client, login, match_factory):
    match_factory(guildford_points=None, opposition_points=None, opposition="Needs Work")
    login()
    page = client.get("/admin/data-quality?completeness=score")
    assert page.status_code == 200
    assert b"Needs Work" in page.data
    assert b"Missing score" in page.data


def test_public_match_and_player_filters(client, match_factory, appearance_factory):
    first = match_factory(season="2025-26", opposition="North Club")
    second = Match(
        league="League", season="2024-25", date=date(2025, 1, 1), opposition="South Club",
        location="Away", result="Loss", guildford_points=5, opposition_points=10,
    )
    db.session.add(second)
    db.session.commit()
    appearance_factory(first, "Filter Player", 1)
    appearance_factory(second, "Filter Player", 16)
    matches = client.get("/data?season=2025-26&opponent=North")
    assert b"North Club" in matches.data and b"South Club" not in matches.data
    players = client.get("/stats?season=2024-25&type=replacement")
    assert b"Filter Player" in players.data


def test_cli_bootstrap_and_emergency_reset(app):
    runner = app.test_cli_runner()
    result = runner.invoke(args=["users", "bootstrap", "--username", "CLI Admin"], input="long-cli-password\nlong-cli-password\n")
    assert result.exit_code == 0
    assert AdminUser.query.filter_by(normalized_username="cli admin").one()
    reset = runner.invoke(args=["users", "reset-password", "CLI Admin"], input="replacement-pass\nreplacement-pass\n")
    assert reset.exit_code == 0
    assert AuditEvent.query.filter_by(action="emergency_password_reset").one()
