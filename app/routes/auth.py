from flask import Blueprint, render_template, request, session, redirect, url_for, flash
import os
from app.utils import is_safe_url

bp = Blueprint('auth', __name__)

@bp.route('/login', methods=['GET', 'POST'])
def login():
    # simple admin login (credentials can be set via env vars ADMIN_USER and ADMIN_PASS)
    if request.method == 'POST':
        user = request.form.get('username', '').strip()
        pw = request.form.get('password', '').strip()
        # Access config from current app (or use os.environ as fallback, but better via app config)
        from flask import current_app
        admin_user = current_app.config.get('ADMIN_USER', 'admin')
        admin_pass = current_app.config.get('ADMIN_PASS', 'password')
        
        if user == admin_user and pw == admin_pass:
            session['admin'] = True
            # Validate next_url to minimize open redirect vulnerability
            next_url = request.args.get('next') or request.form.get('next')
            if not is_safe_url(next_url, request.host_url):
                next_url = url_for('admin.add')
            return redirect(next_url)
        else:
            flash('Invalid credentials', 'error')
            return render_template('login.html', next=request.args.get('next') or '')
    return render_template('login.html', next=request.args.get('next') or '')


@bp.route('/logout', methods=['GET'])
def logout():
    session.pop('admin', None)
    flash('Logged out', 'info')
    return redirect(url_for('main.index'))
