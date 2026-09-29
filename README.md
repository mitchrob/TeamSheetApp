# TeamsheetApp

A Flask application for recording Guildford Rugby match teamsheets and publishing player and season statistics.

## Features

- Named administrator accounts, forced first-login password changes, and attributed activity history.
- Mobile-first entry with searchable player slots, lineup copying, inline review, and 23-player support.
- Matchday squads of up to 23 players: positions 1–15 are starts and 16–23 are replacements.
- Player appearance, season, score, debut, leaver, and shirt-number statistics.
- Public match pages showing the complete teamsheet for each game.
- Duplicate-name detection with conflict-safe player merging.
- SQLite migrations, automated tests, linting, and documented PythonAnywhere deployment.
- Public match/player filters, CSV exports, and an administrator data-quality dashboard.
- Automatic Guildford 1st XV fixture and result imports from the public RFU page.

## Local setup

Python 3.13 is required.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m flask --app run db upgrade
python run.py
```

On macOS or Linux, replace the activation command with `source .venv/bin/activate`. Open <http://127.0.0.1:5000> after starting the app.

Development mode supplies `admin` / `password` only for local bootstrap and logs a warning. Create the first named account with the command below; after that, the shared login is automatically disabled.

```powershell
python -m flask --app run users bootstrap --username your-name
```

The command prompts for a password of at least 12 characters. For emergency recovery:

```powershell
python -m flask --app run users reset-password your-name
```

## Configuration

Set these environment variables in production:

| Name | Purpose |
| --- | --- |
| `APP_ENV=production` | Enables production security checks and secure cookies. |
| `SECRET_KEY` | Long random value used to sign sessions and CSRF tokens. |
| `ADMIN_USER` | Optional temporary bootstrap username; ignored after the first database account exists. |
| `ADMIN_PASSWORD_HASH` | Optional bootstrap password hash; configure together with `ADMIN_USER`. |
| `DATABASE_URL` | Optional SQLAlchemy URL; defaults to `app.db`. |
| `RATELIMIT_STORAGE_URI` | Optional shared rate-limit store; defaults to in-memory storage. |
| `RFU_SYNC_SECRET` | Shared secret of at least 32 characters used to authenticate GitHub fixture snapshots. |
| `RFU_TEAM_ID` | RFU team identifier; defaults to Guildford 1st XV (`9045`). |
| `RFU_GITHUB_WORKFLOW_URL` | Optional link shown to administrators for manually running the sync workflow. |
| `DATABASE_BACKUP_SECRET` | Shared secret of at least 32 characters used only to authenticate database snapshot downloads. |

Generate a password hash locally:

```powershell
python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('replace-with-a-strong-password'))"
```

## Database migrations

Back up `app.db` before every production migration, then run:

```powershell
python -m flask --app run db upgrade
```

The initial migration can create a fresh database or upgrade the original schema. It canonicalizes seasons to `YYYY-YY`, normalizes results, removes duplicate appearances, and adds integrity constraints. The second migration adds named administrators and append-only audit events. The third adds RFU fixture identity, status, synchronization history, and first-import staging.

## RFU fixture synchronization

The `RFU fixture sync` GitHub Actions workflow runs nightly and can also be started manually from the repository's Actions page. It renders the public RFU page in Chromium, validates every match, and sends one signed snapshot to the app. Browser failures and RFU page changes fail closed; they never send a partial snapshot.

Configure the following repository settings:

- Repository secret `RFU_SYNC_SECRET`, matching the PythonAnywhere environment value.
- Repository variable `RFU_SYNC_URL`, set to the production URL ending in `/internal/rfu-sync`.
- PythonAnywhere `RFU_GITHUB_WORKFLOW_URL`, set to the workflow's GitHub page if administrators should see a direct “Run workflow” link.

After deployment, run the workflow once with `dry_run` enabled. If it succeeds, run it normally and review the proposed current-season reconciliation under **Admin → RFU fixture sync**. Once approved, later runs update imported fixtures automatically by their RFU match ID. Imported fixture details are read-only, while teamsheets remain editable. Manual match creation remains available for friendlies and RFU omissions.

To test the scraper locally without sending data:

```powershell
python -m pip install -r requirements-scraper.txt
python -m playwright install chromium
python -m app.rfu_scraper --dry-run --season 2026-2027
```

## Production database backups

The `Back up production database` GitHub Actions workflow securely downloads a consistent SQLite snapshot from PythonAnywhere, verifies its checksum and SQLite integrity, encrypts it, and uploads only the encrypted file to a private Backblaze B2 bucket. PythonAnywhere does not need outbound internet access, and the unencrypted database is removed from the temporary GitHub runner after every run.

Create a private B2 bucket with a lifecycle rule for the desired retention period and a standard application key restricted to that bucket. Do not use the Backblaze master key. Configure these GitHub repository settings:

- Secret `DATABASE_BACKUP_SECRET`, matching the PythonAnywhere environment value.
- Secret `DATABASE_BACKUP_ENCRYPTION_PASSPHRASE`, stored separately in a password manager.
- Secrets `B2_KEY_ID` and `B2_APPLICATION_KEY` for the bucket-restricted Backblaze key.
- Variable `DATABASE_BACKUP_URL`, set to the production URL ending in `/internal/database-backup`.
- Variable `B2_BUCKET`, containing the private bucket name.
- Variable `B2_ENDPOINT`, containing the bucket's HTTPS S3 endpoint.
- Variable `B2_REGION`, containing the Backblaze region from that endpoint.

Run the workflow manually once after configuration and confirm that an encrypted object appears in B2. A successful upload is not sufficient on its own: periodically download a backup, decrypt it, and verify it before relying on the backup process.

To restore a downloaded backup, keep the live database unchanged until the recovered snapshot has passed its integrity check:

```bash
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
  -in teamsheet.db.enc -out restored.db \
  -pass env:DATABASE_BACKUP_ENCRYPTION_PASSPHRASE
