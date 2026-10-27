import os
from typing import Generator
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from playwright.sync_api import Browser, Page, sync_playwright


PORTAL_URL = os.getenv("E2E_PORTAL_URL", "http://127.0.0.1:8001").rstrip("/")
USERNAME = os.getenv("E2E_USERNAME", "testadmin")
PASSWORD = os.getenv("E2E_PASSWORD", "IntegrationAdmin123!")
PORTAL_HOST = urlsplit(PORTAL_URL).hostname


@pytest.fixture(scope="module")
def browser() -> Generator[Browser, None, None]:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        yield browser


@pytest.mark.skipif(
    "E2E_PORTAL_URL" not in os.environ,
    reason="Set E2E_PORTAL_URL to run against the disposable real-backend stack.",
)
def test_admin_creates_knowledge_post_through_real_api(browser: Browser):
    if PORTAL_HOST not in {"127.0.0.1", "localhost"}:
        pytest.fail("The contract test must only target the local disposable integration app.")

    context = browser.new_context()
    page: Page = context.new_page()
    page.set_default_timeout(15000)
    title = f"Playwright contract check {uuid4()}"
    created_article = None
    try:
        page.goto(f"{PORTAL_URL}/login.html")
        page.locator("#username").fill(USERNAME)
        page.locator("#password").fill(PASSWORD)
        page.get_by_role("button", name="Sign In to NOC Portal").click()
        page.wait_for_url(f"{PORTAL_URL}/shift-portal.html", wait_until="domcontentloaded")

        page.get_by_role("tab", name="Knowledge Hub").click()
        page.get_by_role("button", name="Create Post").click()
        page.locator("#knowledgeForm [name='domain']").select_option("ran")
        page.get_by_placeholder("Issue title").fill(title)
        page.get_by_placeholder("Symptoms").fill("Contract test symptom")
        page.get_by_placeholder("Root cause").fill("Contract test root cause")
        page.get_by_placeholder("Troubleshooting steps").fill("Contract test troubleshooting")
        page.get_by_placeholder("Resolution").fill("Contract test resolution")

        with page.expect_response(
            lambda response: response.url.endswith("/api/v1/knowledge-hub")
            and response.request.method == "POST"
        ) as response_info:
            page.get_by_role("button", name="Save article").click()

        response = response_info.value
        assert response.status == 201, f"Knowledge article creation failed: {response.text()}"
        created_article = response.json()
        assert created_article["issue_title"] == title
        assert created_article["domain"] == "ran"
        page.get_by_role("heading", name=title, exact=True).wait_for(state="visible")

        listed_response = page.request.get(f"{PORTAL_URL}/api/v1/knowledge-hub")
        assert listed_response.ok, f"Knowledge article listing failed: {listed_response.text()}"
        assert any(
            article["id"] == created_article["id"]
            and article["issue_title"] == title
            for article in listed_response.json()
        )
    finally:
        if created_article is not None:
            cleanup_response = page.request.put(
                f"{PORTAL_URL}/api/v1/knowledge-hub/{created_article['id']}",
                data={
                    "domain": created_article["domain"],
                    "issue_title": created_article["issue_title"],
                    "symptoms": created_article["symptoms"],
                    "root_cause": created_article["root_cause"],
                    "troubleshooting_steps": created_article["troubleshooting_steps"],
                    "resolution": created_article["resolution"],
                    "reference_link": created_article["reference_link"],
                    "is_active": False,
                    "expected_updated_at": created_article["updated_at"],
                },
            )
            assert cleanup_response.ok, f"Could not deactivate test article: {cleanup_response.text()}"
        context.close()
