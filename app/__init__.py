from flask import Flask
from config import Config
from app.extensions import db

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize Flask extensions
    db.init_app(app)

    # Register Blueprints
    from app.routes import main, admin, auth
    app.register_blueprint(main.bp)
    app.register_blueprint(admin.bp) # admin routes usually are root or /admin? Original was root.
    app.register_blueprint(auth.bp) # login logic

    # Create tables if they don't exist
    # Note: In production we should use migrations. 
    # For now, auto-create on start if using sqlite/dev
    with app.app_context():
        db.create_all()

    # CLI commands
    from app.models import Match, Player, Appearance
    import csv, os
    from app.utils import parse_date_safe

    # Re-registering the CLI commands from original app.py
    @app.cli.command('init-db')
    def init_db_command():
        """Create all database tables."""
        db.create_all()
        print('Initialized the database.')

    @app.cli.command('migrate-csv')
    def migrate_csv_command():
        """Migrate data from GRFC_data.csv to the database."""
        # ...Logic copied/adapted...
        # For brevity, I'll rely on the user running this command or porting it fully if needed.
        # But since I'm rewriting, I should probably include it to be safe 
        # or the user will lose the ability to import data easily.
        # I'll include a simplified version using the logic directly.
        
        CSV_PATH = app.config.get('CSV_PATH', 'GRFC_data.csv')
        
        def read_rows():
            rows = []
            if not os.path.exists(CSV_PATH):
                return rows
            with open(CSV_PATH, newline='', encoding='utf-8') as f:
                reader = csv.reader(f, skipinitialspace=True)
                for row in reader:
                    if not any(cell.strip() for cell in row):
                        continue
                    rows.append([cell.strip() for cell in row])
            return rows

        rows = read_rows()
        if not rows or len(rows) < 2:
            print("CSV file is empty or contains only a header.")
            return

        def find_player_start_index(header_row):
            for i, h in enumerate(header_row):
                if h.strip().isdigit():
                    return i
            return 8

        header = rows[0]
        player_start = find_player_start_index(header)
        player_cache = {}

        # Important: app_context() is already active in CLI command
        count = 0 
        for row in rows[1:]:
             # Check if match already exists (Duplicate prevention for re-runs)
             # Simplistic check: date & opposition
            date_str = row[2] if len(row) > 2 else ''
            match_date = parse_date_safe(date_str)
            if not match_date:
                continue
            
            # This logic is a bit destructive if not careful. 
            # Original app blindly added. I'll stick to original behavior.
            
            new_match = Match(
                league=row[0],
                season=row[1],
                date=match_date,
                opposition=row[3],
                location=row[4],
                result=row[5],
                guildford_points=int(row[6]) if row[6].isdigit() else None,
                opposition_points=int(row[7]) if row[7].isdigit() else None,
            )
            db.session.add(new_match)
            count += 1
            
            for i, player_name in enumerate(row[player_start:player_start + 20]):
                player_name = player_name.strip()
                if not player_name:
                    continue
                
                player = player_cache.get(player_name)
                if not player:
                    player = Player.query.filter_by(name=player_name).first()
                    if not player:
                        player = Player(name=player_name)
                        db.session.add(player)
                    player_cache[player_name] = player
                
                appearance = Appearance(player=player, match=new_match, position=i + 1)
                db.session.add(appearance)
        
        db.session.commit()
        print(f"Successfully migrated {count} matches from CSV.")

    return app
