from flask import Flask, request, redirect, url_for, render_template, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, case
from functools import wraps
import csv
import io
import os
from collections import Counter
from datetime import datetime
from thefuzz import process as fuzz_process, fuzz

app = Flask(__name__)
# Use an environment-provided SECRET_KEY in production (recommended).
app.secret_key = os.environ.get('SECRET_KEY', 'change-me-for-production')

# --- Database Configuration ---
default_db_uri = 'sqlite:///' + os.path.join(os.path.dirname(__file__), 'app.db')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', default_db_uri)
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

def find_potential_duplicates(player_names_to_check, all_player_names, threshold=90):
    """
    Checks a list of names against a list of known names for potential duplicates.

    Returns:
        A list of error messages for names that are not exact matches but are
        very similar to existing names.
    """
    errors = []
    known_names_set = set(all_player_names)

    for name in player_names_to_check:
        if name not in known_names_set:
            # Find the best match from the list of all known players
            if all_player_names:
                best_match, score = fuzz_process.extractOne(name, all_player_names)
                if score >= threshold:
                    errors.append(f"'{name}' is not an existing player. Did you mean '{best_match}'?")
    
    return errors

def _process_teamsheet_form(form_data, match_obj=None):
    """Helper to process and validate teamsheet form data for add and edit."""
    player_names = [form_data.get(f'player{i}', '').strip() for i in range(1, 21)]

    # Validate for duplicate players on the teamsheet
    non_empty_players = [name for name in player_names if name]
    player_counts = Counter(non_empty_players)
    duplicates = [name for name, count in player_counts.items() if count > 1]
    if duplicates:
        flash(f'The teamsheet contains duplicate players: {", ".join(duplicates)}. Please correct and resubmit.', 'error')
        return None

    # Fuzzy match validation against existing players in the database
    all_player_names_in_db = [p.name for p in Player.query.all()]
    fuzzy_errors = find_potential_duplicates(non_empty_players, all_player_names_in_db)
    if fuzzy_errors:
        for error in fuzzy_errors:
            flash(error, 'error')
        return None

    # If editing, clear existing appearances
    if match_obj:
        Appearance.query.filter_by(match_id=match_obj.id).delete()

    # Create or update players and their appearances
    for i, name in enumerate(player_names):
        if not name:
            continue
        
        player = Player.query.filter_by(name=name).first()
        if not player:
            # This player is new to the database
            player = Player(name=name)
            db.session.add(player)
        
        # The appearance is always new, either for a new match or after clearing old ones
        appearance = Appearance(
            player=player, 
            match=match_obj, 
            position=i + 1
        )
        db.session.add(appearance)
    
    return True # Indicates success


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
    date_str = request.form.get('date', '').strip()

    match_date = parse_date_safe(date_str)
    if not match_date:
        flash('Invalid date format. Please use dd/mm/yyyy.', 'error')
        return redirect(url_for('add'))

    # Validate for duplicate players
    try:
        guildford_points = request.form.get('guildford_points', '').strip()
        opposition_points = request.form.get('opposition_points', '').strip()

        new_match = Match(
            league=league,
            season=request.form.get('season', '').strip(),
            date=match_date,
            opposition=request.form.get('opposition', '').strip(),
            location=request.form.get('location', '').strip(),
            result=request.form.get('result', '').strip(),
            guildford_points=int(guildford_points) if guildford_points.isdigit() else None,
            opposition_points=int(opposition_points) if opposition_points.isdigit() else None
        )
        db.session.add(new_match)

        if not _process_teamsheet_form(request.form, new_match):
            return redirect(url_for('add'))

        db.session.commit()
        flash('Teamsheet added successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding teamsheet: {e}', 'error')
        return redirect(url_for('add'))
    return redirect(url_for('stats'))


