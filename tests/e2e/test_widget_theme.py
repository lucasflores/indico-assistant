"""E2E tests for chat widget theme synchronization.

These tests verify that the Chainlit Copilot widget honors the page theme
(light/dark) when mounting. They are skipped by default because they require
running Indico and Chainlit servers.
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


class TestChatWidgetTheme:
    """Theme synchronization scenarios for the chat widget."""

    def test_widget_uses_dark_theme_when_preferred(self, playwright, indico_url):
        """Widget should mount with dark theme when browser prefers dark."""
        browser = playwright.chromium.launch()
        context = browser.new_context(color_scheme="dark")
        page = context.new_page()

        try:
            page.goto(indico_url)
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(750)

            # Theme detection sets a diagnostic global for verification
            theme = page.evaluate("() => window.__IndicoAssistantTheme || null")
            assert theme == "dark"
        finally:
            context.close()
            browser.close()

    def test_widget_updates_theme_when_class_changes(self, playwright, indico_url):
        """Widget should reflect theme change when page toggles theme class."""
        browser = playwright.chromium.launch()
        context = browser.new_context(color_scheme="light")
        page = context.new_page()

        try:
            page.goto(indico_url)
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(500)

            # Force dark theme via body class and trigger observer
            page.evaluate("() => document.body.classList.add('dark-theme')")
            page.wait_for_timeout(500)

            theme = page.evaluate("() => window.__IndicoAssistantTheme || null")
            assert theme == "dark"
        finally:
            context.close()
            browser.close()
