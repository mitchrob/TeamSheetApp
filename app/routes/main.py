from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from sqlalchemy import case, func
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models import Appearance, Match, Player
from app.services import _collect_seasons, compute_season_stats, get_player_stats

bp = Blueprint('main', __name__)

@bp.route('/', methods=['GET'])
def index():
    recent_matches = Match.query.order_by(Match.date.desc()).limit(5).all()
    total_players = Player.query.count()
    total_matches = Match.query.count()
    seasons = _collect_seasons()
    current_season = compute_season_stats(seasons[0]) if seasons else None
    return render_template(
        'index.html',
        recent_matches=recent_matches,
        latest_match=recent_matches[0] if recent_matches else None,
        current_season=current_season,
        total_players=total_players,
        total_matches=total_matches,
    )

@bp.route('/stats', methods=['GET'])
def stats():
    sort_by = request.args.get('sort', 'total')
    order = request.args.get('order', 'desc')
    search_query = request.args.get('search', '')
    show_all = request.args.get('show') == 'all'
    season = request.args.get('season', '').strip()
    appearance_type = request.args.get('type', '').strip()

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
    ).join(Appearance).join(Match).group_by(Player.id, Player.name)

    if search_query:
        query = query.filter(Player.name.ilike(f'%{search_query}%'))
    if season:
        query = query.filter(Match.season == season)
    if appearance_type == 'start':
        query = query.filter(Appearance.position <= 15)
    elif appearance_type == 'replacement':
        query = query.filter(Appearance.position > 15)

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
    return render_template(
        'stats.html', players=player_stats, sort_by=sort_by, order=order, show_all=show_all,
        search_query=search_query, seasons=_collect_seasons(), selected_season=season,
        appearance_type=appearance_type,
    )

@bp.route('/data', methods=['GET'])
def data_view():
    season = request.args.get('season', '').strip()
    opponent = request.args.get('opponent', '').strip()
    location = request.args.get('location', '').strip()
    result = request.args.get('result', '').strip()
    query = Match.query.options(selectinload(Match.appearances))
    if season:
        query = query.filter(Match.season == season)
    if opponent:
        query = query.filter(Match.opposition.ilike(f'%{opponent}%'))
    if location:
        query = query.filter(Match.location == location)
    if result:
        query = query.filter(Match.result == result)
    matches = query.order_by(Match.date.desc()).all()
    for m in matches:
        m.app_count = len(m.appearances)
    locations = [row[0] for row in db.session.query(Match.location).filter(Match.location.isnot(None)).distinct().order_by(Match.location).all() if row[0]]
    return render_template(
        'data.html', matches=matches, seasons=_collect_seasons(), locations=locations,
        filters={'season': season, 'opponent': opponent, 'location': location, 'result': result},
    )


@bp.route("/match/<int:match_id>", methods=["GET"])
def match_view(match_id):
    match = (
        Match.query.options(selectinload(Match.appearances).joinedload(Appearance.player))
        .filter_by(id=match_id)
        .first_or_404()
    )
    lineup = {appearance.position: appearance.player for appearance in match.appearances}
    return render_template(
        "match.html",
        match=match,
        lineup=lineup,
        squad_size=current_app.config["MAX_SQUAD_SIZE"],
    )

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
