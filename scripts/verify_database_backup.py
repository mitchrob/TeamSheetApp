"""Verify that a restored Teamsheet SQLite backup is healthy and complete."""

import argparse
import hashlib
import sqlite3
import sys
from pathlib import Path

REQUIRED_TABLES = {"appearance", "match", "player"}


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_database(path, expected_path=None):
    path = Path(path)
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError("The restored database file is missing or empty.")
    if expected_path is not None and _sha256(path) != _sha256(Path(expected_path)):
        raise RuntimeError("The restored database does not match the source snapshot.")

    connection = None
    try:
        connection = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if integrity != ("ok",):
            raise RuntimeError("The restored database failed its integrity check.")
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        }
        missing = REQUIRED_TABLES - tables
        if missing:
            raise RuntimeError(f"The restored database is missing required tables: {', '.join(sorted(missing))}.")
        counts = {
            table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            for table in sorted(REQUIRED_TABLES)
        }
    except sqlite3.DatabaseError as exc:
        raise RuntimeError("The restored file is not a valid SQLite database.") from exc
    finally:
        if connection is not None:
            connection.close()
    return counts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("database", type=Path)
    parser.add_argument("--matches", type=Path, dest="expected_path")
    args = parser.parse_args()
    counts = verify_database(args.database, args.expected_path)
    print(
        "Restored database verified: "
        f"{counts['match']} matches, {counts['player']} players, {counts['appearance']} appearances."
    )


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        print(f"Restore verification failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
