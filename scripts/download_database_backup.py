"""Download and verify a signed production database snapshot."""

import hashlib
import hmac
import os
import sqlite3
import sys
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

MAX_BACKUP_BYTES = 128 * 1024 * 1024


def _required_environment(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Required environment variable {name} is not configured.")
    return value


def main():
    url = _required_environment("DATABASE_BACKUP_URL")
    secret = _required_environment("DATABASE_BACKUP_SECRET")
    output_path = Path(os.environ.get("DATABASE_BACKUP_OUTPUT", "database-backup.db"))
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.query or parsed.fragment:
        raise RuntimeError("DATABASE_BACKUP_URL must be an HTTPS URL without a query or fragment.")

    timestamp = str(int(time.time()))
    run_id = os.environ.get("DATABASE_BACKUP_RUN_ID", str(uuid.uuid4()))
    message = f"{timestamp}\n{run_id}\nPOST\n{parsed.path}\n".encode()
    signature = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    request = Request(
        url,
        data=b"",
        method="POST",
        headers={
            "X-Backup-Run-ID": run_id,
            "X-Backup-Timestamp": timestamp,
            "X-Backup-Signature": f"sha256={signature}",
        },
    )

    try:
        with urlopen(request, timeout=60) as response:
            expected_digest = response.headers.get("X-Backup-SHA256", "")
            snapshot = response.read(MAX_BACKUP_BYTES + 1)
    except HTTPError as exc:
        raise RuntimeError(f"The backup endpoint returned HTTP {exc.code}.") from exc
    except URLError as exc:
        raise RuntimeError("The backup endpoint could not be reached.") from exc

    if len(snapshot) > MAX_BACKUP_BYTES:
        raise RuntimeError("The downloaded database exceeds the configured safety limit.")
    actual_digest = hashlib.sha256(snapshot).hexdigest()
    if not expected_digest or not hmac.compare_digest(expected_digest, actual_digest):
        raise RuntimeError("The downloaded database checksum is invalid.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(snapshot)
    try:
        connection = sqlite3.connect(f"file:{output_path.resolve().as_posix()}?mode=ro", uri=True)
        try:
            result = connection.execute("PRAGMA integrity_check").fetchone()
        finally:
            connection.close()
        if result != ("ok",):
            raise RuntimeError("The downloaded database failed its integrity check.")
    except sqlite3.DatabaseError as exc:
        output_path.unlink(missing_ok=True)
        raise RuntimeError("The downloaded file is not a valid SQLite database.") from exc

    print(f"Downloaded and verified database backup ({len(snapshot)} bytes).")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        print(f"Backup failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
