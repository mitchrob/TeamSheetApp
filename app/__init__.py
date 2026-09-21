import logging

from flask import Flask, g, redirect, render_template, request, session, url_for
from flask_wtf.csrf import CSRFError
from sqlalchemy import inspect
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

    from app.cli import register_cli
    from app.models import AdminUser

    register_cli(app)

    @app.before_request
    def load_admin_user():
        g.admin_user = None
        admin_table_exists = inspect(db.engine).has_table("admin_user")
        user_id = session.get("admin_user_id")
        if user_id and admin_table_exists:
            user = db.session.get(AdminUser, user_id)
            if user and user.is_active:
                g.admin_user = user
            else:
                session.clear()

        database_accounts_exist = admin_table_exists and db.session.query(AdminUser.id).first() is not None
        legacy_admin = bool(session.get("legacy_admin")) and not database_accounts_exist
        if session.get("legacy_admin") and database_accounts_exist:
            session.clear()
            legacy_admin = False
        g.is_admin = bool(g.admin_user or legacy_admin)

        allowed = {"auth.change_password", "auth.logout", "static"}
        if g.admin_user and g.admin_user.must_change_password and request.endpoint not in allowed:
            return redirect(url_for("auth.change_password"))

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
    required = ("SECRET_KEY",)
    missing = [name for name in required if not app.config.get(name)]
    if production and missing:
        raise RuntimeError(f"Missing required production configuration: {', '.join(missing)}")
    if production and bool(app.config.get("ADMIN_USER")) != bool(app.config.get("ADMIN_PASSWORD_HASH")):
        raise RuntimeError("ADMIN_USER and ADMIN_PASSWORD_HASH must be configured together.")

    if not production and not app.config.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = "development-only-secret"
    if not production and not app.config.get("ADMIN_USER"):
        app.config["ADMIN_USER"] = "admin"
    if not production and not app.config.get("ADMIN_PASSWORD_HASH"):
        app.config["ADMIN_PASSWORD_HASH"] = generate_password_hash("password")
        logging.getLogger(__name__).warning(
            "Using development admin credentials; configure ADMIN_PASSWORD_HASH before deployment."
        )
