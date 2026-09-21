import unicodedata
from datetime import datetime
from functools import wraps

from flask import g, redirect, request, url_for


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not getattr(g, "is_admin", False):
            return redirect(url_for('auth.login', next=request.path))
        return f(*args, **kwargs)
    return wrapper


def normalize_username(value):
    return unicodedata.normalize("NFKC", value or "").strip().casefold()

def parse_date_safe(s):
    if not s:
        return None
    s = s.strip()
    if not s:
        return None
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None
