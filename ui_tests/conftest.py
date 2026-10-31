# Re-export shared fixtures from test_portal_ui so all ui_tests modules can use them.
from ui_tests.test_portal_ui import (  # noqa: F401
    app_page,
    browser,
    portal_url,
)


def assert_active_tab(page, tab_id):
    """Assert that tab_id has the active class and at least one sibling does not."""
    from playwright.sync_api import expect
    import re
    tab = page.locator(f"#{tab_id}")
    expect(tab).to_have_class(re.compile(r"\bbg-slate-800\b"))
    siblings = page.locator("[id^='incident-tab-'], [id^='change-tab-']").all()
    for sib in siblings:
        if sib.get_attribute("id") != tab_id:
            expect(sib).not_to_have_class(re.compile(r"\bbg-slate-800\b"))
            break
def assert_toast(page, pattern):
    """Assert that a toast/message matching pattern is visible."""
    from playwright.sync_api import expect
    import re
    if isinstance(pattern, str):
        pattern = re.compile(pattern, re.IGNORECASE)
    expect(page.get_by_text(pattern)).to_be_visible()
