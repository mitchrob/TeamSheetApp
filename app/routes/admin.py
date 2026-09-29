import csv
import io
import secrets
from datetime import timedelta, timezone

from flask import (
    Blueprint,
    Response,
    current_app,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload
from thefuzz import fuzz
from thefuzz import process as fuzz_process
from werkzeug.security import generate_password_hash

from app.extensions import db
from app.forms import validate_match_form
from app.models import AdminUser, Appearance, AuditEvent, FixtureSyncRun, Match, Player, utc_now
from app.services import (
    SnapshotValidationError,
    approve_initial_run,
    find_potential_duplicates,
    reconciliation_candidates,
)
from app.utils import admin_required, normalize_username

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

    return {
        "league": last_match.league or "",
        "season": last_match.season,
        "date": "",
        "opposition": "",
        "location": last_match.location or "",
        "result": "",
        "guildford_points": "",
        "opposition_points": "",
        "players": [""] * squad_size,
    }


def _record_audit(action, entity_type, entity_id, description):
    db.session.add(
        AuditEvent(
            actor_user_id=g.admin_user.id if g.admin_user else None,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            description=description[:255],
        )
    )


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
        db.session.flush()
        _record_audit("create", "match", match.id, f"Created match against {match.opposition}")
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
    if match.source_provider:
        data.update(
            {
                "league": match.league,
                "season": match.season,
                "date": match.date,
                "opposition": match.opposition,
                "location": match.location,
                "result": match.result,
                "guildford_points": match.guildford_points,
                "opposition_points": match.opposition_points,
            }
        )
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
        _record_audit("edit", "match", match.id, f"Edited match against {match.opposition}")
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
        description = f"Deleted match against {match.opposition} on {match.date.isoformat()}"
        db.session.delete(match)
        _record_audit("delete", "match", match_id, description)
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


@bp.route("/admin/recent-lineups")
@admin_required
def recent_lineups():
    squad_size = current_app.config["MAX_SQUAD_SIZE"]
    matches = (
        Match.query.options(selectinload(Match.appearances).joinedload(Appearance.player))
        .order_by(Match.date.desc(), Match.id.desc())
        .limit(20)
        .all()
    )
    payload = []
    for match in matches:
        players = [""] * squad_size
        for appearance in match.appearances:
            if 1 <= appearance.position <= squad_size:
                players[appearance.position - 1] = appearance.player.name
        payload.append(
            {
                "id": match.id,
                "label": f"{match.date.strftime('%d/%m/%Y')} vs {match.opposition}",
                "players": players,
            }
        )
    return jsonify(payload)


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
        _record_audit(
            "merge",
            "player",
            canonical.id,
            f"Merged {len(players_to_remove)} player records into {canonical_name}",
        )
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Unable to merge players into %s", canonical_name)
        flash("The players could not be merged.", "error")
    else:
        flash(f'Successfully merged {len(players_to_remove)} player(s) into "{canonical_name}".', "success")
    return redirect(url_for("admin.view_duplicates"))


@bp.route("/admin/users", methods=["GET", "POST"])
@admin_required
def users():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        normalized = normalize_username(username)
        if not normalized:
            flash("Username is required.", "error")
        elif len(username) > 80:
            flash("Username must be 80 characters or fewer.", "error")
        elif AdminUser.query.filter_by(normalized_username=normalized).first():
            flash("That username is already in use.", "error")
        else:
            temporary_password = secrets.token_urlsafe(12)
            user = AdminUser(
                username=username,
                normalized_username=normalized,
                password_hash=generate_password_hash(temporary_password),
                must_change_password=True,
            )
            db.session.add(user)
            db.session.flush()
            _record_audit("create", "admin_user", user.id, f"Created administrator {user.username}")
            db.session.commit()
            if g.admin_user is None:
                session.pop("legacy_admin", None)
                session["admin_user_id"] = user.id
            flash(
                f"Administrator created. Temporary password for {user.username}: {temporary_password}",
                "success",
            )
            return redirect(url_for("admin.users"))
    accounts = AdminUser.query.order_by(AdminUser.username).all()
    return render_template("admin_users.html", accounts=accounts)


@bp.route("/admin/users/<int:user_id>/reset", methods=["POST"])
@admin_required
def reset_user_password(user_id):
    user = db.get_or_404(AdminUser, user_id)
    temporary_password = secrets.token_urlsafe(12)
    user.password_hash = generate_password_hash(temporary_password)
    user.must_change_password = True
    _record_audit("reset", "admin_user", user.id, f"Reset password for {user.username}")
    db.session.commit()
    flash(f"Temporary password for {user.username}: {temporary_password}", "success")
    return redirect(url_for("admin.users"))


@bp.route("/admin/users/<int:user_id>/toggle", methods=["POST"])
@admin_required
def toggle_user(user_id):
    user = db.get_or_404(AdminUser, user_id)
    if g.admin_user and user.id == g.admin_user.id:
        flash("You cannot deactivate your own account.", "error")
        return redirect(url_for("admin.users"))
    if user.is_active and AdminUser.query.filter_by(is_active=True).count() <= 1:
        flash("The final active administrator cannot be deactivated.", "error")
        return redirect(url_for("admin.users"))
    user.is_active = not user.is_active
    action = "activate" if user.is_active else "deactivate"
    _record_audit(action, "admin_user", user.id, f"{action.title()}d administrator {user.username}")
    db.session.commit()
    flash(f"{user.username} is now {'active' if user.is_active else 'inactive'}.", "success")
    return redirect(url_for("admin.users"))


@bp.route("/admin/activity")
@admin_required
def activity():
    events = AuditEvent.query.options(selectinload(AuditEvent.actor)).order_by(AuditEvent.created_at.desc()).limit(250).all()
    return render_template("activity.html", events=events)


@bp.route("/admin/fixtures")
@admin_required
def fixture_sync():
    pending_run = (
        FixtureSyncRun.query.filter_by(status="pending_review")
        .order_by(FixtureSyncRun.received_at.desc())
        .first()
    )
    latest_run = (
        FixtureSyncRun.query.filter_by(status="applied")
        .order_by(FixtureSyncRun.completed_at.desc())
        .first()
    )
    imported_matches = (
        Match.query.filter_by(source_provider="rfu-page")
        .order_by(Match.date.desc())
        .all()
    )
    missing_matches = []
    if latest_run:
        latest_ids = {item.external_match_id for item in latest_run.items}
        missing_matches = [
            match
            for match in imported_matches
            if match.season == latest_run.season and match.external_match_id not in latest_ids
        ]

    is_stale = True
    if latest_run and latest_run.completed_at:
        completed_at = latest_run.completed_at
        if completed_at.tzinfo is None:
            completed_at = completed_at.replace(tzinfo=timezone.utc)
        is_stale = utc_now() - completed_at > timedelta(hours=current_app.config["RFU_SYNC_STALE_HOURS"])

    return render_template(
        "fixture_sync.html",
        pending_run=pending_run,
        latest_run=latest_run,
        imported_matches=imported_matches,
        missing_matches=missing_matches,
        candidates=reconciliation_candidates(pending_run) if pending_run else [],
        is_stale=is_stale,
        workflow_url=current_app.config.get("RFU_GITHUB_WORKFLOW_URL"),
        configured=bool(current_app.config.get("RFU_SYNC_SECRET")),
    )


@bp.route("/admin/fixtures/<int:run_id>/approve", methods=["POST"])
@admin_required
def approve_fixture_sync(run_id):
    run = db.get_or_404(FixtureSyncRun, run_id)
    choices = {item.id: request.form.get(f"item_{item.id}", "") for item in run.items}
    try:
        approve_initial_run(run, choices)
        _record_audit(
            "approve",
            "fixture_sync_run",
            run.id,
            f"Approved RFU import: {run.created_count} created and {run.updated_count} linked",
        )
        db.session.commit()
    except SnapshotValidationError as exc:
        db.session.rollback()
        flash(str(exc), "error")
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Unable to approve RFU synchronization run %s", run_id)
        flash("The RFU import could not be approved.", "error")
    else:
        flash("RFU fixtures imported successfully.", "success")
    return redirect(url_for("admin.fixture_sync"))


@bp.route("/admin/data-quality")
@admin_required
def data_quality():
    season = request.args.get("season", "").strip()
    completeness = request.args.get("completeness", "").strip()
    opponent = request.args.get("opponent", "").strip()
    result = request.args.get("result", "").strip()
    query = Match.query.options(selectinload(Match.appearances))
    if season:
        query = query.filter(Match.season == season)
    if opponent:
        query = query.filter(Match.opposition.ilike(f"%{opponent}%"))
    if result:
        query = query.filter(Match.result == result)
    matches = query.order_by(Match.date.desc()).all()
    rows = []
    squad_size = current_app.config["MAX_SQUAD_SIZE"]
    for match in matches:
        if match.fixture_status in {"scheduled", "postponed", "cancelled"}:
            continue
        issues = []
        if len(match.appearances) < squad_size:
            issues.append(f"Incomplete teamsheet ({len(match.appearances)}/{squad_size})")
        if match.guildford_points is None or match.opposition_points is None:
            issues.append("Missing score")
        if not match.season or not match.opposition or not match.date:
            issues.append("Empty required field")
        if not issues:
            continue
        if completeness == "teamsheet" and not any("teamsheet" in issue for issue in issues):
            continue
        if completeness == "score" and "Missing score" not in issues:
            continue
        rows.append({"match": match, "issues": issues})

    names = [player.name for player in Player.query.order_by(Player.name).all()]
    duplicate_pairs = []
    for index, name in enumerate(names):
        for other in names[index + 1:]:
            score = fuzz.token_sort_ratio(name, other)
            if score >= 90:
                duplicate_pairs.append((name, other, score))
    seasons = [row[0] for row in db.session.query(Match.season).distinct().order_by(Match.season.desc()).all()]
    return render_template(
        "data_quality.html", rows=rows, duplicate_pairs=duplicate_pairs, seasons=seasons,
        filters={"season": season, "completeness": completeness, "opponent": opponent, "result": result},
    )


def _csv_response(filename, headers, rows):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerows(rows)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@bp.route("/admin/export/matches.csv")
@admin_required
def export_matches():
    rows = (
        (match.id, match.date.isoformat(), match.season, match.league or "", match.opposition,
         match.location or "", match.result or "", match.guildford_points if match.guildford_points is not None else "",
         match.opposition_points if match.opposition_points is not None else "", match.fixture_status,
         match.source_provider or "", match.source_url or "")
        for match in Match.query.order_by(Match.date, Match.id).all()
    )
    return _csv_response("matches.csv", ["id", "date", "season", "league", "opposition", "location", "result", "guildford_points", "opposition_points", "fixture_status", "source_provider", "source_url"], rows)


@bp.route("/admin/export/appearances.csv")
@admin_required
def export_appearances():
    appearances = Appearance.query.options(selectinload(Appearance.player), selectinload(Appearance.match)).order_by(Appearance.match_id, Appearance.position).all()
    rows = ((item.id, item.match_id, item.match.date.isoformat(), item.player_id, item.player.name, item.position, "Start" if item.position <= 15 else "Replacement") for item in appearances)
    return _csv_response("appearances.csv", ["id", "match_id", "date", "player_id", "player_name", "position", "appearance_type"], rows)


@bp.route("/admin/export/players.csv")
@admin_required
def export_players():
    players = Player.query.options(selectinload(Player.appearances)).order_by(Player.name).all()
    rows = ((player.id, player.name, len(player.appearances), sum(1 for item in player.appearances if item.position <= 15), sum(1 for item in player.appearances if item.position > 15)) for player in players)
    return _csv_response("players.csv", ["id", "name", "appearances", "starts", "replacements"], rows)
