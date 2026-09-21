import logging

from flask import Flask, render_template
from flask_wtf.csrf import CSRFError
from werkzeug.security import generate_password_hash

from app.extensions import csrf, db, limiter, migrate
from config import Config


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    _configure_security(app)

    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    limiter.init_app(app)

    from app.routes import admin, auth, main

    app.register_blueprint(main.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(auth.bp)

    @app.errorhandler(CSRFError)
    def handle_csrf_error(error):
        return render_template("error.html", title="Request expired", message=error.description), 400

    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return response

    return app


def _configure_security(app):
    production = app.config.get("ENVIRONMENT") == "production"
    required = ("SECRET_KEY", "ADMIN_USER", "ADMIN_PASSWORD_HASH")
    missing = [name for name in required if not app.config.get(name)]
    if production and missing:
        raise RuntimeError(f"Missing required production configuration: {', '.join(missing)}")

    if not app.config.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = "development-only-secret"
    if not app.config.get("ADMIN_USER"):
        app.config["ADMIN_USER"] = "admin"
    if not app.config.get("ADMIN_PASSWORD_HASH"):
        app.config["ADMIN_PASSWORD_HASH"] = generate_password_hash("password")
        logging.getLogger(__name__).warning(
            "Using development admin credentials; configure ADMIN_PASSWORD_HASH before deployment."
        )
