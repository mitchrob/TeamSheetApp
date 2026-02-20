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

    # Re-registering the CLI commands from original app.py
    @app.cli.command('init-db')
    def init_db_command():
        """Create all database tables."""
        db.create_all()
        print('Initialized the database.')

    return app
