from datetime import date

import pytest

from app.rfu_scraper import ScrapeError, canonical_season, current_rfu_season, parse_match_cards


def _card(*, match_id="1290636", home_id="25094", home="Weybridge Vandals", away_id="9045", away="Guildford", scores=None, status_text=""):
    score_html = '<div class="coh-style-comp-versace">VS</div>'
    if scores:
        score_html = (
            f'<a class="coh-style-numeric-score">{scores[0]}</a>'
            '<div class="coh-style-vertical-line"></div>'
            f'<a class="coh-style-numeric-right">{scores[1]}</a>'
        )
    return f"""
    <div class="resultWrapper">
      <div class="coh-style-card-left-date">Saturday, 26 Sep 2026</div>
      <a class="coh-style-sub-header-right">Regional 2 South Central</a>
      <div class="coh-style-hometeam"><a href="/fixtures-and-results/search-results?team={home_id}">{home}</a></div>
      <div class="fnr-scores">{score_html}</div>
      <div class="coh-style-away-team"><a href="/fixtures-and-results/search-results?team={away_id}">{away}</a></div>
      <span>{status_text}</span>
      <a class="c065-match-link" data-match-id="{match_id}" href="/fixtures-and-results/match-centre-community?season=2026-2027&amp;team=9045&amp;matchId={match_id}">Match info</a>
    </div>
    """


def test_current_season_uses_july_boundary():
    assert current_rfu_season(date(2026, 6, 30)) == "2025-2026"
    assert current_rfu_season(date(2026, 7, 1)) == "2026-2027"
    assert canonical_season("2026-2027") == "2026-27"


def test_parser_maps_away_fixture_and_score():
    [match] = parse_match_cards(
        _card(scores=(18, 25)), rfu_season="2026-2027", default_status="completed"
    )
    assert match["external_match_id"] == "1290636"
    assert match["location"] == "Away"
    assert match["opposition"] == "Weybridge Vandals"
    assert match["guildford_points"] == 25
    assert match["opposition_points"] == 18
    assert match["status"] == "completed"


def test_parser_maps_home_fixture_and_status():
    [match] = parse_match_cards(
        _card(home_id="9045", home="Guildford", away_id="16848", away="Petersfield", status_text="Postponed"),
        rfu_season="2026-2027",
    )
    assert match["location"] == "Home"
    assert match["opposition"] == "Petersfield"
    assert match["status"] == "postponed"


def test_parser_rejects_invalid_team_identity_and_duplicate_conflicts():
    with pytest.raises(ScrapeError, match="exactly once"):
        parse_match_cards(
            _card(home_id="1", away_id="2"), rfu_season="2026-2027"
        )
    with pytest.raises(ScrapeError, match="conflicting data"):
        parse_match_cards(
            _card() + _card(home="Different Opponent"), rfu_season="2026-2027"
        )