@app.route('/stats', methods=['GET'])
def stats():
    sort_by = request.args.get('sort', 'total')
    order = request.args.get('order', 'desc')
    show_all = request.args.get('show') == 'all'

    starts_case = case((Appearance.position <= 15, 1), else_=0)
    bench_case = case((Appearance.position > 15, 1), else_=0)

    # Define columns for querying and sorting
    total_col = func.count(Appearance.id).label('total')
    starts_col = func.sum(starts_case).label('starts')
    bench_col = func.sum(bench_case).label('bench')

    query = db.session.query(
        Player.name,
        total_col,
        starts_col,
        bench_col
    ).join(Appearance).group_by(Player.name)

    # Map string parameter to a valid SQLAlchemy sortable column
    sort_map = {
        'name': Player.name,
        'total': total_col,
        'starts': starts_col,
        'bench': bench_col,
    }
    sort_column = sort_map.get(sort_by, total_col)

    # Apply sorting to the query
    if order == 'asc':
        query = query.order_by(sort_column.asc())
    else:
        query = query.order_by(sort_column.desc())

    # Apply limit unless show=all is specified
    if not show_all:
        query = query.limit(100)

    player_stats = query.all()
    return render_template('stats.html', players=player_stats, sort_by=sort_by, order=order, show_all=show_all)


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
        if not _process_teamsheet_form(request.form, match):
            return redirect(url_for('edit_match', match_id=match_id))

        try:
            db.session.commit()
            flash('Match updated successfully.', 'success')
            return redirect(url_for('data_view'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating match: {e}', 'error')
            return redirect(url_for('edit_match', match_id=match_id))

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

@app.route('/duplicates')
@admin_required
def view_duplicates():
    """
    Finds and displays potential duplicate players in the database.
    """
    # A lower threshold is better for finding groups.
    # We will show the score in the UI so the admin can judge.
    threshold = 80 
    players = Player.query.order_by(Player.name).all()
    all_player_names = [p.name for p in players]
    
    duplicate_groups_of_names = []
    processed_names = set()

    for name in all_player_names:
        if name in processed_names:
            continue
        
        # Find all names that are similar to the current name
        matches = fuzz_process.extract(name, all_player_names, scorer=fuzz.token_sort_ratio)
        
        current_group = {m[0] for m in matches if m[1] >= threshold}
        
        if len(current_group) > 1:
            duplicate_groups_of_names.append(sorted(list(current_group)))
            processed_names.update(current_group)
            
    # For each group, get the detailed stats for each player
    detailed_groups = []
    all_names_in_groups = {name for group in duplicate_groups_of_names for name in group}

    if all_names_in_groups:
        # Fetch all stats in one go to avoid N+1 queries
        player_stats_map = {}
        stats_query = db.session.query(Player.name, func.count(Appearance.id)).join(Appearance).filter(Player.name.in_(all_names_in_groups)).group_by(Player.name).all()
        for name, count in stats_query:
            player_stats_map[name] = {'name': name, 'total': count}

        for group in duplicate_groups_of_names:
            detailed_group = []
            for name in group:
                # Use the pre-fetched stats, or default if player has no appearances
                detailed_group.append(player_stats_map.get(name, {'name': name, 'total': 0}))
            detailed_groups.append(detailed_group)
    return render_template('duplicates.html', detailed_groups=detailed_groups)

@app.route('/merge', methods=['GET'])
@admin_required
def merge_form():
    """
    Displays a form to merge a specific group of duplicate players.
    The group is identified by a list of names passed as a query parameter.
    """
    player_names_str = request.args.get('players', '')
    if not player_names_str:
        flash('No players specified for merging.', 'error')
        return redirect(url_for('view_duplicates'))

    player_names = [name.strip() for name in player_names_str.split(',') if name.strip()]
    
    # Fetch details for the players in the group
    players_in_group = Player.query.filter(Player.name.in_(player_names)).all()

    if len(players_in_group) < 2:
        flash('A merge operation requires at least two players.', 'info')
        return redirect(url_for('view_duplicates'))

    return render_template('merge_form.html', players=players_in_group)


@app.route('/merge', methods=['POST'])
@admin_required
def merge_players():
    """
    Handles the merging of player records.
    """
    names_to_merge = request.form.getlist('names_to_merge')
    canonical_name = request.form.get('canonical_name')

    if not canonical_name or not names_to_merge or len(names_to_merge) < 1:
        flash('You must select a correct name and at least one player to merge.', 'error')
        return redirect(request.referrer or url_for('view_duplicates'))

    if canonical_name not in names_to_merge:
        flash('The selected correct name must be one of the players being merged.', 'error')
        return redirect(request.referrer)

    # The canonical player is the one we keep
    canonical_player = Player.query.filter_by(name=canonical_name).first()
    
    # The players to be merged are all selected players except the canonical one
    players_to_remove = Player.query.filter(Player.name.in_(names_to_merge), Player.name != canonical_name).all()

    for player in players_to_remove:
        # Re-assign all appearances to the canonical player
        Appearance.query.filter_by(player_id=player.id).update({'player_id': canonical_player.id})
        db.session.delete(player)

    db.session.commit()
    flash(f'Successfully merged {len(players_to_remove)} player(s) into "{canonical_name}".', 'success')
    return redirect(url_for('view_duplicates'))

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
