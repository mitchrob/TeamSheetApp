import hashlib
import hmac
import json
import time
from datetime import date, datetime, timezone

from app.extensions import db
from app.models import Appearance, AuditEvent, FixtureSyncRun, Match
from app.services import compute_season_stats


def _snapshot(*, opposition="Weybridge Vandals", score=None, status="scheduled", match_id="1290636"):
    return {
        "source": "rfu-page",
        "season": "2026-27",
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "matches": [
            {
                "external_match_id": match_id,
                "season": "2026-27",
                "date": "2026-09-26",
                "league": "Regional 2 South Central",
                "opposition": opposition,
                "location": "Away",
                "guildford_points": score[0] if score else None,
                "opposition_points": score[1] if score else None,
                "status": status,
                "source_url": f"https://www.englandrugby.com/fixtures-and-results/match-centre-community?season=2026-2027&team=9045&matchId={match_id}",
            }
        ],
    }


def _post_snapshot(client, payload, *, run_id="100-1", timestamp=None, secret="sync-test-secret"):
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    timestamp = str(timestamp or int(time.time()))
    message = f"{timestamp}\n{run_id}\n".encode() + body
    signature = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    return client.post(
        "/internal/rfu-sync",
        data=body,
        content_type="application/json",
        headers={
            "X-RFU-Timestamp": timestamp,
            "X-RFU-Run-ID": run_id,
            "X-RFU-Signature": signature,
        },
    )


def test_first_snapshot_is_staged_then_approved(client, login, app):
    response = _post_snapshot(client, _snapshot())
    assert response.status_code == 202
    run = FixtureSyncRun.query.one()
    assert run.status == "pending_review"
    assert Match.query.count() == 0

    login()
    item = run.items[0]
    review = client.get("/admin/fixtures")
    assert review.status_code == 200
    assert b"Review the first import" in review.data
    response = client.post(f"/admin/fixtures/{run.id}/approve", data={f"item_{item.id}": "create"})
    assert response.status_code == 302
    match = Match.query.one()
    assert match.external_match_id == "1290636"
    assert match.fixture_status == "scheduled"
    assert AuditEvent.query.filter_by(action="approve", entity_type="fixture_sync_run").count() == 1
    dashboard = client.get("/admin/fixtures")
    assert dashboard.status_code == 200
    assert b"Weybridge Vandals" in dashboard.data


def test_first_snapshot_suggests_existing_match_link(client, login, match_factory):
    manual = match_factory(
        season="2026-27",
        match_date=date(2026, 9, 26),
        opposition="Weybridge Vandals",
        guildford_points=None,
        opposition_points=None,
        result=None,
    )
    manual.location = "Away"
    db.session.commit()
    _post_snapshot(client, _snapshot())
    run = FixtureSyncRun.query.one()
    assert run.items[0].matched_match_id == manual.id

    login()
    client.post(f"/admin/fixtures/{run.id}/approve", data={})
    assert Match.query.count() == 1
    assert db.session.get(Match, manual.id).external_match_id == "1290636"


def test_later_snapshot_updates_result_without_appearances(client, login, match_factory, appearance_factory):
    _post_snapshot(client, _snapshot(), run_id="initial")
    run = FixtureSyncRun.query.one()
    login()
    client.post(f"/admin/fixtures/{run.id}/approve", data={f"item_{run.items[0].id}": "create"})
    match = Match.query.one()
    appearance_factory(match, "Preserved Player", position=1)

    response = _post_snapshot(
        client, _snapshot(score=(24, 20), status="completed"), run_id="second"
    )
    assert response.status_code == 200
    db.session.refresh(match)
    assert match.result == "Win"
    assert match.guildford_points == 24
    assert Appearance.query.filter_by(match_id=match.id).count() == 1
    assert response.get_json()["updated"] == 1

    response = _post_snapshot(
        client, _snapshot(score=(24, 20), status="completed"), run_id="third"
    )
    assert response.get_json()["unchanged"] == 1
    assert Match.query.count() == 1


def test_sync_rejects_bad_signature_stale_request_and_replay(client):
    bad = _post_snapshot(client, _snapshot(), secret="wrong")
    assert bad.status_code == 401
    stale = _post_snapshot(client, _snapshot(), run_id="stale", timestamp=int(time.time()) - 600)
    assert stale.status_code == 401
    assert _post_snapshot(client, _snapshot(), run_id="once").status_code == 202
    assert _post_snapshot(client, _snapshot(), run_id="once").status_code == 409


def test_invalid_snapshot_is_atomic(client):
    payload = _snapshot()
    payload["matches"].append({**payload["matches"][0], "opposition": "Duplicate"})
    response = _post_snapshot(client, payload)
    assert response.status_code == 400
    assert Match.query.count() == 0
    assert FixtureSyncRun.query.count() == 0


def test_imported_fields_are_locked_but_teamsheet_is_editable(client, login):
    _post_snapshot(client, _snapshot(), run_id="initial")
    run = FixtureSyncRun.query.one()
    login()
    client.post(f"/admin/fixtures/{run.id}/approve", data={f"item_{run.items[0].id}": "create"})
    match = Match.query.one()
    response = client.post(
        f"/edit/{match.id}",
        data={
            "league": "Forged League",
            "season": "2030-31",
            "date": "2030-01-01",
            "opposition": "Forged Opposition",
            "location": "Home",
            "result": "Win",
            "guildford_points": "99",
            "opposition_points": "0",
            "player1": "New Player",
        },
    )
    assert response.status_code == 302
    db.session.refresh(match)
    assert match.opposition == "Weybridge Vandals"
    assert match.league == "Regional 2 South Central"
    assert match.date == date(2026, 9, 26)
    assert [appearance.player.name for appearance in match.appearances] == ["New Player"]


def test_scheduled_fixtures_are_public_but_excluded_from_stats(client, login):
    _post_snapshot(client, _snapshot(), run_id="initial")
    run = FixtureSyncRun.query.one()
    login()
    client.post(f"/admin/fixtures/{run.id}/approve", data={f"item_{run.items[0].id}": "create"})
    response = client.get("/")
    assert b"Upcoming fixtures" in response.data
    assert b"Weybridge Vandals" in response.data
    assert compute_season_stats("2026-27") is None