python -c "import sqlite3; c=sqlite3.connect('restored.db'); print(c.execute('PRAGMA integrity_check').fetchone()[0])"
```

Only replace production `app.db` during a planned recovery, after preserving the current file and stopping writes. Apply migrations and reload the web application after restoration.

## Quality checks

```powershell
python -m ruff check .
python -m pytest
```

The development requirements include Playwright. Install its Chromium runtime once with:

```powershell
python -m playwright install chromium
```

Tests use isolated SQLite databases and do not modify `app.db`.

## PythonAnywhere deployment

Use a Python 3.13 web app and virtual environment named `teamsheetapp`. Configure the production environment variables in the WSGI file before creating the application:

```python
import os
import sys

os.environ["APP_ENV"] = "production"
os.environ["SECRET_KEY"] = "replace-with-a-long-random-value"
os.environ["RFU_SYNC_SECRET"] = "replace-with-the-same-32+-character-github-secret"
os.environ["DATABASE_BACKUP_SECRET"] = "replace-with-a-different-32+-character-github-secret"
os.environ["RFU_GITHUB_WORKFLOW_URL"] = "https://github.com/OWNER/REPOSITORY/actions/workflows/rfu-sync.yml"
# Optional only while bootstrapping the first database administrator:
# os.environ["ADMIN_USER"] = "replace-with-the-admin-name"
# os.environ["ADMIN_PASSWORD_HASH"] = "replace-with-the-generated-hash"

project_path = "/home/yourusername/TeamSheetApp"
if project_path not in sys.path:
    sys.path.insert(0, project_path)

from app import create_app
application = create_app()
```

Every push to `main` is checked by GitHub with linting, tests, and a fresh-database migration. PythonAnywhere free accounts do not provide SSH access, so production deployment remains a deliberate manual operation from a PythonAnywhere Bash console.

Before deploying, confirm that the latest off-site Backblaze backup succeeded. Then update the code without replacing `app.db`:

```bash
cd ~/TeamSheetApp
git pull --ff-only origin main
source ~/.virtualenvs/teamsheetapp/bin/activate
python -m pip install -r requirements.txt
python -m flask --app run db upgrade
```

Reload the web application from PythonAnywhere's **Web** page after these commands finish successfully. Never copy the local development `app.db` over the production database.
