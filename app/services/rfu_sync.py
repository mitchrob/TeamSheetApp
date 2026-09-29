import re
import unicodedata
from datetime import date, datetime, timezone
from urllib.parse import parse_qs, urlparse

from app.extensions import db
from app.models import AuditEvent, FixtureImportItem, FixtureSyncRun, Match, utc_now
from app.services.core import canonicalize_season, normalize_result

ALLOWED_STATUSES = {"scheduled", "completed", "postponed", "cancelled", "unknown"}
RFU_SOURCE = "rfu-page"


class SnapshotValidationError(ValueError):
    pass


class ReplayError(ValueError):
    pass


def validate_snapshot(payload, *, team_id="9045", max_matches=100):
    if not isinstance(payload, dict):
        raise SnapshotValidationError("The request body must be a JSON object.")
    if payload.get("source") != RFU_SOURCE:
        raise SnapshotValidationError("The snapshot source is invalid.")

    season = canonicalize_season(payload.get("season"))
    if not season:
        raise SnapshotValidationError("The snapshot season is invalid.")
    scraped_at = _parse_timestamp(payload.get("scraped_at"))
    raw_matches = payload.get("matches")
    if not isinstance(raw_matches, list) or not raw_matches or len(raw_matches) > max_matches:
        raise SnapshotValidationError("The snapshot contains an invalid number of matches.")

    matches = []
    seen_ids = set()
    for index, raw in enumerate(raw_matches, start=1):
        try:
            item = _validate_match(raw, season=season, team_id=str(team_id))
        except SnapshotValidationError as exc:
            raise SnapshotValidationError(f"Match {index}: {exc}") from exc
        if item["external_match_id"] in seen_ids:
            raise SnapshotValidationError("The snapshot contains a duplicate match ID.")
        seen_ids.add(item["external_match_id"])
        matches.append(item)

    return {"season": season, "scraped_at": scraped_at, "matches": matches}


def ingest_snapshot(snapshot, run_id):
    if FixtureSyncRun.query.filter_by(run_id=run_id).first():
        raise ReplayError("This synchronization run has already been received.")

    season = snapshot["season"]
    first_import = not Match.query.filter_by(source_provider=RFU_SOURCE, season=season).first()
    if first_import:
        FixtureSyncRun.query.filter_by(season=season, status="pending_review").update(
            {FixtureSyncRun.status: "superseded"}, synchronize_session=False
        )

    run = FixtureSyncRun(
        run_id=run_id,
        season=season,
        scraped_at=snapshot["scraped_at"],
        status="pending_review" if first_import else "applied",
    )
    db.session.add(run)
    db.session.flush()

    for data in snapshot["matches"]:
        action, matched, issue = _suggest_reconciliation(data) if first_import else ("create", None, None)
        item = FixtureImportItem(
            sync_run=run,
            proposed_action=action,
            matched_match=matched,
            issue=issue,
            **data,
        )
        db.session.add(item)

    db.session.flush()
    if first_import:
        run.conflict_count = sum(item.proposed_action == "conflict" for item in run.items)
        _record_sync_audit(run, "stage", f"Staged {len(run.items)} RFU fixtures for review")
        return run

    _apply_automatic_run(run)
    _record_sync_audit(
        run,
        "sync",
        f"RFU sync: {run.created_count} created, {run.updated_count} updated, "
        f"{run.unchanged_count} unchanged, {run.missing_count} missing",
    )
    return run


def approve_initial_run(run, choices):
    if run.status != "pending_review":
        raise SnapshotValidationError("This synchronization run is no longer awaiting review.")

    selected_match_ids = set()
    resolved = []
    for item in run.items:
        choice = choices.get(item.id)
        if not choice:
            if item.proposed_action == "link" and item.matched_match_id:
                choice = f"match:{item.matched_match_id}"
            elif item.proposed_action == "create":
                choice = "create"
            else:
                raise SnapshotValidationError(f"Choose how to reconcile RFU match {item.external_match_id}.")

        if choice == "create":
            resolved.append((item, None))
            continue
        if not choice.startswith("match:") or not choice[6:].isdigit():
            raise SnapshotValidationError("A reconciliation selection is invalid.")
        match_id = int(choice[6:])
        match = db.session.get(Match, match_id)
        if not match or match.season != run.season or match.source_provider is not None:
            raise SnapshotValidationError("A selected existing match is not available for linking.")
        if match_id in selected_match_ids:
            raise SnapshotValidationError("An existing match cannot be linked to two RFU fixtures.")
        selected_match_ids.add(match_id)
        resolved.append((item, match))

    for item, match in resolved:
        if match is None:
            match = Match()
            db.session.add(match)
            run.created_count += 1
        else:
            run.updated_count += 1
        _copy_item_to_match(item, match, run.scraped_at)
        item.matched_match = match

    run.status = "applied"
    run.completed_at = utc_now()
    run.conflict_count = 0
    run.missing_count = _count_missing(run)
    return run


def reconciliation_candidates(run):
    return (
        Match.query.filter_by(season=run.season, source_provider=None)
        .order_by(Match.date, Match.opposition)
        .all()
    )


def _apply_automatic_run(run):
    for item in run.items:
        match = Match.query.filter_by(
            source_provider=RFU_SOURCE, external_match_id=item.external_match_id
        ).first()
        if match is None:
            match = Match()
            db.session.add(match)
            run.created_count += 1
        else:
            changed = _source_fields_changed(match, item)
            if changed:
                run.updated_count += 1
            else:
                run.unchanged_count += 1
        _copy_item_to_match(item, match, run.scraped_at)
        item.matched_match = match

    run.completed_at = utc_now()
    run.missing_count = _count_missing(run)


