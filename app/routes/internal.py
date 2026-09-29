import hashlib
import hmac
import io
import json
import re
import time

from flask import Blueprint, current_app, jsonify, request, send_file
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import csrf, db, limiter
from app.services import ReplayError, SnapshotValidationError, ingest_snapshot, validate_snapshot
from app.services.database_backup import DatabaseBackupError, create_database_backup

bp = Blueprint("internal", __name__)


@bp.route("/internal/database-backup", methods=["POST"])
@csrf.exempt
@limiter.limit("5 per hour")
def database_backup():
    secret = current_app.config.get("DATABASE_BACKUP_SECRET")
    if not secret:
        return jsonify(error="Database backups are not configured."), 503
    if request.content_length not in (None, 0):
        return jsonify(error="The backup request must not contain a body."), 400

    run_id = request.headers.get("X-Backup-Run-ID", "")
    timestamp_text = request.headers.get("X-Backup-Timestamp", "")
    signature = request.headers.get("X-Backup-Signature", "")
    if not re.fullmatch(r"[A-Za-z0-9._:-]{1,100}", run_id) or not timestamp_text.isdigit():
        return jsonify(error="Invalid backup authentication."), 401

    timestamp = int(timestamp_text)
    if abs(int(time.time()) - timestamp) > current_app.config["DATABASE_BACKUP_MAX_AGE_SECONDS"]:
        return jsonify(error="The backup request has expired."), 401

    message = f"{timestamp_text}\n{run_id}\n{request.method}\n{request.path}\n".encode()
    expected = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    supplied = signature.removeprefix("sha256=")
    if not hmac.compare_digest(expected, supplied):
        return jsonify(error="Invalid backup authentication."), 401

    try:
        snapshot, digest = create_database_backup()
    except DatabaseBackupError:
        current_app.logger.exception("Unable to serve the database backup for run %s", run_id)
        return jsonify(error="The database backup could not be created."), 500

    download_name = f"teamsheet-{time.strftime('%Y%m%d-%H%M%S', time.gmtime())}.db"
    response = send_file(
        io.BytesIO(snapshot),
        as_attachment=True,
        download_name=download_name,
        mimetype="application/vnd.sqlite3",
        conditional=False,
    )
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["X-Backup-SHA256"] = digest
    return response


@bp.route("/internal/rfu-sync", methods=["POST"])
@csrf.exempt
@limiter.limit("10 per hour")
def rfu_sync():
    secret = current_app.config.get("RFU_SYNC_SECRET")
    if not secret:
        return jsonify(error="RFU synchronization is not configured."), 503
    if request.content_length is None or request.content_length > current_app.config["RFU_SYNC_MAX_BODY_BYTES"]:
        return jsonify(error="The synchronization payload is too large."), 413

    body = request.get_data(cache=True)
    run_id = request.headers.get("X-RFU-Run-ID", "")
    timestamp_text = request.headers.get("X-RFU-Timestamp", "")
    signature = request.headers.get("X-RFU-Signature", "")
    if not re.fullmatch(r"[A-Za-z0-9._:-]{1,100}", run_id) or not timestamp_text.isdigit():
        return jsonify(error="Invalid synchronization authentication."), 401
    timestamp = int(timestamp_text)
    if abs(int(time.time()) - timestamp) > current_app.config["RFU_SYNC_MAX_AGE_SECONDS"]:
        return jsonify(error="The synchronization request has expired."), 401

    message = f"{timestamp_text}\n{run_id}\n".encode() + body
    expected = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    supplied = signature.removeprefix("sha256=")
    if not hmac.compare_digest(expected, supplied):
        return jsonify(error="Invalid synchronization authentication."), 401

    try:
        payload = json.loads(body)
        snapshot = validate_snapshot(
            payload,
            team_id=current_app.config["RFU_TEAM_ID"],
            max_matches=current_app.config["RFU_SYNC_MAX_MATCHES"],
        )
        run = ingest_snapshot(snapshot, run_id)
        db.session.commit()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return jsonify(error="The synchronization payload is not valid JSON."), 400
    except ReplayError as exc:
        db.session.rollback()
        return jsonify(error=str(exc)), 409
    except SnapshotValidationError as exc:
        db.session.rollback()
        return jsonify(error=str(exc)), 400
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Unable to apply RFU synchronization run %s", run_id)
        return jsonify(error="The synchronization could not be applied."), 500

    status_code = 202 if run.status == "pending_review" else 200
    return (
        jsonify(
            status=run.status,
            run_id=run.run_id,
            created=run.created_count,
            updated=run.updated_count,
            unchanged=run.unchanged_count,
            conflicts=run.conflict_count,
            missing=run.missing_count,
        ),
        status_code,
    )
