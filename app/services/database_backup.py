import hashlib
import sqlite3
import tempfile
from pathlib import Path

from flask import current_app

from app.extensions import db


class DatabaseBackupError(RuntimeError):
    pass


def create_database_backup():
    """Create and verify a transactionally consistent SQLite snapshot."""
    if db.engine.dialect.name != "sqlite":
        raise DatabaseBackupError("Database backups are only configured for SQLite.")

    temporary_directory = tempfile.TemporaryDirectory(prefix="teamsheet-backup-")
    backup_path = Path(temporary_directory.name) / "teamsheet.db"
    source_connection = None
    destination_connection = None

    try:
        source_connection = db.engine.raw_connection()
        source_database = source_connection.driver_connection
        destination_connection = sqlite3.connect(backup_path)
        source_database.backup(destination_connection)
        destination_connection.close()
        destination_connection = None

        verification = sqlite3.connect(f"file:{backup_path.as_posix()}?mode=ro", uri=True)
        try:
            result = verification.execute("PRAGMA integrity_check").fetchone()
        finally:
            verification.close()
        if result != ("ok",):
            raise DatabaseBackupError("The database snapshot did not pass its integrity check.")

        if backup_path.stat().st_size > current_app.config["DATABASE_BACKUP_MAX_BYTES"]:
            raise DatabaseBackupError("The database snapshot exceeds the configured safety limit.")
        snapshot = backup_path.read_bytes()
        digest = hashlib.sha256(snapshot).hexdigest()
        temporary_directory.cleanup()
        return snapshot, digest
    except DatabaseBackupError:
        temporary_directory.cleanup()
        raise
    except (OSError, sqlite3.DatabaseError) as exc:
        temporary_directory.cleanup()
        current_app.logger.exception("Unable to create the SQLite database backup")
        raise DatabaseBackupError("The database backup could not be created.") from exc
    finally:
        if destination_connection is not None:
            destination_connection.close()
        if source_connection is not None:
            source_connection.close()
