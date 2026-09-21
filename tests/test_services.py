from datetime import date

from app.services import _collect_seasons, canonicalize_season, compute_season_stats, normalize_result


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
    assert compute_season_stats("2024-25")["debut_count"] == 1
    assert compute_season_stats("2023-24")["debut_count"] == 0


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
