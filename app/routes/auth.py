from urllib.parse import urljoin, urlsplit

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from app.extensions import limiter

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
        valid_user = user == current_app.config["ADMIN_USER"]
        valid_password = check_password_hash(current_app.config["ADMIN_PASSWORD_HASH"], password)
        if valid_user and valid_password:
            session.clear()
            session["admin"] = True
            session.permanent = True
            return redirect(next_url if _is_safe_redirect(next_url) else url_for("admin.add"))
        flash("Invalid credentials", "error")
    return render_template("login.html", next=next_url)


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("Logged out", "info")
    return redirect(url_for("main.index"))
