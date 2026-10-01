import re
from collections import Counter

from sqlalchemy.orm import joinedload, selectinload
from thefuzz import process as fuzz_process

from app.extensions import db
from app.models import Appearance, Match, Player

SEASON_PATTERN = re.compile(r"^\s*(\d{4})[-/](\d{2}|\d{4})\s*$")


def canonicalize_season(value):
    match = SEASON_PATTERN.match(value or "")
    if not match:
        return None
    start = int(match.group(1))
    end_text = match.group(2)
    end = int(end_text) if len(end_text) == 4 else (start // 100) * 100 + int(end_text)
    if len(end_text) == 2 and end < start:
        end += 100
    if end != start + 1:
        return None
    return f"{start}-{end % 100:02d}"


def normalize_result(value, guildford_points=None, opposition_points=None):
    if guildford_points is not None and opposition_points is not None:
        if guildford_points > opposition_points:
            return "Win"
        if guildford_points < opposition_points:
            return "Loss"
        return "Draw"

    normalized = (value or "").strip().lower()
    mapping = {
        "w": "Win",
        "win": "Win",
        "won": "Win",
        "d": "Draw",
        "draw": "Draw",
        "l": "Loss",
        "lose": "Loss",
        "loss": "Loss",
        "lost": "Loss",
    }
    return mapping.get(normalized)


def get_previous_season(season, all_seasons):
    if season not in all_seasons:
        return None
    index = all_seasons.index(season)
    return all_seasons[index + 1] if index + 1 < len(all_seasons) else None


def _collect_seasons(matches=None):
    if matches is None:
        seasons = [row[0] for row in db.session.query(Match.season).distinct().all() if row[0]]
    else:
        seasons = list({match.season for match in matches if match.season})

    def season_key(season):
        canonical = canonicalize_season(season)
        return (0, -int(canonical[:4]), canonical) if canonical else (1, 0, season.casefold())

    return sorted(seasons, key=season_key)


def compute_season_stats(season):
    season_matches = (
        Match.query.options(selectinload(Match.appearances).joinedload(Appearance.player))
        .filter_by(season=season)
        .all()
    )
    season_matches = [
        match for match in season_matches if match.fixture_status not in {"scheduled", "postponed", "cancelled"}
    ]
    if not season_matches:
        return None

    total_matches = len(season_matches)
    wins = draws = losses = 0
    points_for = points_against = scored_matches = 0
    player_counts = {}

    for match in season_matches:
        result = normalize_result(match.result, match.guildford_points, match.opposition_points)
        if result == "Win":
            wins += 1
        elif result == "Draw":
            draws += 1
        elif result == "Loss":
            losses += 1

        if match.guildford_points is not None and match.opposition_points is not None:
            points_for += match.guildford_points
            points_against += match.opposition_points
            scored_matches += 1

        for appearance in match.appearances:
            name = appearance.player.name
            entry = player_counts.setdefault(name, {"starts": 0, "bench": 0, "total": 0})
            entry["starts" if appearance.position <= 15 else "bench"] += 1
            entry["total"] += 1

    leaderboard = sorted(
        player_counts.items(), key=lambda item: (-item[1]["total"], -item[1]["starts"], item[0].casefold())
    )
    total_players_used = len(player_counts)

    first_appearance_season = {}
    first_appearances = (
        db.session.query(Player.name, Match.season)
        .select_from(Player)
        .join(Appearance)
        .join(Match)
        .filter(Match.fixture_status.notin_(("scheduled", "postponed", "cancelled")))
        .order_by(Match.date.asc(), Match.id.asc())
        .all()
    )
    for name, first_season in first_appearances:
        first_appearance_season.setdefault(name, first_season)

    debutants = sorted(
        (name for name in player_counts if first_appearance_season.get(name) == season),
        key=str.casefold,
    )
    debut_count = len(debutants)
    debut_pct = (debut_count / total_players_used * 100.0) if total_players_used else 0.0

    all_seasons = _collect_seasons()
    previous_season = get_previous_season(season, all_seasons)
    leavers = []
    leavers_pct = 0.0
    if previous_season:
        previous_players = {
            name
            for (name,) in db.session.query(Player.name)
            .join(Appearance)
            .join(Match)
            .filter(Match.season == previous_season)
            .filter(Match.fixture_status.notin_(("scheduled", "postponed", "cancelled")))
            .distinct()
            .all()
        }
        leavers = sorted(previous_players - set(player_counts), key=str.casefold)
        leavers_pct = (len(leavers) / len(previous_players) * 100.0) if previous_players else 0.0

    return {
        "season": season,
        "total_matches": total_matches,
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "win_pct": (wins / total_matches * 100.0) if total_matches else 0.0,
        "points_for": points_for,
        "points_against": points_against,
        "avg_points_for": round(points_for / scored_matches) if scored_matches else 0,
        "avg_points_against": round(points_against / scored_matches) if scored_matches else 0,
        "leaderboard": leaderboard,
        "total_players_used": total_players_used,
        "debutants": debutants,
        "debut_count": debut_count,
        "debut_pct": debut_pct,
        "leavers": leavers,
        "leavers_count": len(leavers),
        "leavers_pct": leavers_pct,
        "match_list": sorted(season_matches, key=lambda match: match.date),
        "available_seasons": all_seasons,
        "previous_season": previous_season,
        "scored_matches": scored_matches,
    }


def get_player_stats(name):
    player = Player.query.filter_by(name=name).first()
    if not player:
        return None

    appearances = (
        Appearance.query.options(joinedload(Appearance.match))
        .filter_by(player_id=player.id)
        .join(Match)
        .filter(Match.fixture_status.notin_(("scheduled", "postponed", "cancelled")))
        .order_by(Match.date.desc())
        .all()
    )
    if not appearances:
        return None

    total = len(appearances)
    seasons_played = len({appearance.match.season for appearance in appearances})
    starts = sum(1 for appearance in appearances if appearance.position <= 15)
    wins = sum(
        1
        for appearance in appearances
        if normalize_result(
            appearance.match.result,
            appearance.match.guildford_points,
            appearance.match.opposition_points,
        )
        == "Win"
    )
    shirt_counts = Counter(appearance.position for appearance in appearances)

    return {
        "name": name,
        "first_date": appearances[-1].match.date,
        "last_date": appearances[0].match.date,
        "starts": starts,
        "bench": total - starts,
        "total": total,
        "seasons_played": seasons_played,
        "win_pct": wins / total * 100.0,
        "by_shirt": [
            {"num": number, "count": count, "pct": count / total * 100.0}
            for number, count in sorted(shirt_counts.items())
        ],
        "appearances": appearances,
    }


def find_potential_duplicates(player_names_to_check, all_player_names, threshold=90):
    errors = []
    known_names = set(all_player_names)
    for name in player_names_to_check:
        if name not in known_names and all_player_names:
            best_match, score = fuzz_process.extractOne(name, all_player_names)
            if score >= threshold:
                errors.append(f"'{name}' is not an existing player. Did you mean '{best_match}'?")
    return errors
