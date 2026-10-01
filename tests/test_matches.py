from datetime import date


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


def test_season_summary_lists_debutants(client, match_factory, appearance_factory):
    previous = match_factory(season="2024-25", match_date=date(2024, 9, 1), opposition="Previous")
    current = match_factory(season="2025-26", match_date=date(2025, 9, 1), opposition="Current")
    appearance_factory(previous, "Established Player")
    appearance_factory(current, "Established Player")
    appearance_factory(current, "Zoe Debutant", position=2)
    appearance_factory(current, "Amy Debutant", position=3)

    response = client.get("/season?season=2025-26")

    assert response.status_code == 200
    assert b"Debutants list:" in response.data
    assert response.data.index(b"Amy Debutant") < response.data.index(b"Zoe Debutant")
    assert b"Established Player</a>," not in response.data.split(b"Debutants list:", 1)[1].split(b"</p>", 1)[0]
    assert b"/player?name=Amy%20Debutant" in response.data


def test_season_summary_links_leavers_to_player_profiles(client, match_factory, appearance_factory):
    previous = match_factory(season="2024-25", match_date=date(2024, 9, 1), opposition="Previous")
    current = match_factory(season="2025-26", match_date=date(2025, 9, 1), opposition="Current")
    appearance_factory(previous, "Former Player")
    appearance_factory(current, "Current Player")

    response = client.get("/season?season=2025-26")

    assert response.status_code == 200
    leavers = response.data.split(b"Leavers list:", 1)[1].split(b"</p>", 1)[0]
    assert b"/player?name=Former%20Player" in leavers
    assert b">Former Player</a>" in leavers
