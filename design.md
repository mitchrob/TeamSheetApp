# Teamsheet App Design Document

## 1. Overview
The Teamsheet App is a lightweight web application designed to manage, process, and display rugby match teamsheets and player appearance statistics. It provides administration capabilities for adding and editing match data, as well as public-facing views for season statistics and individual player records.

## 2. Tech Stack
- **Backend Framework**: Python / Flask
- **Database**: SQLite (local `app.db`) via Flask-SQLAlchemy
- **Frontend**: HTML / CSS (Jinja2 Templates)
- **Deployment Strategy**: PythonAnywhere (using WSGI)

## 3. Data Architecture (SQLAlchemy Models)

The system relies on three core relational models to structure the rugby data:

- **Match**: Represents a single game.
  - Fields: `id`, `league`, `season`, `date`, `opposition`, `location`, `result`, `guildford_points`, `opposition_points`.
  - Relationship: One-to-many with `Appearance`.

- **Player**: Represents an individual player.
  - Fields: `id`, `name` (unique).
  - Relationship: One-to-many with `Appearance`.

- **Appearance**: A linking table that records a player taking part in a specific match at a specific position.
  - Fields: `id`, `player_id`, `match_id`, `position`.

## 4. Key Features & Workflows

### 4.1. Data Ingestion & Match Entry
- Authorized users can add new match Teamsheets via an administrative form (`/add`).
- The application processes comma-separated or bulk-text input, extracting player names to specific rugby positions (1-22).
- Includes validation logic (`find_potential_duplicates`) to prevent entering misspelled or duplicated player names (using fuzzy string matching or threshold checking).

### 4.2. Player Management
- Provides an automated process to flag and view potential duplicate players (`/admin/duplicates`).
- Enables admins to merge duplicate profiles into a single unified record (`/admin/merge`), automatically transferring all associated `Appearance` records to the canonical player model.

### 4.3. Statistical Views
- **Global Stats (`/stats`)**: Overall leaderboard of player appearances.
- **Season View (`/season/<season>`)**: Aggregated metrics for a specific season, including total players used, debutants, match results, and most frequent players.
- **Player View (`/player/<name>`)**: Detailed history of a single player, displaying every match they played and their position.
- **Data View (`/data`)**: A raw data exploration interface.

### 4.4. Security & Authentication
- Protected routes (adding data, editing, deleting, merging) are wrapped with an `@admin_required` decorator.
- Session-based login mechanism via a `/login` route.

## 5. Deployment & CLI Commands
The application exposes Flask CLI commands to handle database initialization:
- `flask init-db` - Initializes the SQLite tables.
