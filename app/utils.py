from functools import wraps
from flask import session, redirect, url_for, request
from datetime import datetime

def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get('admin'):
            return redirect(url_for('auth.login', next=request.path))
        return f(*args, **kwargs)
    return wrapper

def parse_date_safe(s):
    if not s:
        return None
    s = s.strip()
    if not s:
        return None
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            continue
    return None
