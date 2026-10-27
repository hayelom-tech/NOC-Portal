import json
import mimetypes
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Generator
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Browser, Route, sync_playwright


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def portal_url():
    class PortalHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
                return
            request_path = urlsplit(self.path).path
            if request_path.startswith("/assets/"):
                asset_root = (PROJECT_ROOT / "ui" / "assets").resolve()
                asset = (asset_root / request_path.removeprefix("/assets/")).resolve()
                if asset_root not in asset.parents or not asset.is_file():
                    self.send_error(404)
                    return
                content = asset.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", mimetypes.guess_type(asset.name)[0] or "application/octet-stream")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return
            pages = {
                "/": PROJECT_ROOT / "ui" / "pages" / "shift-portal.html",
                "/shift-portal.html": PROJECT_ROOT / "ui" / "pages" / "shift-portal.html",
                "/admin.html": PROJECT_ROOT / "ui" / "pages" / "admin.html",
                "/login.html": PROJECT_ROOT / "ui" / "pages" / "login.html",
            }
            page = pages.get(self.path)
            if page is None:
                self.send_error(404)
                return
            html = page.read_text(encoding="utf-8").replace(
                "</head>",
                "<style>.hidden { display: none !important; }</style></head>",
                1,
            )
            content = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

    server = ThreadingHTTPServer(("127.0.0.1", 0), PortalHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    thread.join()
    server.server_close()


@pytest.fixture(scope="session")
def browser() -> Generator[Browser, None, None]:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=os.getenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE"),
            headless=True,
        )
        yield browser


@pytest.fixture
def app_page(browser: Browser, portal_url: str):
    context = browser.new_context()
    page = context.new_page()
    page.add_init_script("window.tailwind = window.tailwind || {};")
    created_articles = []
    roster_teams = [{"id": 1, "name": "Power", "challenge_domain": "power"}]
    session = {"authenticated": False}
    base_url = urlsplit(portal_url)
    origin = f"{base_url.scheme}://{base_url.netloc}"

    def fulfill(route: Route, body, status=200):
        route.fulfill(status=status, content_type="application/json", body=json.dumps(body))

    def handle_request(route: Route):
        request = route.request
        request_url = urlsplit(request.url)
        if f"{request_url.scheme}://{request_url.netloc}" != origin:
            route.abort()
            return
        if not request_url.path.startswith("/api/v1/"):
            route.continue_()
            return

        if request_url.path == "/api/v1/auth/me":
            if not session["authenticated"]:
                fulfill(route, {"detail": "Authentication required"}, status=401)
                return
            fulfill(route, {
                "id": 1,
                "username": "ui-admin",
                "email": "ui-admin@example.invalid",
                "full_name": "UI Test Admin",
                "role": "admin",
                "avatar_key": "default",
            })
        elif request_url.path == "/api/v1/auth/login" and request.method == "POST":
            session["authenticated"] = True
            fulfill(route, {"user": {
                "username": "ui-admin",
                "full_name": "UI Test Admin",
                "role": "admin",
            }})
        elif request_url.path == "/api/v1/auth/permissions":
            fulfill(route, {"edit_process_articles": "yes"})
        elif request_url.path == "/api/v1/knowledge-hub/pending":
            fulfill(route, [])
        elif request_url.path == "/api/v1/knowledge-hub/recent":
            recent = {domain: None for domain in ("power", "ran", "tx", "core")}
            for article in reversed(created_articles):
                if recent[article["domain"]] is None:
                    recent[article["domain"]] = article
            fulfill(route, recent)
        elif request_url.path == "/api/v1/knowledge-hub":
            if request.method == "POST":
                payload = request.post_data_json
                article = {
                    **payload,
                    "id": len(created_articles) + 1,
                    "created_at": "2026-10-21T00:00:00Z",
                }
                created_articles.append(article)
                fulfill(route, article, status=201)
            else:
                fulfill(route, created_articles)
        elif request_url.path == "/api/v1/notifications":
            fulfill(route, [])
        elif request_url.path == "/api/v1/users":
            fulfill(route, [])
        elif request_url.path == "/api/v1/audit-logs":
            fulfill(route, [])
        elif request_url.path == "/api/v1/roster-teams":
            if request.method == "POST":
                payload = request.post_data_json
                team = {"id": len(roster_teams) + 1, **payload}
                roster_teams.append(team)
                fulfill(route, team, status=201)
            else:
                fulfill(route, roster_teams)
        elif request_url.path.startswith("/api/v1/roster-teams/") and request.method == "PATCH":
            team_id = int(request_url.path.rsplit("/", 1)[-1])
            team = next(team for team in roster_teams if team["id"] == team_id)
            team.update(request.post_data_json)
            fulfill(route, team)
        elif request_url.path.startswith("/api/v1/shifts"):
            fulfill(route, [])
        elif request_url.path in {"/api/v1/roster", "/api/v1/l2-roster"}:
            fulfill(route, [])
        else:
            fulfill(route, {"detail": f"Unexpected UI test API request: {request_url.path}"}, status=404)

    page.route("**/*", handle_request)
    yield page, created_articles
    context.close()


