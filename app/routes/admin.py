from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from app.extensions import db
from app.models import Match, Player, Appearance
from app.utils import admin_required, parse_date_safe
from app.services import find_potential_duplicates, _collect_seasons
from app.services import find_potential_duplicates, _collect_seasons

from sqlalchemy import func
from collections import Counter

bp = Blueprint('admin', __name__)

def get_most_recent_teamsheet_from_db():
    defaults = {
        'league': '', 'season': '', 'date': '', 'opposition': '', 'location': '',
        'result': '', 'guildford_points': '', 'opposition_points': '',
        'players': [''] * 20
    }
    
    last_match = Match.query.order_by(Match.date.desc()).first()
    if not last_match:
        return defaults

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

def _process_teamsheet_form(form_data, match_obj=None):
    player_names = [form_data.get(f'player{i}', '').strip() for i in range(1, 21)]

    non_empty_players = [name for name in player_names if name]
    player_counts = Counter(non_empty_players)
    duplicates = [name for name, count in player_counts.items() if count > 1]
    if duplicates:
        flash(f'The teamsheet contains duplicate players: {", ".join(duplicates)}. Please correct and resubmit.', 'error')
        return None

    all_player_names_in_db = [p.name for p in Player.query.all()]
    fuzzy_errors = find_potential_duplicates(non_empty_players, all_player_names_in_db)
    if fuzzy_errors:
        for error in fuzzy_errors:
            flash(error, 'error')
        return None

    if match_obj:
        Appearance.query.filter_by(match_id=match_obj.id).delete()

    for i, name in enumerate(player_names):
        if not name:
            continue
        
        player = Player.query.filter_by(name=name).first()
        if not player:
            player = Player(name=name)
            db.session.add(player)
        
        appearance = Appearance(
            player=player, 
            match=match_obj, 
            position=i + 1
        )
        db.session.add(appearance)
    
    return True

@bp.route('/add', methods=['GET'])
@admin_required
def add():
    defaults = get_most_recent_teamsheet_from_db()
    return render_template('add.html', defaults=defaults)

@bp.route('/add', methods=['POST'])
@admin_required
def add_post():
    league = request.form.get('league', '').strip()
    date_str = request.form.get('date', '').strip()

    match_date = parse_date_safe(date_str)
    if not match_date:
        flash('Invalid date format. Please use dd/mm/yyyy.', 'error')
        return redirect(url_for('admin.add'))

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
            return redirect(url_for('admin.add'))

        db.session.commit()
        flash('Teamsheet added successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding teamsheet: {e}', 'error')
        return redirect(url_for('admin.add'))
    return redirect(url_for('main.stats'))

@bp.route('/edit/<int:match_id>', methods=['GET', 'POST'])
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

        if not _process_teamsheet_form(request.form, match):
            return redirect(url_for('admin.edit_match', match_id=match_id))

        try:
            db.session.commit()
            flash('Match updated successfully.', 'success')
            return redirect(url_for('main.data_view'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating match: {e}', 'error')
            return redirect(url_for('admin.edit_match', match_id=match_id))

    players = [''] * 20
    for ap in match.appearances:
        if 1 <= ap.position <= 20:
            players[ap.position - 1] = ap.player.name
    
    return render_template('edit.html', match=match, players=players)

@bp.route('/delete/<int:match_id>', methods=['POST'])
@admin_required
def delete_match(match_id):
    match = Match.query.get_or_404(match_id)
    db.session.delete(match)
    db.session.commit()
    flash('Match deleted successfully.', 'success')
    return redirect(url_for('main.data_view'))

@bp.route('/player_names', methods=['GET'])
@admin_required
def player_names():
    # Return list of {name, count} for all players
    # We can use a group by query or just iterate if dataset is small. 
    # Use database aggregation for efficiency.
    stats = db.session.query(Player.name, func.count(Appearance.id))\
        .outerjoin(Appearance)\
        .group_by(Player.id, Player.name)\
        .order_by(Player.name)\
        .all()
    
    # stats is list of (name, count)
    data = [{'name': name, 'count': count} for name, count in stats]
    return jsonify(data)

@bp.route('/duplicates')
@admin_required
def view_duplicates():
    threshold = 80 
    players = Player.query.order_by(Player.name).all()
    all_player_names = [p.name for p in players]
    
    # We can probably move this logic to logic.py/services.py if we want, but for now it's fine
    from thefuzz import process as fuzz_process, fuzz
    duplicate_groups_of_names = []
    processed_names = set()

    for name in all_player_names:
        if name in processed_names:
            continue
        matches = fuzz_process.extract(name, all_player_names, scorer=fuzz.token_sort_ratio)
        current_group = {m[0] for m in matches if m[1] >= threshold}
        
        if len(current_group) > 1:
            duplicate_groups_of_names.append(sorted(list(current_group)))
            processed_names.update(current_group)
            
    detailed_groups = []
    all_names_in_groups = {name for group in duplicate_groups_of_names for name in group}

    if all_names_in_groups:
        player_stats_map = {}
        stats_query = db.session.query(Player.name, func.count(Appearance.id)).join(Appearance).filter(Player.name.in_(all_names_in_groups)).group_by(Player.name).all()
        for name, count in stats_query:
            player_stats_map[name] = {'name': name, 'total': count}

        for group in duplicate_groups_of_names:
            detailed_group = []
            for name in group:
                detailed_group.append(player_stats_map.get(name, {'name': name, 'total': 0}))
            detailed_groups.append(detailed_group)
    return render_template('duplicates.html', detailed_groups=detailed_groups)

@bp.route('/merge', methods=['GET'])
@admin_required
def merge_form():
    player_names_str = request.args.get('players', '')
    if not player_names_str:
        flash('No players specified for merging.', 'error')
        return redirect(url_for('admin.view_duplicates'))

    player_names = [name.strip() for name in player_names_str.split(',') if name.strip()]
    players_in_group = Player.query.filter(Player.name.in_(player_names)).all()

    if len(players_in_group) < 2:
        flash('A merge operation requires at least two players.', 'info')
        return redirect(url_for('admin.view_duplicates'))

    return render_template('merge_form.html', players=players_in_group)


@bp.route('/merge', methods=['POST'])
@admin_required
def merge_players():
    names_to_merge = request.form.getlist('names_to_merge')
    canonical_name = request.form.get('canonical_name')

    if not canonical_name or not names_to_merge or len(names_to_merge) < 1:
        flash('You must select a correct name and at least one player to merge.', 'error')
        return redirect(request.referrer or url_for('admin.view_duplicates'))

    if canonical_name not in names_to_merge:
        flash('The selected correct name must be one of the players being merged.', 'error')
        return redirect(request.referrer)

    canonical_player = Player.query.filter_by(name=canonical_name).first()
    players_to_remove = Player.query.filter(Player.name.in_(names_to_merge), Player.name != canonical_name).all()

    for player in players_to_remove:
        # Re-assign all appearances
        Appearance.query.filter_by(player_id=player.id).update({'player_id': canonical_player.id})
        db.session.delete(player)

    db.session.commit()
    flash(f'Successfully merged {len(players_to_remove)} player(s) into "{canonical_name}".', 'success')
    return redirect(url_for('admin.view_duplicates'))


