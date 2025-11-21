from flask import Flask, request, redirect, url_for, render_template, flash, session
from functools import wraps
import csv
import io
import os
from collections import Counter
from datetime import datetime
from urllib.parse import unquote

app = Flask(__name__)
# Use an environment-provided SECRET_KEY in production (recommended).
app.secret_key = os.environ.get('SECRET_KEY', 'change-me-for-production')

CSV_PATH = os.path.join(os.path.dirname(__file__), "GRFC_data.csv")


def read_rows():
    """Read CSV rows (including header) as lists of fields."""
    rows = []
    if not os.path.exists(CSV_PATH):
        return rows
    with open(CSV_PATH, newline='', encoding='utf-8') as f:
        reader = csv.reader(f, skipinitialspace=True)
        for row in reader:
            # skip empty lines
            if not any(cell.strip() for cell in row):
                continue
            rows.append([cell.strip() for cell in row])
    return rows


def get_most_recent_teamsheet():
    """Return the most recent teamsheet row as a dict of metadata and players.

    Returns:
        { 'league':..., 'season':..., 'date':..., 'opposition':...,
          'location':..., 'result':..., 'guildford_points':..., 'opposition_points':...,
          'players': [p1, p2, ...]
        }
    If CSV is empty, returns defaults with empty strings and 20 empty players.
    """
    rows = read_rows()
    # defaults
    defaults = {
        'league': '', 'season': '', 'date': '', 'opposition': '', 'location': '',
        'result': '', 'guildford_points': '', 'opposition_points': '',
        'players': [''] * 20
    }
    if not rows or len(rows) < 2:
        return defaults

    header = rows[0]
    player_start = find_player_start_index(header)

    # Try to find the row with the maximum parseable date in the Date column (index 2)
    best_row = None
    best_date = None

    def parse_date_safe(s):
        if not s:
            return None
        s = s.strip()
        if not s:
            return None
        for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
            try:
                return datetime.strptime(s, fmt).date()
            except Exception:
                continue
        return None

    for row in rows[1:]:
        date_str = row[2] if len(row) > 2 else ''
        d = parse_date_safe(date_str)
        if d is None:
            continue
        if best_date is None or d > best_date:
            best_date = d
            best_row = row

    # If we couldn't parse any dates, fallback to the last row
    selected = best_row if best_row is not None else rows[-1]

    last = selected
    # Ensure we have at least metadata fields
    if len(last) >= 8:
        meta = last[:8]
    else:
        meta = last + [''] * (8 - len(last))

    players = []
    if len(last) > player_start:
        players = last[player_start:player_start + 20]
    # pad to 20
    if len(players) < 20:
        players += [''] * (20 - len(players))

    # If date parsed, fill normalized date string into defaults['date'] so form shows a consistent value
    date_value = ''
    if best_date is not None:
        date_value = best_date.strftime('%d/%m/%Y')
    else:
        # use raw meta value if available
        date_value = meta[2] if len(meta) > 2 else ''

    return {
        'league': meta[0],
        'season': meta[1],
        'date': date_value,
        'opposition': meta[3],
        'location': meta[4],
        'result': meta[5],
        'guildford_points': meta[6],
        'opposition_points': meta[7],
        'players': players,
    }


def find_player_start_index(header_row):
    """Detect the first column index that represents player positions (1,2,3...)."""
    for i, h in enumerate(header_row):
        if h.strip().isdigit():
            return i
    # fallback: assume player columns start at column 8 (common in this CSV)
    return 8


def compute_appearances():
    rows = read_rows()
    if not rows:
        return {}
    header = rows[0]
    player_start = find_player_start_index(header)

    counts = {}
    for row in rows[1:]:
        # ensure row has enough columns
        if len(row) <= player_start:
            continue
        # enumerate player columns; idx is 1-based position among player columns
        for idx, cell in enumerate(row[player_start:], start=1):
            name = cell.strip()
            if not name:
                continue
            entry = counts.setdefault(name, {'starts': 0, 'bench': 0, 'total': 0})
            if idx <= 15:
                entry['starts'] += 1
            else:
                entry['bench'] += 1
            entry['total'] += 1
    return counts


