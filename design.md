# Teamsheet App Design

## Architecture

The application uses a Flask application factory, blueprints, SQLAlchemy models, and Alembic migrations. `app.py` and `run.py` are thin launchers; application behavior lives under `app/`.

SQLite remains the production data store on PythonAnywhere. Schema changes are applied with `flask --app run db upgrade`, never during request startup.

## Data model

- `Match` stores a canonical `YYYY-YY` season, date, opposition, optional location and league, canonical result, and optional nonnegative scores.
- `Player` stores a unique, nonblank display name.
- `Appearance` joins one player to one match and one shirt position. Player/match and match/position pairs are unique; positions range from 1 through 23.

When both scores are present, the result is derived from the score. Missing scores are excluded from score averages. A player's debut season is determined by their earliest match date.

## Routes and access

- Public reads: `/`, `/stats`, `/season?season=YYYY-YY`, `/player?name=...`, `/match/<id>`, and `/data`.
- Authentication: `/login`; `/logout` accepts POST only.
- Administrator writes: `/add`, `/edit/<id>`, `/delete/<id>`, `/duplicates`, and `/merge`.

Write operations require an authenticated administrator session and a valid CSRF token. Production requires a session secret, administrator username, and password hash. Login attempts are rate-limited and redirect destinations are restricted to the current host.

## Operations

- Python 3.13 and exact direct dependency versions provide a reproducible runtime.
- Pytest covers security, forms, data integrity, merges, and statistics.
- Ruff enforces the configured code-quality rules.
- CI runs linting, tests, and a fresh migration before deployment.
- Deployment takes an SQLite backup before applying migrations and reloads the WSGI app only after every earlier step succeeds.