def _count_missing(run):
    incoming = {item.external_match_id for item in run.items}
    existing = {
        external_id
        for (external_id,) in db.session.query(Match.external_match_id)
        .filter(Match.source_provider == RFU_SOURCE, Match.season == run.season)
        .all()
        if external_id
    }
    return len(existing - incoming)


def _copy_item_to_match(item, match, scraped_at):
    match.league = item.league
    match.season = item.season
    match.date = item.date
    match.opposition = item.opposition
    match.location = item.location
    match.result = item.result
    match.guildford_points = item.guildford_points
    match.opposition_points = item.opposition_points
    match.source_provider = RFU_SOURCE
    match.external_match_id = item.external_match_id
    match.source_url = item.source_url
    match.fixture_status = item.fixture_status
    match.source_updated_at = scraped_at
    match.last_synced_at = scraped_at


def _source_fields_changed(match, item):
    fields = (
        "league",
        "season",
        "date",
        "opposition",
        "location",
        "result",
        "guildford_points",
        "opposition_points",
        "source_url",
        "fixture_status",
    )
    return any(getattr(match, field) != getattr(item, field) for field in fields)


def _suggest_reconciliation(data):
    possible = Match.query.filter_by(season=data["season"], date=data["date"], source_provider=None).all()
    matches = [
        match
        for match in possible
        if _identity(match.opposition) == _identity(data["opposition"])
        and (match.location or "").strip().casefold() == data["location"].casefold()
    ]
    if len(matches) == 1:
        return "link", matches[0], None
    if len(matches) > 1:
        return "conflict", None, "More than one existing match has the same date, opponent, and location."
    return "create", None, None


def _validate_match(raw, *, season, team_id):
    if not isinstance(raw, dict):
        raise SnapshotValidationError("The match must be an object.")
    external_id = str(raw.get("external_match_id", "")).strip()
    if not re.fullmatch(r"\d{1,40}", external_id):
        raise SnapshotValidationError("The external match ID is invalid.")

    item_season = canonicalize_season(raw.get("season"))
    if item_season != season:
        raise SnapshotValidationError("The match season does not match the snapshot.")
    try:
        match_date = date.fromisoformat(str(raw.get("date", "")))
    except ValueError as exc:
        raise SnapshotValidationError("The match date is invalid.") from exc

    opposition = _bounded_text(raw.get("opposition"), "opposition", 100, required=True)
    league = _bounded_text(raw.get("league"), "league", 100, required=False)
    location = str(raw.get("location", "")).strip()
    if location not in {"Home", "Away"}:
        raise SnapshotValidationError("The location must be Home or Away.")

    guildford_points = _score(raw.get("guildford_points"), "Guildford score")
    opposition_points = _score(raw.get("opposition_points"), "Opposition score")
    if (guildford_points is None) != (opposition_points is None):
        raise SnapshotValidationError("Both scores must be supplied together.")

    status = str(raw.get("status", "unknown")).strip().lower()
    if status not in ALLOWED_STATUSES:
        raise SnapshotValidationError("The fixture status is invalid.")
    if guildford_points is not None and status not in {"cancelled", "postponed"}:
        status = "completed"

    source_url = _validate_source_url(raw.get("source_url"), external_id, team_id)
    return {
        "external_match_id": external_id,
        "season": season,
        "date": match_date,
        "league": league,
        "opposition": opposition,
        "location": location,
        "result": normalize_result(None, guildford_points, opposition_points),
        "guildford_points": guildford_points,
        "opposition_points": opposition_points,
        "fixture_status": status,
        "source_url": source_url,
    }


def _validate_source_url(value, external_id, team_id):
    url = str(value or "").strip()
    if len(url) > 500:
        raise SnapshotValidationError("The RFU source URL is too long.")
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in {"englandrugby.com", "www.englandrugby.com"}
        or parsed.path != "/fixtures-and-results/match-centre-community"
    ):
        raise SnapshotValidationError("The RFU source URL is invalid.")
    query = parse_qs(parsed.query)
    if query.get("matchId") != [external_id] or query.get("team") != [team_id]:
        raise SnapshotValidationError("The RFU source URL does not match the fixture identity.")
    return url


def _parse_timestamp(value):
    if not isinstance(value, str):
        raise SnapshotValidationError("The scrape timestamp is invalid.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SnapshotValidationError("The scrape timestamp is invalid.") from exc
    if parsed.tzinfo is None:
        raise SnapshotValidationError("The scrape timestamp must include a timezone.")
    parsed = parsed.astimezone(timezone.utc)
    age_seconds = (datetime.now(timezone.utc) - parsed).total_seconds()
    if age_seconds < -300 or age_seconds > 86_400:
        raise SnapshotValidationError("The scrape timestamp is outside the accepted window.")
    return parsed


def _bounded_text(value, label, limit, *, required):
    text = str(value or "").strip()
    if required and not text:
        raise SnapshotValidationError(f"The {label} is required.")
    if len(text) > limit:
        raise SnapshotValidationError(f"The {label} is too long.")
    return text or None


def _score(value, label):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 999:
        raise SnapshotValidationError(f"The {label} is invalid.")
    return value


def _identity(value):
    normalized = unicodedata.normalize("NFKC", value or "").casefold()
    return " ".join(re.findall(r"[a-z0-9]+", normalized))


def _record_sync_audit(run, action, description):
    db.session.add(
        AuditEvent(
            actor_user_id=None,
            action=f"rfu_{action}",
            entity_type="fixture_sync_run",
            entity_id=str(run.id),
            description=description[:255],
        )
    )
