from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit

from flask import Blueprint, current_app, flash, g, redirect, render_template, request, session, url_for
from sqlalchemy import inspect
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db, limiter
from app.models import AdminUser
from app.utils import admin_required, normalize_username

bp = Blueprint("auth", __name__)


def _is_safe_redirect(target):
    if not target:
        return False
    host = urlsplit(request.host_url)
    destination = urlsplit(urljoin(request.host_url, target))
    return destination.scheme in {"http", "https"} and destination.netloc == host.netloc


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def login():
    next_url = request.values.get("next", "")
    if request.method == "POST":
        user = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        admin_table_exists = inspect(db.engine).has_table("admin_user")
        account = (
            AdminUser.query.filter_by(normalized_username=normalize_username(user)).first()
            if admin_table_exists
            else None
        )
        if account and account.is_active and check_password_hash(account.password_hash, password):
            session.clear()
            session["admin_user_id"] = account.id
            session.permanent = True
            account.last_login_at = datetime.now(timezone.utc)
            db.session.commit()
            if account.must_change_password:
                return redirect(url_for("auth.change_password"))
            return redirect(next_url if _is_safe_redirect(next_url) else url_for("admin.add"))

        fallback_configured = current_app.config.get("ADMIN_USER") and current_app.config.get("ADMIN_PASSWORD_HASH")
        if fallback_configured and (not admin_table_exists or AdminUser.query.count() == 0):
            valid_user = user == current_app.config["ADMIN_USER"]
            valid_password = check_password_hash(current_app.config["ADMIN_PASSWORD_HASH"], password)
            if valid_user and valid_password:
                session.clear()
                session["legacy_admin"] = True
                session.permanent = True
                return redirect(next_url if _is_safe_redirect(next_url) else url_for("admin.add"))
        flash("Invalid credentials", "error")
    return render_template("login.html", next=next_url)


@bp.route("/admin/password", methods=["GET", "POST"])
@admin_required
def change_password():
    if g.admin_user is None:
        flash("Create a database administrator before changing account passwords.", "info")
        return redirect(url_for("admin.users"))
    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirmation = request.form.get("confirmation", "")
        if not check_password_hash(g.admin_user.password_hash, current_password):
            flash("Current password is incorrect.", "error")
        elif len(new_password) < 12:
            flash("New passwords must contain at least 12 characters.", "error")
        elif new_password != confirmation:
            flash("The new passwords do not match.", "error")
        else:
            g.admin_user.password_hash = generate_password_hash(new_password)
            g.admin_user.must_change_password = False
            db.session.commit()
            flash("Password changed successfully.", "success")
            return redirect(url_for("admin.add"))
    return render_template("change_password.html")


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("Logged out", "info")
    return redirect(url_for("main.index"))
