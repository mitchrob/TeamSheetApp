from functools import wraps
from flask import session, redirect, url_for, request
from datetime import datetime
from urllib.parse import urlparse, urljoin

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

def is_safe_url(target, request_host_url):
    if not target:
        return False
    ref_url = urlparse(request_host_url)
    test_url = urlparse(urljoin(request_host_url, target))
    return test_url.scheme in ('http', 'https') and ref_url.netloc == test_url.netloc
