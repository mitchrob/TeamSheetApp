from collections import Counter

from app.services import canonicalize_season, normalize_result
from app.utils import parse_date_safe


def validate_match_form(form, squad_size):
    values = {
        "league": form.get("league", "").strip(),
        "season": form.get("season", "").strip(),
        "date": form.get("date", "").strip(),
        "opposition": form.get("opposition", "").strip(),
        "location": form.get("location", "").strip(),
        "result": form.get("result", "").strip(),
        "guildford_points": form.get("guildford_points", "").strip(),
        "opposition_points": form.get("opposition_points", "").strip(),
    }
    players = [form.get(f"player{position}", "").strip() for position in range(1, squad_size + 1)]
    values["players"] = players
    errors = []

    match_date = parse_date_safe(values["date"])
    if not match_date:
        errors.append("Enter a valid match date.")

    season = canonicalize_season(values["season"])
    if not season:
        errors.append("Season must use the format YYYY-YY, for example 2026-27.")

    if not values["opposition"]:
        errors.append("Opposition is required.")
    if len(values["opposition"]) > 100:
        errors.append("Opposition must be 100 characters or fewer.")
    if len(values["league"]) > 100:
        errors.append("League must be 100 characters or fewer.")
    if len(values["location"]) > 50:
        errors.append("Location must be 50 characters or fewer.")

    guildford_points = _parse_score(values["guildford_points"], "Guildford score", errors)
    opposition_points = _parse_score(values["opposition_points"], "Opposition score", errors)
    if (guildford_points is None) != (opposition_points is None):
        errors.append("Enter both scores or leave both scores blank.")

    result = normalize_result(values["result"], guildford_points, opposition_points)
    if values["result"] and result is None:
        errors.append("Result must be Win, Draw, or Loss.")

    long_names = [name for name in players if len(name) > 100]
    if long_names:
        errors.append("Player names must be 100 characters or fewer.")
    normalized_names = [name.casefold() for name in players if name]
    duplicates = [name for name, count in Counter(normalized_names).items() if count > 1]
    if duplicates:
        errors.append("A player can only appear once on a teamsheet.")

    data = {
        "league": values["league"] or None,
        "season": season,
        "date": match_date,
        "opposition": values["opposition"],
        "location": values["location"] or None,
        "result": result,
        "guildford_points": guildford_points,
        "opposition_points": opposition_points,
    }
    return data, players, values, errors


def _parse_score(raw_value, label, errors):
    if not raw_value:
        return None
    try:
        score = int(raw_value)
    except ValueError:
        errors.append(f"{label} must be a whole number.")
        return None
    if not 0 <= score <= 999:
        errors.append(f"{label} must be between 0 and 999.")
        return None
    return score
