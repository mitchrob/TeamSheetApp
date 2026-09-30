import sqlite3

import pytest

from scripts.verify_database_backup import verify_database


def _database(path, *, include_tables=True):
    connection = sqlite3.connect(path)
    try:
        if include_tables:
            for table in ("match", "player", "appearance"):
                connection.execute(f'CREATE TABLE "{table}" (id INTEGER PRIMARY KEY)')
            connection.execute('INSERT INTO "match" DEFAULT VALUES')
        else:
            connection.execute('CREATE TABLE "unrelated" (id INTEGER PRIMARY KEY)')
        connection.commit()
    finally:
        connection.close()


def test_verify_database_accepts_matching_healthy_snapshot(tmp_path):
    source = tmp_path / "source.db"
    restored = tmp_path / "restored.db"
    _database(source)
    restored.write_bytes(source.read_bytes())

    counts = verify_database(restored, source)

    assert counts == {"appearance": 0, "match": 1, "player": 0}


def test_verify_database_rejects_changed_or_incomplete_snapshot(tmp_path):
    source = tmp_path / "source.db"
    changed = tmp_path / "changed.db"
    incomplete = tmp_path / "incomplete.db"
    _database(source)
    _database(changed)
    _database(incomplete, include_tables=False)
    with sqlite3.connect(changed) as connection:
        connection.execute('INSERT INTO "player" DEFAULT VALUES')

    with pytest.raises(RuntimeError, match="does not match"):
        verify_database(changed, source)
    with pytest.raises(RuntimeError, match="missing required tables"):
        verify_database(incomplete)
