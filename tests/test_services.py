from datetime import date

from app.extensions import db
from app.services import (
    _collect_seasons,
    canonicalize_season,
    compute_season_stats,
    get_player_stats,
    normalize_result,
)


def test_season_and_result_normalization():
    assert canonicalize_season("2025-2026") == "2025-26"
    assert canonicalize_season("2025/26") == "2025-26"
    assert canonicalize_season("2099-00") == "2099-00"
    assert canonicalize_season("summer") is None
    assert normalize_result("Lose") == "Loss"
    assert normalize_result("Loss", 30, 20) == "Win"


def test_season_order_is_deterministic(app, match_factory):
    match_factory(season="2023-24", match_date=date(2023, 9, 1), opposition="A")
    match_factory(season="2025-26", match_date=date(2025, 9, 1), opposition="B")
    match_factory(season="2024-25", match_date=date(2024, 9, 1), opposition="C")
    assert _collect_seasons() == ["2025-26", "2024-25", "2023-24"]


def test_debut_uses_earliest_match_date(app, match_factory, appearance_factory):
    later = match_factory(season="2023-24", match_date=date(2023, 9, 1), opposition="Later")
    earlier = match_factory(season="2024-25", match_date=date(2020, 9, 1), opposition="Earlier")
    appearance_factory(later, "Date Ordered Player")
    appearance_factory(earlier, "Date Ordered Player")
    earlier_stats = compute_season_stats("2024-25")
    later_stats = compute_season_stats("2023-24")
    assert earlier_stats["debut_count"] == 1
    assert earlier_stats["debutants"] == ["Date Ordered Player"]
    assert later_stats["debut_count"] == 0
    assert later_stats["debutants"] == []


def test_missing_scores_are_excluded_from_averages(app, match_factory):
    match_factory(guildford_points=20, opposition_points=10, opposition="Scored")
    match_factory(
        match_date=date(2025, 9, 8),
        guildford_points=None,
        opposition_points=None,
        result=None,
        opposition="Unscored",
    )
    stats = compute_season_stats("2025-26")
    assert stats["scored_matches"] == 1
    assert stats["avg_points_for"] == 20
    assert stats["avg_points_against"] == 10


def test_player_stats_count_distinct_seasons(app, match_factory, appearance_factory):
    first = match_factory(season="2024-25", match_date=date(2025, 1, 1), opposition="First")
    second = match_factory(season="2025-26", match_date=date(2025, 9, 1), opposition="Second")
    third = match_factory(season="2025-26", match_date=date(2025, 9, 8), opposition="Third")
    for match in (first, second, third):
        appearance_factory(match, "Multi Season Player")

    assert get_player_stats("Multi Season Player")["seasons_played"] == 2


def test_player_season_timeline_shows_gaps_and_departure(app, match_factory, appearance_factory):
    before = match_factory(season="2021-22", match_date=date(2021, 9, 4), opposition="Before Debut")
    debut = match_factory(season="2022-23", match_date=date(2022, 9, 3), opposition="Debut")
    second = match_factory(season="2022-23", match_date=date(2022, 9, 10), opposition="Second")
    match_factory(season="2023-24", match_date=date(2023, 9, 2), opposition="Missed")
    comeback = match_factory(season="2024-25", match_date=date(2024, 9, 7), opposition="Comeback")
    match_factory(season="2025-26", match_date=date(2025, 9, 6), opposition="After Leaving")
    match_factory(season="2025-26", match_date=date(2025, 9, 13), opposition="After Leaving Again")
    upcoming = match_factory(season="2026-27", match_date=date(2026, 9, 5), opposition="Upcoming")
    upcoming.fixture_status = "scheduled"
    db.session.commit()
    appearance_factory(before, "Someone Else")
    for match in (debut, second, comeback):
        appearance_factory(match, "Timeline Player")

    timeline = get_player_stats("Timeline Player")["by_season"]

    assert [(s["season"], s["count"], s["club_matches"]) for s in timeline] == [
        ("2022-23", 2, 2),
        ("2023-24", 0, 1),
        ("2024-25", 1, 1),
        ("2025-26", 0, 2),
    ]
    assert [s["height_pct"] for s in timeline] == [100.0, 0.0, 50.0, 0.0]
    assert timeline[0]["label"] == "22-23"
