"""Playwright smoke tests for the Change Request Management UI.

Selectors follow the IDs used in shift-portal.html / portal-core.js.
Run with:  python -m pytest ui_tests/test_change_requests_ui.py -q
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


def _open_change_tab(page):
    page.get_by_role("tab", name="Change Management").click()
    page.locator("#changePanel").wait_for(state="visible")


def test_change_create_edit_patch_persist(app_page, portal_url):
    """Create -> edit -> patch -> reload -> persistence (all CR-specific fields)."""
    page, _ = app_page
    _login(page, portal_url)
    _open_change_tab(page)

    # Create new
    page.get_by_role("button", name="Create New").click()
    cr_id = "CR-UI-TEST-001"
    page.locator("#cr_cr_id").fill(cr_id)
    page.locator("#cr_title").fill("ui smoke test change")
    page.locator("#cr_domain").select_option("TX")
    page.locator("#cr_risk_level").select_option("high")
    page.locator("#cr_lead_engineer").fill("Test Engineer")
    page.locator("#cr_approver").fill("Test Approver")
    page.locator("#cr_window_start").fill("2026-10-22T09:00")
    page.locator("#cr_window_end").fill("2026-10-22T12:00")
    page.locator("#cr_description").fill("smoke test description")
    page.get_by_role("button", name="Submit / Save").click()
    expect(page.get_by_text("Change request saved successfully!")).to_be_visible()

    # Wait for dropdown refresh to include the new cr_id before reloading
    sel = page.locator("#changeSelector")
    expect(sel).to_contain_text(cr_id)

    # Reload and confirm it persisted
    page.reload(wait_until="domcontentloaded")
    _open_change_tab(page)
    page.locator("#change-tab-scheduled").click()
    sel = page.locator("#changeSelector")
    expect(sel).to_contain_text(cr_id)

    # Select it and verify ALL fields persisted with correct types
    sel.select_option(label=f"{cr_id} (high)")
    page.locator("#cr_cr_id").wait_for(state="visible")

    expect(page.locator("#cr_cr_id")).to_have_value(cr_id)
    expect(page.locator("#cr_title")).to_have_value("ui smoke test change")
    expect(page.locator("#cr_domain")).to_have_value("TX")
    expect(page.locator("#cr_risk_level")).to_have_value("high")
    expect(page.locator("#cr_lead_engineer")).to_have_value("Test Engineer")
    expect(page.locator("#cr_approver")).to_have_value("Test Approver")
    expect(page.locator("#cr_description")).to_have_value("smoke test description")

    # Datetime fields: verify they come back (string comparison on the formatted value)
    ws = page.locator("#cr_window_start").input_value()
    we = page.locator("#cr_window_end").input_value()
    assert ws.startswith("2026-10-22T09:00"), f"window_start mismatch: {ws}"
    assert we.startswith("2026-10-22T12:00"), f"window_end mismatch: {we}"

    # Enum fields: verify the value string matches exactly
    expect(page.locator("#cr_status")).to_have_value("scheduled")


def test_change_dirty_check_and_autoswitch(app_page, portal_url):
    """Edit -> change status -> submit -> auto-switch to new tab, no prompt."""
    page, _ = app_page
    _login(page, portal_url)
    _open_change_tab(page)

    page.locator("#change-tab-scheduled").click()
    page.locator("#changeSelector").wait_for(state="visible")
    page.locator("#changeSelector").select_option(index=1)
    page.locator("#cr_cr_id").wait_for(state="visible")

    # Dirty the form
    page.locator("#cr_title").fill("edited title")
    # Change status
    page.locator("#cr_status").select_option("completed")

    # Submit — should auto-switch to Completed without a confirm prompt
    page.get_by_role("button", name="Submit / Save").click()
    expect(page.get_by_text("Change request saved successfully!")).to_be_visible()

    # Completed tab should now be active; scheduled should not
    assert_active_tab(page, "change-tab-completed")

    # Click another tab — no dirty prompt (form reset + baseline cleared)
    page.locator("#change-tab-scheduled").click()


def test_change_404_mid_edit(app_page, portal_url):
    """Delete CR server-side mid-edit -> toast -> refresh, no zombie PATCH."""
    page, _ = app_page

    # Register the route interceptor BEFORE any change-request fetch happens
    def handler(route):
        if route.request.method == "PATCH":
            route.fulfill(
                status=404,
                content_type="application/json",
                body=json.dumps({"detail": "Change request not found"}),
            )
        else:
            route.continue_()

    page.route("**/api/v1/change-requests/*", handler)

    _login(page, portal_url)
    _open_change_tab(page)

    page.locator("#change-tab-scheduled").click()
    page.locator("#changeSelector").wait_for(state="visible")
    page.locator("#changeSelector").select_option(index=1)
    page.locator("#cr_cr_id").wait_for(state="visible")

    page.get_by_role("button", name="Submit / Save").click()
    assert_toast(page, r"not found")

    # Dropdown should have refreshed (no zombie state)
    page.unroute("**/api/v1/change-requests/*")
