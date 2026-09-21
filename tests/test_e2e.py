import threading

import pytest
from werkzeug.security import generate_password_hash
from werkzeug.serving import make_server

pytest.importorskip("playwright.sync_api")

from app import create_app
from app.extensions import db
from app.models import AdminUser, Match
from app.utils import normalize_username
from config import TestConfig


@pytest.fixture(scope="module")
def live_site(tmp_path_factory):
    database = tmp_path_factory.mktemp("browser") / "browser.db"

    class BrowserConfig(TestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{database.as_posix()}"
        WTF_CSRF_ENABLED = False

    app = create_app(BrowserConfig)
    with app.app_context():
        db.create_all()
        db.session.add(
            AdminUser(
                username="Browser Admin",
                normalized_username=normalize_username("Browser Admin"),
                password_hash=generate_password_hash("browser-password"),
                must_change_password=False,
            )
        )
        db.session.commit()

    server = make_server("127.0.0.1", 0, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", app
    server.shutdown()
    thread.join(timeout=5)


def _login(page, base_url):
    page.goto(f"{base_url}/login")
    page.get_by_label("Username").fill("Browser Admin")
    page.get_by_label("Password").fill("browser-password")
    page.get_by_role("button", name="Login").click()
    page.wait_for_url("**/add")


def test_mobile_complete_validate_and_edit_23_player_teamsheet(page, live_site):
    base_url, app = live_site
    page.set_viewport_size({"width": 390, "height": 844})
    _login(page, base_url)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")

    page.get_by_label("League").fill("Browser League")
    page.get_by_label("Season").fill("2026-27")
    page.get_by_label("Date").fill("2026-09-19")
    page.get_by_role("textbox", name="Opposition", exact=True).fill("Mobile Rivals")
    page.get_by_label("Location").fill("Home")
    for position in range(1, 24):
        page.get_by_role("combobox", name=f"Position {position}", exact=True).fill(f"Player {position:02d}")

    position_two = page.get_by_role("combobox", name="Position 2", exact=True)
    position_two.fill("Player 01")
    assert position_two.evaluate("element => element.classList.contains('input-error')")
    position_two.fill("Player 02")
    page.get_by_role("button", name="Add teamsheet").click()
    page.wait_for_url("**/stats")

    with app.app_context():
        match = Match.query.one()
        match_id = match.id

    page.goto(f"{base_url}/edit/{match_id}")
    assert page.get_by_role("combobox", name="Position 23", exact=True).input_value() == "Player 23"
    page.get_by_role("textbox", name="Opposition", exact=True).fill("Edited Mobile Rivals")
    page.get_by_role("button", name="Update teamsheet").click()
    page.wait_for_url("**/data")
    assert page.get_by_text("Edited Mobile Rivals").is_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


def test_keyboard_player_picker_and_visual_smoke(browser, live_site, tmp_path):
    base_url, _ = live_site
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    _login(page, base_url)
    first_position = page.get_by_role("combobox", name="Position 1", exact=True)
    first_position.fill("Player 0")
    first_position.press("ArrowDown")
    page.keyboard.press("Enter")
    assert first_position.input_value().startswith("Player")

    page.goto(f"{base_url}/login")
    login_card = page.locator(".auth-card")
    before_hover = login_card.bounding_box()
    login_card.hover()
    page.wait_for_timeout(250)
    assert login_card.bounding_box() == before_hover

    routes = ["/", "/data", "/stats", "/season?season=2026-27", "/match/1", "/player?name=Player%2001", "/login", "/add"]
    for index, route in enumerate(routes):
        page.goto(f"{base_url}{route}")
        page.screenshot(path=tmp_path / f"smoke-{index}.png", full_page=True)
        assert page.title()
    context.close()
