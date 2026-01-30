from app.extensions import db
from app.models import Match, Player, Appearance
from sqlalchemy import func, case
from collections import Counter
from thefuzz import process as fuzz_process, fuzz

def _collect_seasons(matches=None):
    if matches is None:
        # Query distinct seasons from the Match table
        seasons_query = db.session.query(Match.season).distinct().all()
        seasons = [s[0] for s in seasons_query if s[0]]
    else:
        # If matches provided, extract from them (legacy behavior mostly)
        seasons = list(set(m.season for m in matches if m.season))

    # attempt to sort seasons by the numeric year parsed from the first 4 digits
    # (e.g., '2015-16' -> 2015). Sort most recent first.
    def season_key(s):
        try:
            return -int(s.strip()[:4])
        except Exception:
            # fallback to lexicographic ordering for unparsable labels
            return s
    try:
        seasons = sorted(seasons, key=season_key)
    except (ValueError, TypeError):
        pass
    return seasons

def compute_season_stats(season):
    """Compute aggregate statistics for a given season string."""
    season_matches = Match.query.filter_by(season=season).all()
    if not season_matches:
        return None

    total_matches = len(season_matches)
    
    wins = draws = losses = 0
    points_for = 0
    points_against = 0

    # player counters for the season
    player_counts = {}
    shirt_counter = Counter()

    for match in season_matches:
        # result
        r = (match.result or '').lower()
        if r.startswith('win'):
            wins += 1
        elif r.startswith('draw'):
            draws += 1
        else:
            losses += 1

        # points
        points_for += match.guildford_points or 0
        points_against += match.opposition_points or 0

        # players
        for ap in match.appearances:
            name = ap.player.name
            entry = player_counts.setdefault(name, {'starts': 0, 'bench': 0, 'total': 0})
            if ap.position <= 15:
                entry['starts'] += 1
            else:
                entry['bench'] += 1
            entry['total'] += 1
            shirt_counter[ap.position] += 1

    # average points for/against per match
    avg_points_for = round((points_for / total_matches)) if total_matches > 0 else 0
    avg_points_against = round((points_against / total_matches)) if total_matches > 0 else 0
    win_pct = (wins / total_matches * 100.0) if total_matches > 0 else 0.0

    # leaderboard: sort by total desc, then starts desc, then name
    leaderboard = sorted(player_counts.items(), key=lambda kv: (-kv[1].get('total', 0), -kv[1].get('starts', 0), kv[0]))

    # total unique players used
    total_players_used = len(player_counts)

    # Compute global first-appearance season for each player
    first_appearance_season = {}
    first_apps = db.session.query(Player.name, func.min(Match.season)).select_from(Player).join(Appearance).join(Match).group_by(Player.name).all()
    for name, first_season in first_apps:
        first_appearance_season[name] = first_season

    # Debuts: players whose first appearance season is this season
    debuts = [p for p in player_counts.keys() if first_appearance_season.get(p) == season]
    debut_count = len(debuts)
    debut_pct = (debut_count / total_players_used * 100.0) if total_players_used > 0 else 0.0

    # find previous season
    # Note: this might be inefficient if called often, but matches current logic
    all_seasons = _collect_seasons() 
    prev_season = None
    if season in all_seasons:
        idx = all_seasons.index(season)
        if idx + 1 < len(all_seasons):
            prev_season = all_seasons[idx + 1]

    # fallback logic for prev_season if not found in list (regex) - kept from original
    if prev_season is None:
        try:
            import re
            m = re.match(r'^\s*(\d{4})\s*-\s*(\d{2,4})\s*$', season)
            if m:
                start = int(m.group(1))
                prev_start = start - 1
                prev_end = (prev_start + 1) % 100
                candidate = f"{prev_start}-{prev_end:02d}"
                if candidate in all_seasons:
                    prev_season = candidate
                else:
                    prev_season = candidate # simplified assumption
        except Exception:
            pass

    leavers = []
    leavers_count = 0
    leavers_pct = 0.0
    if prev_season:
        # players in previous season
        prev_players = {p.name for p in Player.query.join(Appearance).join(Match).filter(Match.season == prev_season)}

        # players who were in prev season but not in this season
        leavers_set = prev_players - set(player_counts.keys())
        leavers = sorted(leavers_set)
        leavers_count = len(leavers)
        leavers_pct = (leavers_count / len(prev_players) * 100.0) if len(prev_players) > 0 else 0.0

    # shirt distribution list
    shirt_dist = []
    for num, cnt in sorted(shirt_counter.items()):
        pct = (cnt / sum(shirt_counter.values()) * 100.0) if shirt_counter else 0.0
        shirt_dist.append({'num': num, 'count': cnt, 'pct': pct})

    # match list (sorted by date)
    match_list = sorted(season_matches, key=lambda m: m.date)

    return {
        'season': season,
        'total_matches': total_matches,
        'wins': wins,
        'draws': draws,
        'losses': losses,
        'win_pct': win_pct,
        'points_for': points_for,
        'points_against': points_against,
        'avg_points_for': avg_points_for,
        'avg_points_against': avg_points_against,
        'leaderboard': leaderboard,
        'shirt_dist': shirt_dist,
        'total_players_used': total_players_used,
        'debut_count': debut_count,
        'debut_pct': debut_pct,
        'leavers': leavers,
        'leavers_count': leavers_count,
        'leavers_pct': leavers_pct,
        'match_list': match_list,
        'available_seasons': all_seasons,
        'previous_season': prev_season,
    }

def get_player_stats(name):
    """Compute per-player stats."""
    player = Player.query.filter_by(name=name).first()
    if not player:
        return None

    player_appearances = Appearance.query.filter_by(player_id=player.id).join(Match).order_by(Match.date.desc()).all()
    if not player_appearances:
        return None

    total_matches = len(player_appearances)
    starts = sum(1 for a in player_appearances if a.position <= 15)
    bench = total_matches - starts
    wins = sum(1 for a in player_appearances if (a.match.result or '').lower() == 'win')
    win_pct = (wins / total_matches * 100.0) if total_matches > 0 else 0.0

    first_app = Appearance.query.filter_by(player_id=player.id).join(Match).order_by(Match.date.asc()).first()
    last_app = Appearance.query.filter_by(player_id=player.id).join(Match).order_by(Match.date.desc()).first()
    first_date = first_app.match.date if first_app else None
    last_date = last_app.match.date if last_app else None

    # compute distribution by shirt number
    shirt_counts = Counter()
    for a in player_appearances:
        shirt_counts[a.position] += 1

    by_shirt = []
    for num, cnt in sorted(shirt_counts.items()):
        pct = (cnt / total_matches * 100.0) if total_matches > 0 else 0.0
        by_shirt.append({'num': num, 'count': cnt, 'pct': pct})

    return {
        'name': name,
        'first_date': first_date,
        'last_date': last_date,
        'starts': starts,
        'bench': bench,
        'total': total_matches,
        'win_pct': win_pct,
        'by_shirt': by_shirt,
        'appearances': player_appearances, 
    }

def find_potential_duplicates(player_names_to_check, all_player_names, threshold=90):
    """Checks a list of names against a list of known names for potential duplicates."""
    errors = []
    known_names_set = set(all_player_names)

    for name in player_names_to_check:
        if name not in known_names_set:
            if all_player_names:
                best_match, score = fuzz_process.extractOne(name, all_player_names)
                if score >= threshold:
                    errors.append(f"'{name}' is not an existing player. Did you mean '{best_match}'?")
    return errors
