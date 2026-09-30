def test_public_match_page_shows_teamsheet(client, match_factory, appearance_factory):
    match = match_factory(opposition="Old Rivals")
    appearance_factory(match, "Starting Player", position=1)
    appearance_factory(match, "Replacement Player", position=23)

    response = client.get(f"/match/{match.id}")

    assert response.status_code == 200
    assert b"Guildford vs Old Rivals" in response.data
    assert b"Starting Player" in response.data
    assert b"Replacement Player" in response.data
    assert b'<span class="shirt-number" aria-hidden="true">16</span>' in response.data
    assert b'<span class="shirt-number" aria-hidden="true">23</span>' in response.data
    assert b"Edit teamsheet" not in response.data


def test_admin_match_page_links_to_edit(client, login, match_factory):
    match = match_factory()
    login()
    response = client.get(f"/match/{match.id}")
    assert response.status_code == 200
    assert f"/edit/{match.id}".encode() in response.data


def test_unknown_match_returns_404(client):
    assert client.get("/match/999999").status_code == 404


def test_player_profile_shows_seasons_played(client, match_factory, appearance_factory):
    match = match_factory(season="2025-26")
    appearance_factory(match, "Profile Player")

    response = client.get("/player?name=Profile%20Player")

    assert response.status_code == 200
    assert b"Seasons played:</strong> 1" in response.data


def test_season_summary_omits_shirt_distribution(client, match_factory, appearance_factory):
    match = match_factory(season="2025-26")
    appearance_factory(match, "Season Player")

    response = client.get("/season?season=2025-26")

    assert response.status_code == 200
    assert b"Player Leaderboard" in response.data
    assert b"Shirt Number Distribution" not in response.data
