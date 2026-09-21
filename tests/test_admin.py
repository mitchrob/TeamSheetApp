from app.extensions import db
from app.models import Appearance, AuditEvent, Match, Player


def _valid_match_data(**updates):
    data = {
        "league": "League",
        "season": "2026-27",
        "date": "2026-09-12",
        "opposition": "Rivals",
        "location": "Home",
        "result": "Loss",
        "guildford_points": "22",
        "opposition_points": "20",
        "player1": "Alex Player",
        "player23": "Sam Replacement",
    }
    data.update(updates)
    return data


def test_add_match_derives_result_and_supports_23_players(client, login):
    login()
    response = client.post("/add", data=_valid_match_data())
    assert response.status_code == 302
    match = Match.query.one()
    assert match.result == "Win"
    assert {appearance.position for appearance in match.appearances} == {1, 23}


def test_validation_error_preserves_input(client, login):
    login()
    response = client.post("/add", data=_valid_match_data(season="summer", opposition="Remember Me"))
    assert response.status_code == 400
    assert b"Remember Me" in response.data
    assert b"Season must use the format" in response.data
    assert Match.query.count() == 0


def test_edit_replaces_appearances_and_derives_result(client, login, match_factory, appearance_factory):
    login()
    match = match_factory()
    appearance_factory(match, "Old Player")
    response = client.post(
        f"/edit/{match.id}",
        data=_valid_match_data(
            opposition="Updated Opposition",
            guildford_points="10",
            opposition_points="15",
            player1="New Player",
            player23="",
        ),
    )
    assert response.status_code == 302
    db.session.refresh(match)
    assert match.opposition == "Updated Opposition"
    assert match.result == "Loss"
    assert [appearance.player.name for appearance in match.appearances] == ["New Player"]


def test_duplicate_players_are_case_insensitive(client, login):
    login()
    response = client.post("/add", data=_valid_match_data(player1="Alex Player", player2="alex player"))
    assert response.status_code == 400
    assert b"only appear once" in response.data


def test_public_data_view_hides_admin_controls(client, match_factory):
    match = match_factory()
    response = client.get("/data")
    assert response.status_code == 200
    assert f"/match/{match.id}".encode() in response.data
    assert b">Edit<" not in response.data
    assert b">Delete<" not in response.data


def test_delete_match_removes_appearances_and_records_activity(client, login, match_factory, appearance_factory):
    login()
    match = match_factory(opposition="Delete Me")
    appearance_factory(match, "Delete Test Player", position=1)

    response = client.post(f"/delete/{match.id}", follow_redirects=True)

    assert response.status_code == 200
    assert b"Match deleted successfully" in response.data
    assert db.session.get(Match, match.id) is None
    assert Appearance.query.filter_by(match_id=match.id).count() == 0

    event = AuditEvent.query.filter_by(action="delete", entity_type="match", entity_id=str(match.id)).one()
    assert "Delete Me" in event.description


def test_merge_removes_same_match_conflict(client, login, match_factory):
    login()
    match = match_factory()
    canonical = Player(name="Correct Name")
    duplicate = Player(name="Correct Nme")
    db.session.add_all([canonical, duplicate])
    db.session.flush()
    db.session.add_all(
        [
            Appearance(player=canonical, match=match, position=1),
            Appearance(player=duplicate, match=match, position=2),
        ]
    )
    db.session.commit()

    response = client.post(
        "/merge",
        data={"names_to_merge": ["Correct Name", "Correct Nme"], "canonical_name": "Correct Name"},
    )
    assert response.status_code == 302
    assert Player.query.filter_by(name="Correct Nme").first() is None
    assert Appearance.query.filter_by(player_id=canonical.id, match_id=match.id).count() == 1
