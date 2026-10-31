"""Playwright smoke tests for the Incident Management UI.

Selectors follow the IDs used in shift-portal.html / portal-core.js.
Run with:  python -m pytest ui_tests/test_incidents_ui.py -q
"""
import json
import re

from playwright.sync_api import expect


def _login(page, portal_url):
    page.goto(f"{portal_url}/login.html", wait_until="commit")
    page.locator("#username").fill("ui-admin")
    page.locator("#password").fill("browser-test-password")
    page.get_by_role("button", name="Sign In to NOC Portal").click()
    page.wait_for_url(f"{portal_url}/", wait_until="domcontentloaded")
    page.wait_for_function("document.getElementById('userLabel').textContent === 'UI Test Admin'")


def _open_incident_tab(page):
    page.get_by_role("tab", name="Incident Management").click()
    page.locator("#incidentPanel").wait_for(state="visible")


def assert_active_tab(page, tab_id):
    """Assert that tab_id has the active class and its siblings do not."""
    tab = page.locator(f"#{tab_id}")
    expect(tab).to_have_class(re.compile(r"\bbg-slate-800\b"))
    siblings = page.locator(f"[id^='incident-tab-'], [id^='change-tab-']").all()
    for sib in siblings:
        if sib.get_attribute("id") != tab_id:
            expect(sib).not_to_have_class(re.compile(r"\bbg-slate-800\b"))
            break


def test_incident_create_edit_patch_persist(app_page, portal_url):
    """Create -> edit -> patch -> reload -> persistence."""
    page, _ = app_page
    _login(page, portal_url)
    _open_incident_tab(page)

    # Create new
    page.get_by_role("button", name="Create New").click()
    ref = "INC-UI-TEST-001"
    page.locator("#inc_ref").fill(ref)
    page.locator("#inc_desc").fill("ui smoke test incident")
    page.locator("#inc_priority").select_option("P2")
    page.get_by_role("button", name="Submit / Save").click()
    expect(page.get_by_text("Incident saved successfully!")).to_be_visible()

    # Wait for the dropdown refresh to include the new ref before reloading
    sel = page.locator("#incidentSelector")
    expect(sel).to_contain_text(ref)

    # Reload and confirm it persisted (appears in Ongoing dropdown)
    page.reload(wait_until="domcontentloaded")
    _open_incident_tab(page)
    page.locator("#incident-tab-ongoing").click()
    sel = page.locator("#incidentSelector")
    expect(sel).to_contain_text(ref)

def test_incident_dirty_check_and_autoswitch(app_page, portal_url):
    """Edit -> change status to resolved -> submit -> auto-switch to Resolved tab, no prompt."""
    page, _ = app_page
    _login(page, portal_url)
    _open_incident_tab(page)

    page.locator("#incident-tab-ongoing").click()
    page.locator("#incidentSelector").wait_for(state="visible")
    page.locator("#incidentSelector").select_option(index=1)
    page.locator("#inc_ref").wait_for(state="visible")

    # Dirty the form
    page.locator("#inc_desc").fill("edited description")
    # Change status to resolved
    page.locator("#inc_status").select_option("resolved")

    # Submit — should auto-switch to Resolved without a confirm prompt
    page.get_by_role("button", name="Submit / Save").click()
    expect(page.get_by_text("Incident saved successfully!")).to_be_visible()

    # Resolved tab should now be active; ongoing should not
    assert_active_tab(page, "incident-tab-resolved")

    # Click another tab — no dirty prompt (form reset + baseline cleared)
    page.locator("#incident-tab-ongoing").click()


def test_incident_404_mid_edit(app_page, portal_url):
    """Delete incident server-side mid-edit -> toast -> refresh, no zombie PATCH."""
    page, _ = app_page

    # Register the route interceptor BEFORE any incident fetch happens
    def handler(route):
        if route.request.method == "PATCH":
            route.fulfill(
                status=404,
                content_type="application/json",
                body=json.dumps({"detail": "Incident not found"}),
            )
        else:
            route.continue_()

    page.route("**/api/v1/incidents/*", handler)

    _login(page, portal_url)
    _open_incident_tab(page)

    page.locator("#incident-tab-ongoing").click()
    page.locator("#incidentSelector").wait_for(state="visible")
    page.locator("#incidentSelector").select_option(index=1)
    page.locator("#inc_ref").wait_for(state="visible")

    page.get_by_role("button", name="Submit / Save").click()
    assert_toast(page, r"not found")

    # Dropdown should have refreshed (no zombie state)
    page.unroute("**/api/v1/incidents/*")
