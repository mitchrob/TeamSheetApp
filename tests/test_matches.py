def test_public_match_page_shows_teamsheet(client, match_factory, appearance_factory):
    match = match_factory(opposition="Old Rivals")
    appearance_factory(match, "Starting Player", position=1)
    appearance_factory(match, "Replacement Player", position=23)

    response = client.get(f"/match/{match.id}")

    assert response.status_code == 200
    assert b"Guildford vs Old Rivals" in response.data
    assert b"Starting Player" in response.data
    assert b"Replacement Player" in response.data
    assert b"Edit teamsheet" not in response.data


def test_admin_match_page_links_to_edit(client, login, match_factory):
    match = match_factory()
    login()
    response = client.get(f"/match/{match.id}")
    assert response.status_code == 200
    assert f"/edit/{match.id}".encode() in response.data


def test_unknown_match_returns_404(client):
    assert client.get("/match/999999").status_code == 404
