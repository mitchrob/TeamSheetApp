from flask import Flask, request, redirect, url_for, render_template, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, case
from functools import wraps
import csv
import io
import os
from collections import Counter
from datetime import datetime

app = Flask(__name__)
# Use an environment-provided SECRET_KEY in production (recommended).
app.secret_key = os.environ.get('SECRET_KEY', 'change-me-for-production')

# --- Database Configuration ---
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(os.path.dirname(__file__), 'app.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- Database Models ---
class Player(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    appearances = db.relationship('Appearance', back_populates='player', lazy='dynamic')

class Match(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    league = db.Column(db.String(100))
    season = db.Column(db.String(20))
    date = db.Column(db.Date, nullable=False)
    opposition = db.Column(db.String(100))
    location = db.Column(db.String(50))
    result = db.Column(db.String(20))
    guildford_points = db.Column(db.Integer)
    opposition_points = db.Column(db.Integer)
    appearances = db.relationship('Appearance', back_populates='match', cascade="all, delete-orphan")

class Appearance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    match_id = db.Column(db.Integer, db.ForeignKey('match.id'), nullable=False)
    position = db.Column(db.Integer, nullable=False) # 1-15 for starts, 16-20 for bench
    player = db.relationship('Player', back_populates='appearances')
    match = db.relationship('Match', back_populates='appearances')

CSV_PATH = os.path.join(os.path.dirname(__file__), "GRFC_data.csv")

def get_most_recent_teamsheet_from_db():
    """Return the most recent teamsheet from the DB as a dict for form defaults."""
    defaults = {
        'league': '', 'season': '', 'date': '', 'opposition': '', 'location': '',
        'result': '', 'guildford_points': '', 'opposition_points': '',
        'players': [''] * 20
    }
    
    last_match = Match.query.order_by(Match.date.desc()).first()
    if not last_match:
        return defaults

    # Pre-fill players
    players = [''] * 20
    for ap in last_match.appearances:
        if 1 <= ap.position <= 20:
            players[ap.position - 1] = ap.player.name

    return {
        'league': last_match.league,
        'season': last_match.season,
        'date': last_match.date.strftime('%d/%m/%Y'),
        'opposition': last_match.opposition,
        'location': last_match.location,
        'result': last_match.result,
        'guildford_points': last_match.guildford_points,
        'opposition_points': last_match.opposition_points,
        'players': players,
    }

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
    defaults = get_most_recent_teamsheet_from_db()
    return render_template('add.html', defaults=defaults)


@app.route('/player_names', methods=['GET'])
@admin_required
def player_names():
    players = Player.query.order_by(Player.name).all()
    player_names = [p.name for p in players]
    return jsonify(player_names)


@app.route('/add', methods=['POST'])
@admin_required
def add_post():
    league = request.form.get('league', '').strip()
    season = request.form.get('season', '').strip()
    date_str = request.form.get('date', '').strip()
    opposition = request.form.get('opposition', '').strip()
    location = request.form.get('location', '').strip()
    result = request.form.get('result', '').strip()
    guildford_points = request.form.get('guildford_points', '').strip()
    opposition_points = request.form.get('opposition_points', '').strip()
    player_names = [request.form.get(f'player{i}', '').strip() for i in range(1, 21)]

    match_date = parse_date_safe(date_str)
    if not match_date:
        flash('Invalid date format. Please use dd/mm/yyyy.', 'error')
        return redirect(url_for('add'))

    # Validate for duplicate players
    non_empty_players = [name for name in player_names if name]
    player_counts = Counter(non_empty_players)
    duplicates = [name for name, count in player_counts.items() if count > 1]
    if duplicates:
        flash(f'The teamsheet contains duplicate players: {", ".join(duplicates)}. Please correct and resubmit.', 'error')
        return redirect(url_for('add'))

    try:
        new_match = Match(
            league=league,
            season=season,
            date=match_date,
            opposition=opposition,
            location=location,
            result=result,
            guildford_points=int(guildford_points) if guildford_points.isdigit() else None,
            opposition_points=int(opposition_points) if opposition_points.isdigit() else None
        )
        db.session.add(new_match)

        for i, name in enumerate(player_names):
            if not name:
                continue
            player = Player.query.filter_by(name=name).first()
            if not player:
                player = Player(name=name)
                db.session.add(player)
            
            appearance = Appearance(player=player, match=new_match, position=i + 1)
            db.session.add(appearance)

        db.session.commit()
        flash('Teamsheet added successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding teamsheet: {e}', 'error')
        return redirect(url_for('add'))
    return redirect(url_for('stats'))


@app.route('/stats', methods=['GET'])
def stats():
    starts_case = case((Appearance.position <= 15, 1), else_=0)
    bench_case = case((Appearance.position > 15, 1), else_=0)

    player_stats = db.session.query(
        Player.name,
        func.count(Appearance.id).label('total'),
        func.sum(starts_case).label('starts'),
        func.sum(bench_case).label('bench')
    ).join(Appearance).group_by(Player.name).all()

    sorted_players = sorted(
        player_stats, key=lambda p: (-p.total, -p.starts, p.name)
    )
    return render_template('stats.html', players=sorted_players)


@app.route('/data', methods=['GET'])
def data_view():
    matches = Match.query.order_by(Match.date.desc()).all()
    return render_template('data.html', matches=matches)


@app.route('/edit/<int:match_id>', methods=['GET', 'POST'])
@admin_required
def edit_match(match_id):
    match = Match.query.get_or_404(match_id)

    if request.method == 'POST':
        match.league = request.form.get('league', '').strip()
        match.season = request.form.get('season', '').strip()
        match.date = parse_date_safe(request.form.get('date', '').strip())
        match.opposition = request.form.get('opposition', '').strip()
        match.location = request.form.get('location', '').strip()
        match.result = request.form.get('result', '').strip()
        match.guildford_points = int(request.form.get('guildford_points')) if request.form.get('guildford_points').isdigit() else None
        match.opposition_points = int(request.form.get('opposition_points')) if request.form.get('opposition_points').isdigit() else None

        # Clear existing appearances for this match
        Appearance.query.filter_by(match_id=match.id).delete()

        player_names = [request.form.get(f'player{i}', '').strip() for i in range(1, 21)]
        # Validate for duplicate players
        non_empty_players = [name for name in player_names if name]
        player_counts = Counter(non_empty_players)
        duplicates = [name for name, count in player_counts.items() if count > 1]
        if duplicates:
            flash(f'The teamsheet contains duplicate players: {", ".join(duplicates)}. Please correct and resubmit.', 'error')
            return redirect(url_for('edit_match', match_id=match_id))

        for i, name in enumerate(player_names):
            if not name:
                continue
            player = Player.query.filter_by(name=name).first()
            if not player:
                player = Player(name=name)
                db.session.add(player)
            appearance = Appearance(player=player, match=match, position=i + 1)
            db.session.add(appearance)
        
        db.session.commit()
        flash('Match updated successfully.', 'success')
        return redirect(url_for('data_view'))

    # GET request
    players = [''] * 20
    for ap in match.appearances:
        if 1 <= ap.position <= 20:
            players[ap.position - 1] = ap.player.name
    
    return render_template('edit.html', match=match, players=players)


@app.route('/delete/<int:match_id>', methods=['POST'])
@admin_required
def delete_match(match_id):
    match = Match.query.get_or_404(match_id)
    db.session.delete(match)
    db.session.commit()
    flash('Match deleted successfully.', 'success')
    return redirect(url_for('data_view'))

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
    # Query distinct seasons from the Match table
    seasons_query = db.session.query(Match.season).distinct().all()
    seasons = [s[0] for s in seasons_query if s[0]]

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
    """Compute aggregate statistics for a given season string (matches the Season column).

    Returns a dict with summary metrics, player leaderboard, shirt distribution,
    total players, debuts count, leavers count, and match list.
    """
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

    # average points for/against per match, rounded to whole numbers
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

    # find previous season (based on seasons list ordering)
    all_matches = Match.query.all()
    seasons = _collect_seasons(all_matches)
    prev_season = None
    if season in seasons:
        idx = seasons.index(season)
        if idx + 1 < len(seasons):
            prev_season = seasons[idx + 1]

    if prev_season is None:
        try:
            import re
            m = re.match(r'^\s*(\d{4})\s*-\s*(\d{2,4})\s*$', season)
            if m:
                start = int(m.group(1))
                prev_start = start - 1
                prev_end = (prev_start + 1) % 100
                candidate = f"{prev_start}-{prev_end:02d}"
                if candidate in seasons:
                    prev_season = candidate
                else:
                    prev_season = candidate
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

    # match list (sorted by parsed date ascending)
    match_list = sorted(season_matches, key=lambda m: m.date)
    # Convert to dicts for template compatibility if needed, but passing objects is better
    # For now, we assume the template can handle the match objects directly.

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
        'available_seasons': seasons,
        'previous_season': prev_season,
    }


@app.route('/season', methods=['GET'])
def season_view():
    all_matches = Match.query.all()
    seasons = _collect_seasons(all_matches)
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
        'appearances': player_appearances, # Already sorted by date desc
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


# --- CLI Commands for Database Management ---
@app.cli.command('init-db')
def init_db_command():
    """Create all database tables."""
    # Use app_context to ensure the application context is available.
    # db.create_all() needs this to know which app instance to work with.
    db.create_all()
    print('Initialized the database.')

@app.cli.command('migrate-csv')
def migrate_csv_command():
    """Migrate data from GRFC_data.csv to the database."""

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

    if not os.path.exists(CSV_PATH):
        CSV_PATH = os.path.join(os.path.dirname(__file__), "GRFC_data.csv")
        print(f"Error: {CSV_PATH} not found.")
        return

    rows = read_rows()
    if not rows or len(rows) < 2:
        print("CSV file is empty or contains only a header.")
        return

    def find_player_start_index(header_row):
        """Detect the first column index that represents player positions (1,2,3...)."""
        for i, h in enumerate(header_row):
            if h.strip().isdigit():
                return i
        # fallback: assume player columns start at column 8 (common in this CSV)
        return 8


    header = rows[0]
    player_start = find_player_start_index(header)
    player_cache = {} # Cache player objects to avoid DB lookups

    with app.app_context():
        for row in rows[1:]:
            # Parse match data
            date_str = row[2] if len(row) > 2 else ''
            match_date = parse_date_safe(date_str)
            if not match_date:
                print(f"Skipping row with unparseable date: {date_str}")
                continue

            new_match = Match(
                league=row[0],
                season=row[1],
                date=match_date,
                opposition=row[3],
                location=row[4],
                result=row[5],
                guildford_points=int(row[6]) if row[6].isdigit() else None,
                opposition_points=int(row[7]) if row[7].isdigit() else None,
            )
            db.session.add(new_match)

            # Parse players and create appearances
            for i, player_name in enumerate(row[player_start:player_start + 20]):
                player_name = player_name.strip()
                if not player_name:
                    continue
                
                player = player_cache.get(player_name)
                if not player:
                    player = Player.query.filter_by(name=player_name).first()
                    if not player:
                        player = Player(name=player_name)
                        db.session.add(player)
                    player_cache[player_name] = player
                
                appearance = Appearance(player=player, match=new_match, position=i + 1)
                db.session.add(appearance)
        
        db.session.commit()
    print(f"Successfully migrated {len(rows) - 1} rows from CSV to the database.")
