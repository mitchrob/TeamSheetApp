from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.extensions import db
from app.models import Player, Match, Appearance
from app.services import compute_season_stats, get_player_stats, _collect_seasons
from sqlalchemy import func, case

bp = Blueprint('main', __name__)

@bp.route('/', methods=['GET'])
def index():
    # Per plan for Phase 1, just partial parity but moving towards Dashboard
    # Task says: "Instead of redirecting to /add ... create a Dashboard"
    # I will implement the Dashboard now as requested by user.
    
    recent_matches = Match.query.order_by(Match.date.desc()).limit(5).all()
    # Simple summary stats could be added here
    total_players = Player.query.count()
    total_matches = Match.query.count()
    
    return render_template('index.html', recent_matches=recent_matches, total_players=total_players, total_matches=total_matches)

@bp.route('/stats', methods=['GET'])
def stats():
    sort_by = request.args.get('sort', 'total')
    order = request.args.get('order', 'desc')
    search_query = request.args.get('search', '')
    show_all = request.args.get('show') == 'all'

    starts_case = case((Appearance.position <= 15, 1), else_=0)
    bench_case = case((Appearance.position > 15, 1), else_=0)

    total_col = func.count(Appearance.id).label('total')
    starts_col = func.sum(starts_case).label('starts')
    bench_col = func.sum(bench_case).label('bench')

    query = db.session.query(
        Player.name,
        total_col,
        starts_col,
        bench_col
    ).join(Appearance).group_by(Player.name)

    if search_query:
        query = query.filter(Player.name.ilike(f'%{search_query}%'))

    sort_map = {
        'name': Player.name,
        'total': total_col,
        'starts': starts_col,
        'bench': bench_col,
    }
    sort_column = sort_map.get(sort_by, total_col)

    if order == 'asc':
        query = query.order_by(sort_column.asc())
    else:
        query = query.order_by(sort_column.desc())

    if not show_all:
        query = query.limit(100)

    player_stats = query.all()
    return render_template('stats.html', players=player_stats, sort_by=sort_by, order=order, show_all=show_all, search_query=search_query)

@bp.route('/data', methods=['GET'])
def data_view():
    matches = Match.query.order_by(Match.date.desc()).all()
    # Explicitly count appearances to avoid template lazy loading issues
    for m in matches:
        m.app_count = len(m.appearances)
    return render_template('data.html', matches=matches)

@bp.route('/season', methods=['GET'])
def season_view():
    # Needed to fetch seasons for default if param missing
    all_seasons = _collect_seasons()
    if not all_seasons:
        flash('No season data available', 'error')
        return redirect(url_for('main.stats'))
    
    season = request.args.get('season') or all_seasons[0]
    stats = compute_season_stats(season)
    if stats is None:
        flash('No data for that season', 'error')
        return redirect(url_for('main.stats'))
    return render_template('season.html', stats=stats)

@bp.route('/player', methods=['GET'])
def player_view():
    name = request.args.get('name')
    if not name:
        flash('Missing player name', 'error')
        return redirect(url_for('main.stats'))
    name = name.strip()
    stats = get_player_stats(name)
    if not stats:
        flash(f'No appearances found for {name}', 'error')
        return redirect(url_for('main.stats'))
    return render_template('player.html', stats=stats)
