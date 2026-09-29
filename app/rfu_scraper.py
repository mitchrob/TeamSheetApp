import argparse
import hashlib
import hmac
import json
import os
import re
import sys
import time
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urljoin, urlparse
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

RFU_BASE_URL = "https://www.englandrugby.com"
RFU_LIST_URL = RFU_BASE_URL + "/fixtures-and-results/search-results?season={season}&team={team_id}"
SEASON_PATTERN = re.compile(r"^(\d{4})-(\d{4})$")


class ScrapeError(RuntimeError):
    pass


def current_rfu_season(today=None):
    today = today or date.today()
    start = today.year if today.month >= 7 else today.year - 1
    return f"{start}-{start + 1}"


def canonical_season(rfu_season):
    match = SEASON_PATTERN.fullmatch(rfu_season or "")
    if not match or int(match.group(2)) != int(match.group(1)) + 1:
        raise ScrapeError("Season must use RFU format YYYY-YYYY with consecutive years.")
    return f"{match.group(1)}-{int(match.group(2)) % 100:02d}"


def parse_match_cards(html, *, rfu_season, team_id="9045", default_status="scheduled"):
    season = canonical_season(rfu_season)
    soup = BeautifulSoup(html, "html.parser")
    matches = {}
    for wrapper in soup.select(".resultWrapper"):
        match_link = wrapper.select_one("a.c065-match-link[data-match-id]")
        if not match_link:
            continue
        external_id = (match_link.get("data-match-id") or "").strip()
        if not external_id.isdigit():
            raise ScrapeError("An RFU card contains an invalid match ID.")

        date_node = wrapper.select_one(".coh-style-card-left-date")
        league_node = wrapper.select_one(".coh-style-sub-header-right")
        home_node = wrapper.select_one(".coh-style-hometeam a[href*='team=']")
        away_node = wrapper.select_one(".coh-style-away-team a[href*='team=']")
        if not all((date_node, home_node, away_node)):
            raise ScrapeError(f"RFU match {external_id} is missing required card fields.")

        match_date = _parse_rfu_date(date_node.get_text(" ", strip=True))
        home = _team_from_link(home_node)
        away = _team_from_link(away_node)
        guildford_sides = [side for side, team in (("Home", home), ("Away", away)) if team["id"] == str(team_id)]
        if len(guildford_sides) != 1:
            raise ScrapeError(f"RFU match {external_id} does not contain Guildford exactly once.")
        location = guildford_sides[0]
        opposition = away["name"] if location == "Home" else home["name"]

        score_nodes = wrapper.select(".fnr-scores a")
        scores = [node.get_text(strip=True) for node in score_nodes if node.get_text(strip=True).isdigit()]
        if len(scores) not in {0, 2}:
            raise ScrapeError(f"RFU match {external_id} contains an incomplete score.")
        home_score, away_score = (map(int, scores) if scores else (None, None))
        guildford_points = home_score if location == "Home" else away_score
        opposition_points = away_score if location == "Home" else home_score

        card_text = wrapper.get_text(" ", strip=True).casefold()
        if "postponed" in card_text:
            status = "postponed"
        elif "cancelled" in card_text or "canceled" in card_text or "abandoned" in card_text:
            status = "cancelled"
        elif guildford_points is not None:
            status = "completed"
        else:
            status = default_status

        source_url = urljoin(RFU_BASE_URL, match_link.get("href", ""))
        _validate_card_url(source_url, external_id, str(team_id))
        record = {
            "external_match_id": external_id,
            "season": season,
            "date": match_date.isoformat(),
            "league": league_node.get_text(" ", strip=True) if league_node else None,
            "opposition": opposition,
            "location": location,
            "guildford_points": guildford_points,
            "opposition_points": opposition_points,
            "status": status,
            "source_url": source_url,
        }
        previous = matches.get(external_id)
        if previous and previous != record:
            raise ScrapeError(f"RFU match {external_id} appeared with conflicting data.")
        matches[external_id] = record
    return list(matches.values())


def scrape_rfu(*, rfu_season, team_id="9045", diagnostics_dir=None):
    canonical_season(rfu_season)
    url = RFU_LIST_URL.format(season=rfu_season, team_id=team_id)
    diagnostics_path = Path(diagnostics_dir) if diagnostics_dir else None
    if diagnostics_path:
        diagnostics_path.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage", "--disable-file-access"],
        )
        page = browser.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            _reject_block_page(page)
            _dismiss_cookie_notice(page)
            page.get_by_role("heading", name="Guildford", exact=True).wait_for(timeout=30_000)
            if str(team_id) not in page.url or rfu_season not in page.url:
                raise ScrapeError("The RFU page redirected to an unexpected team or season.")

            fixture_html = _activate_tab_and_capture(page, "fixtures")
            result_html = _activate_tab_and_capture(page, "results")
            fixtures = parse_match_cards(
                fixture_html, rfu_season=rfu_season, team_id=team_id, default_status="scheduled"
            )
            results = parse_match_cards(
                result_html, rfu_season=rfu_season, team_id=team_id, default_status="unknown"
            )
            combined = {item["external_match_id"]: item for item in fixtures}
            combined.update({item["external_match_id"]: item for item in results})
            if not combined:
                raise ScrapeError("The RFU page did not expose any fixture or result cards.")
            return sorted(combined.values(), key=lambda item: (item["date"], item["external_match_id"]))
        except Exception:
            if diagnostics_path:
                try:
                    page.screenshot(path=str(diagnostics_path / "rfu-page.png"), full_page=True)
                    (diagnostics_path / "rfu-page.html").write_text(
                        _sanitize_html(page.content()), encoding="utf-8"
                    )
                except Exception:
                    pass
            raise
        finally:
            browser.close()