def append_row_text(row_text):
    """Append a raw CSV row text to the CSV file.

    We validate that the text parses as CSV first.
    """
    sio = io.StringIO(row_text)
    reader = csv.reader(sio, skipinitialspace=True)
    parsed_any = False
    # Write parsed rows using csv.writer to ensure consistent quoting and column separation
    with open(CSV_PATH, 'a', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        for parsed in reader:
            # skip empty/blank parsed rows
            if not parsed or not any(cell.strip() for cell in parsed):
                continue
            # strip whitespace from each cell and write
            writer.writerow([cell.strip() for cell in parsed])
            parsed_any = True

    if not parsed_any:
        raise ValueError("Could not parse provided row as CSV")


def append_row_list(row_list):
    """Append a parsed row (list of fields) to the CSV using csv.writer to ensure correct quoting."""
    # Normalize empty strings
    row_list = [str(x).strip() if x is not None else '' for x in row_list]
    # Ensure the file exists and ends with a newline where appropriate
    exists = os.path.exists(CSV_PATH)
    with open(CSV_PATH, 'a', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        # If file exists and not empty, writer will append on a new line; just write the row
        writer.writerow(row_list)


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get('admin'):
            return redirect(url_for('login', next=request.path))
        return f(*args, **kwargs)
    return wrapper



@app.route('/', methods=['GET'])
def index():
    # Make the add form the default entry point
    return redirect(url_for('add'))


@app.route('/add', methods=['GET'])
@admin_required
def add():
    defaults = get_most_recent_teamsheet()
    return render_template('add.html', defaults=defaults)


@app.route('/add', methods=['POST'])
@admin_required
def add_post():
    # Collect metadata fields
    league = request.form.get('league', '').strip()
    season = request.form.get('season', '').strip()
    date = request.form.get('date', '').strip()
    opposition = request.form.get('opposition', '').strip()
    location = request.form.get('location', '').strip()
    result = request.form.get('result', '').strip()
    guildford_points = request.form.get('guildford_points', '').strip()
    opposition_points = request.form.get('opposition_points', '').strip()

    # Collect up to 20 player fields (some CSVs include 18, 19 or 20)
    players = []
    for i in range(1, 21):
        p = request.form.get(f'player{i}', '')
        if p is None:
            p = ''
        players.append(p.strip())

    row = [league, season, date, opposition, location, result, guildford_points, opposition_points] + players
    try:
        append_row_list(row)
    except Exception as e:
        flash(f'Error appending row: {e}', 'error')
        return redirect(url_for('add'))
    flash('Teamsheet added successfully.', 'success')
    return redirect(url_for('stats'))


@app.route('/upload', methods=['POST'])
@admin_required
def upload():
    row_text = request.form.get('row')
    if not row_text or not row_text.strip():
        flash('Please paste a CSV row into the textarea.', 'error')
        return redirect(url_for('index'))
    try:
        append_row_text(row_text)
    except Exception as e:
        flash(f'Error appending row: {e}', 'error')
        return redirect(url_for('index'))
    flash('Row appended successfully.', 'success')
    return redirect(url_for('stats'))


@app.route('/stats', methods=['GET'])
def stats():
    counts = compute_appearances()
    # sort by total desc, then starts desc, then name
    sorted_players = sorted(
        counts.items(), key=lambda kv: (-kv[1].get('total', 0), -kv[1].get('starts', 0), kv[0])
    )
    return render_template('stats.html', players=sorted_players)


@app.route('/data', methods=['GET'])
def data_view():
    """Render the CSV as an HTML table showing the header and rows."""
    rows = read_rows()
    header = rows[0] if rows else []
    data_rows = rows[1:] if len(rows) > 1 else []
    player_start = find_player_start_index(header) if header else 8
    return render_template('data.html', header=header, rows=data_rows, player_start=player_start)


@app.route('/login', methods=['GET', 'POST'])
def login():
    # simple admin login (credentials can be set via env vars ADMIN_USER and ADMIN_PASS)
    if request.method == 'POST':
        user = request.form.get('username', '').strip()
        pw = request.form.get('password', '').strip()
        admin_user = os.environ.get('ADMIN_USER', 'admin')
        admin_pass = os.environ.get('ADMIN_PASS', 'password')
        if user == admin_user and pw == admin_pass:
            session['admin'] = True
            next_url = request.args.get('next') or request.form.get('next') or url_for('add')
            return redirect(next_url)
        else:
            flash('Invalid credentials', 'error')
            return render_template('login.html', next=request.args.get('next') or '')
    return render_template('login.html', next=request.args.get('next') or '')


@app.route('/logout', methods=['GET'])
def logout():
    session.pop('admin', None)
    flash('Logged out', 'info')
    return redirect(url_for('index'))


def _collect_seasons(rows):
    seasons = []
    for row in rows[1:]:
        if len(row) > 1:
            s = row[1].strip()
            if s and s not in seasons:
                seasons.append(s)
    # attempt to sort seasons by the numeric year parsed from the first 4 digits
    # (e.g., '2015-16' -> 2015). Sort most recent first.
    def season_key(s):
        try:
            year_part = s.strip()[:4]
            year = int(year_part)
            return -year
        except Exception:
            # fallback to lexicographic ordering for unparsable labels
            return s
    try:
        seasons = sorted(seasons, key=season_key)
    except Exception:
        pass
    return seasons


def compute_season_stats(season):
    """Compute aggregate statistics for a given season string (matches the Season column).

    Returns a dict with summary metrics, player leaderboard, shirt distribution,
    total players, debuts count, leavers count, and match list.
    """
    rows = read_rows()
    if not rows or len(rows) < 2:
        return None
    header = rows[0]
    player_start = find_player_start_index(header)

    # Collect rows for the requested season
    season_rows = []
    for row in rows[1:]:
        if len(row) > 1 and row[1].strip() == season:
            season_rows.append(row)

    total_matches = len(season_rows)

    wins = draws = losses = 0
    points_for = 0
    points_against = 0

    # player counters for the season
    from collections import Counter as _Counter
    player_counts = {}
    shirt_counter = _Counter()

    for row in season_rows:
        # result
        result = row[5].strip() if len(row) > 5 else ''
        r = result.lower()
        if r.startswith('win'):
            wins += 1
        elif r.startswith('draw'):
            draws += 1
        else:
            # count anything else as a loss for simplicity
            losses += 1

        # points
        try:
            points_for += int(row[6].strip()) if len(row) > 6 and row[6].strip() else 0
        except Exception:
            pass
        try:
            points_against += int(row[7].strip()) if len(row) > 7 and row[7].strip() else 0
        except Exception:
            pass

        # players
        if len(row) > player_start:
            for idx, cell in enumerate(row[player_start:], start=1):
                name = cell.strip()
                if not name:
                    continue
                entry = player_counts.setdefault(name, {'starts': 0, 'bench': 0, 'total': 0})
                if idx <= 15:
                    entry['starts'] += 1
                else:
                    entry['bench'] += 1
                entry['total'] += 1
                shirt_counter[idx] += 1

    # average points for/against per match, rounded to whole numbers
    avg_points_for = round((points_for / total_matches)) if total_matches > 0 else 0
    avg_points_against = round((points_against / total_matches)) if total_matches > 0 else 0
    win_pct = (wins / total_matches * 100.0) if total_matches > 0 else 0.0

    # leaderboard: sort by total desc, then starts desc, then name
    leaderboard = sorted(player_counts.items(), key=lambda kv: (-kv[1].get('total', 0), -kv[1].get('starts', 0), kv[0]))

    # total unique players used
    total_players_used = len(player_counts)

    # compute global first-appearance season for each player to detect debuts
    first_appearance_season = {}
    for row in rows[1:]:
        row_season = row[1].strip() if len(row) > 1 else ''
        if len(row) > player_start:
            for cell in row[player_start:]:
                name = cell.strip()
                if not name:
                    continue
                if name not in first_appearance_season:
                    first_appearance_season[name] = row_season

    # debuts: players whose first appearance season == this season
    debuts = [p for p in player_counts.keys() if first_appearance_season.get(p) == season]
    debut_count = len(debuts)
    debut_pct = (debut_count / total_players_used * 100.0) if total_players_used > 0 else 0.0

    # find previous season (based on seasons list ordering)
    seasons = _collect_seasons(rows)
    prev_season = None
    if season in seasons:
        idx = seasons.index(season)
        if idx + 1 < len(seasons):
            prev_season = seasons[idx + 1]

    # If we couldn't find an explicit previous season in the collected list,
    # try to derive the previous season label arithmetically (e.g. '2016-17' -> '2015-16').
    # This helps when season labels follow the YYYY-YY pattern but a season row
    # might be missing from the CSV.
    if prev_season is None:
        try:
            import re
            m = re.match(r'^\s*(\d{4})\s*-\s*(\d{2,4})\s*$', season)
            if m:
                start = int(m.group(1))
                prev_start = start - 1
                prev_end = prev_start % 100
                candidate = f"{prev_start}-{prev_end:02d}"
                if candidate in seasons:
                    prev_season = candidate
                else:
                    # even if candidate not present in seasons list, use it as the
                    # logical previous-season label so callers can display it.
                    prev_season = candidate
        except Exception:
            pass

    leavers = []
    leavers_count = 0
    leavers_pct = 0.0
    if prev_season:
        # players in previous season
        prev_players = set()
        for row in rows[1:]:
            if len(row) > 1 and row[1].strip() == prev_season and len(row) > player_start:
                for cell in row[player_start:]:
                    n = cell.strip()
                    if n:
                        prev_players.add(n)
        # players who were in prev season but not in this season
        leavers_set = prev_players.difference(set(player_counts.keys()))
        leavers = sorted(leavers_set)
        leavers_count = len(leavers)
        leavers_pct = (leavers_count / len(prev_players) * 100.0) if len(prev_players) > 0 else 0.0

    # shirt distribution list
    shirt_dist = []
    for num, cnt in sorted(shirt_counter.items()):
        pct = (cnt / sum(shirt_counter.values()) * 100.0) if shirt_counter else 0.0
        shirt_dist.append({'num': num, 'count': cnt, 'pct': pct})

    # match list (sorted by parsed date ascending)
    match_list = []
    for row in season_rows:
        date_raw = row[2] if len(row) > 2 else ''
        date_parsed = parse_date_safe(date_raw)
        match_list.append({
            'date_raw': date_raw,
            'date': date_parsed,
            'opposition': row[3] if len(row) > 3 else '',
            'location': row[4] if len(row) > 4 else '',
            'result': row[5] if len(row) > 5 else '',
            'guildford_points': row[6] if len(row) > 6 else '',
            'opposition_points': row[7] if len(row) > 7 else '',
            'row': row,
        })
    match_list = sorted(match_list, key=lambda m: (m['date'] is None, m['date'] or datetime.min.date()))

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
        'available_seasons': _collect_seasons(rows),
        'previous_season': prev_season,
    }


@app.route('/season', methods=['GET'])
def season_view():
    rows = read_rows()
    seasons = _collect_seasons(rows)
    if not seasons:
        flash('No season data available', 'error')
        return redirect(url_for('stats'))
    season = request.args.get('season') or seasons[0]
    stats = compute_season_stats(season)
    if stats is None:
        flash('No data for that season', 'error')
        return redirect(url_for('stats'))
    return render_template('season.html', stats=stats)


def parse_date_safe(s):
    if not s:
        return None
    s = s.strip()
    if not s:
        return None
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            continue
    return None


def get_player_stats(name):
    """Compute per-player stats and return metadata and list of teamsheets where they appear."""
    rows = read_rows()
    if not rows or len(rows) < 2:
        return None
    header = rows[0]
    player_start = find_player_start_index(header)

    appearances = []  # list of dicts for matches where player appears
    for row in rows[1:]:
        # check if player appears in this row's player columns
        if len(row) <= player_start:
            continue
        found_idx = None
        for idx, cell in enumerate(row[player_start:], start=1):
            if cell.strip() and cell.strip() == name:
                found_idx = idx
                break
        if found_idx is None:
            continue

        date_raw = row[2] if len(row) > 2 else ''
        date_parsed = parse_date_safe(date_raw)
        result = row[5] if len(row) > 5 else ''
        guildford_points = row[6] if len(row) > 6 else ''
        opposition_points = row[7] if len(row) > 7 else ''
        # players slice
        players = row[player_start:player_start + 20] if len(row) > player_start else []

        appearances.append({
            'date_raw': date_raw,
            'date': date_parsed,
            'result': result,
            'guildford_points': guildford_points,
            'opposition_points': opposition_points,
            'players': players,
            'position_index': found_idx,
            'row': row,
        })

    if not appearances:
        return None

    # compute first and last appearance by date if possible, otherwise by order seen
    dates = [a['date'] for a in appearances if a['date'] is not None]
    first_date = min(dates) if dates else None
    last_date = max(dates) if dates else None

    starts = 0
    bench = 0
    wins = 0
    total_matches = 0
    for a in appearances:
        total_matches += 1
        if a['position_index'] <= 15:
            starts += 1
        else:
            bench += 1
        if a['result'] and a['result'].strip().lower() == 'win':
            wins += 1

    win_pct = (wins / total_matches * 100.0) if total_matches > 0 else 0.0

    # sort appearances by date desc where possible, else keep file order
    appearances_sorted = sorted(appearances, key=lambda a: (a['date'] is None, a['date'] or datetime.min.date()), reverse=True)
    # compute distribution by shirt number
    from collections import Counter as _Counter
    shirt_counts = _Counter()
    for a in appearances:
        shirt_counts[a['position_index']] += 1

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
        'appearances': appearances_sorted,
    }


@app.route('/player', methods=['GET'])
def player_view():
    name = request.args.get('name')
    if not name:
        flash('Missing player name', 'error')
        return redirect(url_for('stats'))
    # URL param will be percent-decoded by Flask already; ensure trimmed
    name = name.strip()
    stats = get_player_stats(name)
    if not stats:
        flash(f'No appearances found for {name}', 'error')
        return redirect(url_for('stats'))
    return render_template('player.html', stats=stats)


if __name__ == '__main__':
    # Respect environment flags for debug and PORT when running locally.
    debug_env = os.environ.get('FLASK_DEBUG', '')
    debug = str(debug_env).lower() in ('1', 'true', 'yes')
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=debug)
