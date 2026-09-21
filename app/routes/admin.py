from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from thefuzz import fuzz
from thefuzz import process as fuzz_process

from app.extensions import db
from app.forms import validate_match_form
from app.models import Appearance, Match, Player
from app.services import find_potential_duplicates
from app.utils import admin_required

bp = Blueprint("admin", __name__)


def get_most_recent_teamsheet_from_db():
    squad_size = current_app.config["MAX_SQUAD_SIZE"]
    defaults = {
        "league": "",
        "season": "",
        "date": "",
        "opposition": "",
        "location": "",
        "result": "",
        "guildford_points": "",
        "opposition_points": "",
        "players": [""] * squad_size,
    }
    last_match = Match.query.order_by(Match.date.desc()).first()
    if not last_match:
        return defaults

    players = [""] * squad_size
    for appearance in last_match.appearances:
        if 1 <= appearance.position <= squad_size:
            players[appearance.position - 1] = appearance.player.name
    return {
        "league": last_match.league or "",
        "season": last_match.season,
        "date": last_match.date.isoformat(),
        "opposition": last_match.opposition,
        "location": last_match.location or "",
        "result": last_match.result or "",
        "guildford_points": last_match.guildford_points if last_match.guildford_points is not None else "",
        "opposition_points": last_match.opposition_points if last_match.opposition_points is not None else "",
        "players": players,
    }


def _validate_and_prepare_form():
    squad_size = current_app.config["MAX_SQUAD_SIZE"]
    data, players, values, errors = validate_match_form(request.form, squad_size)
    existing_names = [player.name for player in Player.query.all()]
    errors.extend(find_potential_duplicates([name for name in players if name], existing_names))
    return data, players, values, errors


def _replace_appearances(match, player_names):
    if match.id is not None:
        for appearance in list(match.appearances):
            db.session.delete(appearance)
        db.session.flush()
    for position, name in enumerate(player_names, start=1):
        if not name:
            continue
        player = Player.query.filter_by(name=name).first()
        if not player:
            player = Player(name=name)
            db.session.add(player)
        db.session.add(Appearance(player=player, match=match, position=position))


@bp.route("/add", methods=["GET", "POST"])
@admin_required
def add():
    if request.method == "GET":
        return render_template(
            "add.html", defaults=get_most_recent_teamsheet_from_db(), squad_size=current_app.config["MAX_SQUAD_SIZE"]
        )

    data, players, values, errors = _validate_and_prepare_form()
    if errors:
        for error in errors:
            flash(error, "error")
        return render_template("add.html", defaults=values, squad_size=len(players)), 400

    try:
        match = Match(**data)
        db.session.add(match)
        _replace_appearances(match, players)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Unable to add teamsheet")
        flash("The teamsheet could not be saved. Please try again.", "error")
        return render_template("add.html", defaults=values, squad_size=len(players)), 500

    flash("Teamsheet added successfully.", "success")
    return redirect(url_for("main.stats"))


@bp.route("/edit/<int:match_id>", methods=["GET", "POST"])
@admin_required
def edit_match(match_id):
    match = db.get_or_404(Match, match_id)
    squad_size = current_app.config["MAX_SQUAD_SIZE"]

    if request.method == "GET":
        players = [""] * squad_size
        for appearance in match.appearances:
            if 1 <= appearance.position <= squad_size:
                players[appearance.position - 1] = appearance.player.name
        values = {
            "league": match.league or "",
            "season": match.season,
            "date": match.date.isoformat(),
            "opposition": match.opposition,
            "location": match.location or "",
            "result": match.result or "",
            "guildford_points": match.guildford_points if match.guildford_points is not None else "",
            "opposition_points": match.opposition_points if match.opposition_points is not None else "",
            "players": players,
        }
        return render_template("edit.html", match=match, values=values, players=players, squad_size=squad_size)

    data, players, values, errors = _validate_and_prepare_form()
    if errors:
        for error in errors:
            flash(error, "error")
        return render_template(
            "edit.html", match=match, players=players, values=values, squad_size=squad_size
        ), 400

    try:
        for field, value in data.items():
            setattr(match, field, value)
        _replace_appearances(match, players)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Unable to update match %s", match_id)
        flash("The teamsheet could not be updated. Please try again.", "error")
        return render_template(
            "edit.html", match=match, players=players, values=values, squad_size=squad_size
        ), 500

    flash("Match updated successfully.", "success")
    return redirect(url_for("main.data_view"))


@bp.route("/delete/<int:match_id>", methods=["POST"])
@admin_required
def delete_match(match_id):
    match = db.get_or_404(Match, match_id)
    try:
        db.session.delete(match)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Unable to delete match %s", match_id)
        flash("The match could not be deleted.", "error")
    else:
        flash("Match deleted successfully.", "success")
    return redirect(url_for("main.data_view"))


@bp.route("/player_names")
@admin_required
def player_names():
    stats = (
        db.session.query(Player.name, func.count(Appearance.id))
        .outerjoin(Appearance)
        .group_by(Player.id, Player.name)
        .order_by(Player.name)
        .all()
    )
    return jsonify([{"name": name, "count": count} for name, count in stats])


@bp.route("/duplicates")
@admin_required
def view_duplicates():
    all_names = [player.name for player in Player.query.order_by(Player.name).all()]
    groups = []
    processed = set()
    for name in all_names:
        if name in processed:
            continue
        group = {item[0] for item in fuzz_process.extract(name, all_names, scorer=fuzz.token_sort_ratio) if item[1] >= 80}
        if len(group) > 1:
            groups.append(sorted(group))
            processed.update(group)

    grouped_names = {name for group in groups for name in group}
    counts = dict(
        db.session.query(Player.name, func.count(Appearance.id))
        .outerjoin(Appearance)
        .filter(Player.name.in_(grouped_names))
        .group_by(Player.name)
        .all()
    )
    detailed_groups = [[{"name": name, "total": counts.get(name, 0)} for name in group] for group in groups]
    return render_template("duplicates.html", detailed_groups=detailed_groups)


@bp.route("/merge", methods=["GET"])
@admin_required
def merge_form():
    names = [name.strip() for name in request.args.get("players", "").split(",") if name.strip()]
    players = Player.query.filter(Player.name.in_(names)).all()
    if len(players) < 2:
        flash("A merge requires at least two existing players.", "error")
        return redirect(url_for("admin.view_duplicates"))
    return render_template("merge_form.html", players=players)


@bp.route("/merge", methods=["POST"])
@admin_required
def merge_players():
    names = list(dict.fromkeys(request.form.getlist("names_to_merge")))
    canonical_name = request.form.get("canonical_name", "")
    if len(names) < 2 or canonical_name not in names:
        flash("Select at least two players and choose one of them as the correct name.", "error")
        return redirect(url_for("admin.view_duplicates"))

    canonical = Player.query.filter_by(name=canonical_name).first()
    if not canonical:
        flash("The selected player no longer exists.", "error")
        return redirect(url_for("admin.view_duplicates"))

    players_to_remove = Player.query.filter(Player.name.in_(names), Player.id != canonical.id).all()
    try:
        for player in players_to_remove:
            for appearance in list(player.appearances):
                conflict = Appearance.query.filter_by(player_id=canonical.id, match_id=appearance.match_id).first()
                if conflict:
                    db.session.delete(appearance)
                else:
                    appearance.player = canonical
            db.session.delete(player)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Unable to merge players into %s", canonical_name)
        flash("The players could not be merged.", "error")
    else:
        flash(f'Successfully merged {len(players_to_remove)} player(s) into "{canonical_name}".', "success")
    return redirect(url_for("admin.view_duplicates"))