def build_snapshot(matches, *, rfu_season):
    return {
        "source": "rfu-page",
        "season": canonical_season(rfu_season),
        "scraped_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "matches": matches,
    }


def submit_snapshot(snapshot, *, endpoint, secret, run_id):
    if not endpoint.lower().startswith("https://"):
        raise ScrapeError("RFU_SYNC_URL must be an HTTPS URL.")
    body = json.dumps(snapshot, separators=(",", ":"), sort_keys=True).encode()
    timestamp = str(int(time.time()))
    message = f"{timestamp}\n{run_id}\n".encode() + body
    signature = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    request = Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "User-Agent": "GuildfordTeamsheetSync/1.0",
            "X-RFU-Timestamp": timestamp,
            "X-RFU-Run-ID": run_id,
            "X-RFU-Signature": signature,
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            response_body = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise ScrapeError(f"The Teamsheet app rejected the snapshot ({exc.code}): {detail}") from exc
    except URLError as exc:
        raise ScrapeError("The Teamsheet app could not be reached.") from exc
    try:
        return json.loads(response_body)
    except json.JSONDecodeError as exc:
        raise ScrapeError("The Teamsheet app returned an invalid response.") from exc


def _activate_tab_and_capture(page, tab_id):
    tab = page.locator(f"li[data-tab-id='{tab_id}']")
    button = tab.locator("button")
    if button.count() != 1:
        raise ScrapeError(f"The RFU {tab_id.title()} tab is missing.")
    button.click(force=True)
    try:
        page.wait_for_function(
            "tabId => document.querySelector(`li[data-tab-id='${tabId}']`)?.classList.contains('active')",
            tab_id,
            timeout=15_000,
        )
        page.wait_for_timeout(500)
    except PlaywrightTimeoutError as exc:
        raise ScrapeError(f"The RFU {tab_id.title()} tab did not activate.") from exc
    return page.content()


def _dismiss_cookie_notice(page):
    button = page.get_by_role("button", name=re.compile("Disagree and close", re.I))
    if button.count():
        try:
            button.click(timeout=3_000)
        except PlaywrightTimeoutError:
            pass


def _reject_block_page(page):
    evidence = f"{page.title()} {page.locator('body').inner_text(timeout=10_000)[:2000]}".casefold()
    blocked = ("captcha", "access denied", "just a moment", "request blocked", "cloudfront")
    if any(marker in evidence for marker in blocked):
        raise ScrapeError("The RFU page presented a browser challenge or access block.")


def _parse_rfu_date(value):
    try:
        return datetime.strptime(value, "%A, %d %b %Y").date()
    except ValueError as exc:
        raise ScrapeError(f"RFU date '{value}' is not recognized.") from exc


def _team_from_link(node):
    query = parse_qs(urlparse(node.get("href", "")).query)
    team_ids = query.get("team", [])
    name = node.get_text(" ", strip=True)
    if len(team_ids) != 1 or not team_ids[0].isdigit() or not name:
        raise ScrapeError("An RFU team link is invalid.")
    return {"id": team_ids[0], "name": name}


def _validate_card_url(url, external_id, team_id):
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in {"englandrugby.com", "www.englandrugby.com"}
        or parsed.path != "/fixtures-and-results/match-centre-community"
        or query.get("matchId") != [external_id]
        or query.get("team") != [team_id]
    ):
        raise ScrapeError(f"RFU match {external_id} has an invalid source link.")


def _sanitize_html(html):
    soup = BeautifulSoup(html, "html.parser")
    for node in soup.select("script, style, iframe"):
        node.decompose()
    return str(soup)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Scrape Guildford RFU fixtures and submit a signed snapshot.")
    parser.add_argument("--season", default="", help="RFU season in YYYY-YYYY format")
    parser.add_argument("--team-id", default=os.environ.get("RFU_TEAM_ID", "9045"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--diagnostics-dir", default="diagnostics")
    args = parser.parse_args(argv)

    season = args.season or current_rfu_season()
    matches = scrape_rfu(rfu_season=season, team_id=args.team_id, diagnostics_dir=args.diagnostics_dir)
    snapshot = build_snapshot(matches, rfu_season=season)
    summary = [
        f"{item['date']} {item['location']} vs {item['opposition']} ({item['status']})"
        for item in snapshot["matches"]
    ]
    print(f"Scraped {len(summary)} Guildford fixtures for {season}:")
    print("\n".join(summary))
    if args.dry_run:
        return 0

    endpoint = os.environ.get("RFU_SYNC_URL", "")
    secret = os.environ.get("RFU_SYNC_SECRET", "")
    if not endpoint or not secret:
        raise ScrapeError("RFU_SYNC_URL and RFU_SYNC_SECRET are required unless --dry-run is used.")
    run_id = "-".join(
        filter(None, (os.environ.get("GITHUB_RUN_ID"), os.environ.get("GITHUB_RUN_ATTEMPT")))
    ) or str(uuid.uuid4())
    result = submit_snapshot(snapshot, endpoint=endpoint, secret=secret, run_id=run_id)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ScrapeError as exc:
        print(f"RFU sync failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
