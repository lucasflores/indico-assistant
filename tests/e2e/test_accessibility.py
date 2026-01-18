"""E2E accessibility checks for the chat widget.

These tests are skipped by default because they require running Indico and
Chainlit instances with the widget enabled. They provide smoke coverage for
keyboard and screen reader affordances.
"""

import pytest

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skip(reason="Requires running Indico + Chainlit servers"),
]


@pytest.fixture
def playwright():
    """Provide playwright instance (requires pytest-playwright)."""
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            yield p
    except ImportError:
        pytest.skip("pytest-playwright not installed")


@pytest.fixture
def indico_url():
    """Return the base URL of the Indico instance for testing."""
    import os

    return os.environ.get("INDICO_TEST_URL", "http://localhost:8080")


class TestKeyboardAccessibility:
    """Keyboard affordances for the widget trigger and panel."""

    def test_widget_exposes_aria_and_role(self, playwright, indico_url):
        browser = playwright.chromium.launch()
        context = browser.new_context()
        page = context.new_page()
        try:
            page.goto(indico_url)
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(750)

            widget = page.query_selector("[class*='cl-widget'], [class*='chainlit']")
            assert widget is not None, "Widget root should exist"
            aria_label = widget.get_attribute("aria-label")
            role = widget.get_attribute("role")
            assert aria_label == "Indico Assistant chat"
            assert role == "complementary"
        finally:
            context.close()
            browser.close()


class TestScreenReaderSupport:
    """ARIA live region presence for message announcements."""

    def test_live_region_exists(self, playwright, indico_url):
        browser = playwright.chromium.launch()
        context = browser.new_context()
        page = context.new_page()
        try:
            page.goto(indico_url)
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(750)

            live_region = page.query_selector("#assistant-live-region")
            assert live_region is not None, "Live region should be injected for screen readers"
            assert live_region.get_attribute("aria-live") == "polite"
        finally:
            context.close()
            browser.close()
