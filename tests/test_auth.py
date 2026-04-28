import pytest
from app import create_app
from flask import url_for

@pytest.fixture
def app():
    app = create_app()
    app.config.update({
        "TESTING": True,
        "ADMIN_USER": "admin",
        "ADMIN_PASS": "password"
    })
    yield app

@pytest.fixture
def client(app):
    return app.test_client()

def test_login_open_redirect(client):
    response = client.post('/login?next=http://evil.com', data={
        'username': 'admin',
        'password': 'password'
    })
    # the redirect should not go to evil.com
    assert response.status_code == 302
    assert 'evil.com' not in response.headers['Location']

def test_login_safe_redirect(client):
    response = client.post('/login?next=/admin/add', data={
        'username': 'admin',
        'password': 'password'
    })
    # the redirect should go to /admin/add
    assert response.status_code == 302
    assert response.headers['Location'].endswith('/add')
