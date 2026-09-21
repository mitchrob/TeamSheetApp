# TeamsheetApp

A Flask application for recording Guildford Rugby match teamsheets and publishing player and season statistics.

## Features

- Secure administrator workflow for adding, editing, deleting, and merging data.
- Matchday squads of up to 23 players: positions 1–15 are starts and 16–23 are replacements.
- Player appearance, season, score, debut, leaver, and shirt-number statistics.
- Public match pages showing the complete teamsheet for each game.
- Duplicate-name detection with conflict-safe player merging.
- SQLite migrations, automated tests, linting, and gated PythonAnywhere deployment.

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

Development mode supplies `admin` / `password` only for local use and logs a warning. Production refuses to start without secure configuration.

## Configuration

Set these environment variables in production:

| Name | Purpose |
| --- | --- |
| `APP_ENV=production` | Enables production security checks and secure cookies. |
| `SECRET_KEY` | Long random value used to sign sessions and CSRF tokens. |
| `ADMIN_USER` | Administrator username. |
| `ADMIN_PASSWORD_HASH` | Werkzeug password hash; never store the plaintext password. |
| `DATABASE_URL` | Optional SQLAlchemy URL; defaults to `app.db`. |
| `RATELIMIT_STORAGE_URI` | Optional shared rate-limit store; defaults to in-memory storage. |

Generate a password hash locally:

```powershell
python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('replace-with-a-strong-password'))"
```

## Database migrations

Back up `app.db` before every production migration, then run:

```powershell
python -m flask --app run db upgrade
```

The initial migration can create a fresh database or upgrade the original schema. It canonicalizes seasons to `YYYY-YY`, normalizes results, removes duplicate appearances, and adds integrity constraints.

## Quality checks

```powershell
python -m ruff check .
python -m pytest
```

Tests use isolated SQLite databases and do not modify `app.db`.

## PythonAnywhere deployment

Use a Python 3.13 web app and virtual environment named `teamsheetapp`. Configure the production environment variables in the WSGI file before creating the application:

```python
import os
import sys

os.environ["APP_ENV"] = "production"
os.environ["SECRET_KEY"] = "replace-with-a-long-random-value"
os.environ["ADMIN_USER"] = "replace-with-the-admin-name"
os.environ["ADMIN_PASSWORD_HASH"] = "replace-with-the-generated-hash"

project_path = "/home/yourusername/TeamSheetApp"
if project_path not in sys.path:
    sys.path.insert(0, project_path)

from app import create_app
application = create_app()
```

Pushes to `main` deploy only after linting, tests, and a fresh-database migration pass. The deployment job backs up `app.db`, pulls with `--ff-only`, installs pinned dependencies, applies migrations, and reloads the PythonAnywhere WSGI file.
