# TeamsheetApp

A lightweight web application designed to manage, process, and display rugby match teamsheets and player appearance statistics. It provides administration capabilities for adding and editing match data, as well as public-facing views for season statistics and individual player records.

## Key Features

- **Data Ingestion & Match Entry**: Authorized users can add new match Teamsheets via an administrative form (`/add`). The application processes player names mapped to specific rugby positions (1-22) and includes validation logic to prevent misspelled or duplicated player names.
- **Player Management**: Features an automated process to flag potential duplicate players (`/duplicates`) and enables admins to merge duplicate profiles into a single unified record (`/merge`), transferring all appearances accurately.
- **Statistical Views**:
  - **Global Stats**: Overall leaderboard of player appearances (`/stats`).
  - **Season View**: Aggregated metrics for a specific season, including total players used, debutants, match results, and most frequent players (`/season/<season>`).
  - **Player View**: Detailed history of a single player, displaying every match they played and their position (`/player/<name>`).
  - **Data View**: A raw data exploration interface (`/data`).
- **Security**: Protected routes for administration actions are wrapped with an `@admin_required` decorator, using a session-based login mechanism via a `/login` route.

## Tech Stack

- **Backend Framework**: Python / Flask
- **Database**: SQLite (local `app.db`) via Flask-SQLAlchemy
- **Frontend**: HTML / CSS (Jinja2 Templates)
- **Deployment Strategy**: PythonAnywhere (using WSGI)

## Local Development Setup

Quick start (Windows / PowerShell / Bash):

1. Create and activate a virtual environment (optional but recommended):

```bash
# Unix / macOS
python -m venv .venv
source .venv/bin/activate

# Windows (PowerShell)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Initialize the database:

```bash
flask --app app init-db
```

4. Run the app:

```bash
python run.py
```
*(Alternatively, `python app.py` can be used).*

5. Open `http://127.0.0.1:5000/` in your browser, upload teamsheet data, and view `Player Appearances`.

## Deployment to PythonAnywhere

1.  **Pull changes**: On PythonAnywhere, navigate to your project and pull the latest changes:
    ```bash
    cd TeamsheetApp
    git pull
    ```

2.  **Update Dependencies**:
    ```bash
    source myenv/bin/activate
    pip install -r requirements.txt
    ```

3.  **Update WSGI Configuration**:
    Edit your WSGI configuration file (in the Web tab) to point to the new application factory.

    **Old:**
    ```python
    from app import app as application
    ```

    **New:**
    ```python
    import sys
    import os

    # Add project directory to path
    path = '/home/yourusername/TeamsheetApp'
    if path not in sys.path:
        sys.path.insert(0, path)

    # Import the application factory
    from app import create_app
    application = create_app()
    ```

4.  **Reload**: Reload the web app from the Web tab.

Notes:
- The database `app.db` is in the project root. If you want to keep your existing data, make sure `app.db` is preserved (it is git-ignored by default).
- If you have trouble, check the Error Log in the Web tab.