def test_admin_can_create_and_see_knowledge_post(app_page, portal_url):
    page, created_articles = app_page
    page.goto(f"{portal_url}/login.html", wait_until="commit")
    page.locator("#username").fill("ui-admin")
    page.locator("#password").fill("browser-test-password")
    page.get_by_role("button", name="Sign In to NOC Portal").click()
    page.wait_for_url(f"{portal_url}/", wait_until="domcontentloaded")
    page.wait_for_function("document.getElementById('userLabel').textContent === 'UI Test Admin'")
    page.set_default_timeout(8000)
    page.get_by_role("tab", name="Knowledge Hub").click()
    page.get_by_role("button", name="Create Post").click()

    title = "UI test: packet loss recovery"
    page.locator("#knowledgeForm [name='domain']").select_option("ran")
    page.get_by_placeholder("Issue title").fill(title)
    page.get_by_placeholder("Symptoms").fill("Intermittent packet loss is observed.")
    page.get_by_placeholder("Root cause").fill("A congested uplink.")
    page.get_by_placeholder("Troubleshooting steps").fill("Check interface utilization.")
    page.get_by_placeholder("Resolution").fill("Move traffic to the alternate link.")
    page.get_by_role("button", name="Save article").click()

    page.get_by_role("heading", name=title).wait_for(state="visible")
    assert len(created_articles) == 1
    assert created_articles[0]["issue_title"] == title
    assert created_articles[0]["domain"] == "ran"


def test_theme_toggle_persists_after_reload(app_page, portal_url):
    page, _ = app_page
    page.goto(f"{portal_url}/login.html", wait_until="commit")
    page.locator("#username").fill("ui-admin")
    page.locator("#password").fill("browser-test-password")
    page.get_by_role("button", name="Sign In to NOC Portal").click()
    toggle = page.locator("#themeToggle")
    toggle.wait_for(state="visible")

    assert page.locator("html").evaluate("(element) => element.classList.contains('dark')")
    toggle.click()
    assert not page.locator("html").evaluate("(element) => element.classList.contains('dark')")
    assert page.evaluate("localStorage.getItem('theme')") == "light"

    page.reload(wait_until="domcontentloaded")
    page.locator("#themeToggle").wait_for(state="visible")
    assert not page.locator("html").evaluate("(element) => element.classList.contains('dark')")
    assert page.locator("#themeToggle").get_attribute("aria-pressed") == "false"


def test_admin_can_register_and_map_roster_team_labels(app_page, portal_url):
    page, _ = app_page
    page.set_default_timeout(8000)
    page.goto(f"{portal_url}/login.html", wait_until="commit")
    page.locator("#username").fill("ui-admin")
    page.locator("#password").fill("browser-test-password")
    page.get_by_role("button", name="Sign In to NOC Portal").click()
    page.wait_for_url(f"{portal_url}/", wait_until="domcontentloaded")

    page.goto(f"{portal_url}/admin.html", wait_until="domcontentloaded")
    page.get_by_role("heading", name="Front Office team label mappings").wait_for(state="visible")
    page.locator("#rosterTeamForm [name='name']").fill("Fiber Transmission")
    page.locator("#rosterTeamForm [name='challenge_domain']").select_option("tx")
    page.get_by_role("button", name="Add team label").click()

    row = page.locator("#rosterTeamsRows tr").filter(has_text="Fiber Transmission")
    row.wait_for(state="visible")
    domain = row.get_by_role("combobox")
    assert domain.input_value() == "tx"
    domain.select_option("power")
    row.get_by_role("button", name="Save").click()
    page.locator("#toast").get_by_text(
        "Updated the challenge domain for Fiber Transmission."
    ).wait_for(state="visible")
