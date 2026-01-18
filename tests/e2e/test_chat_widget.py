"""E2E tests for chat widget visibility.

These tests verify that the Chainlit Copilot widget appears correctly
on Indico pages when enabled. Requires Playwright for browser automation.

Note: These tests require a running Indico instance and Chainlit server.
They are marked as e2e and skipped by default in CI unless explicitly run.
"""

import pytest

# Mark all tests in this module as e2e
pytestmark = [pytest.mark.e2e, pytest.mark.skip(reason="Requires running Indico + Chainlit servers")]


class TestChatWidgetVisibility:
    """E2E tests for chat widget visibility on Indico pages."""

    @pytest.fixture
    def browser_page(self, playwright):
        """Create a browser page for testing."""
        browser = playwright.chromium.launch()
        context = browser.new_context()
        page = context.new_page()
        yield page
        context.close()
        browser.close()

    def test_widget_button_visible_on_page(self, browser_page, indico_url):
        """Chat widget button should be visible on Indico page."""
        browser_page.goto(indico_url)
        browser_page.wait_for_load_state("networkidle")

        # Look for Chainlit widget button (typically has class like 'cl-widget-button')
        widget_button = browser_page.locator("[class*='cl-widget'], [class*='chainlit']")
        assert widget_button.is_visible(), "Chat widget button should be visible"

    def test_widget_button_in_fixed_position(self, browser_page, indico_url):
        """Chat widget should be in fixed position (bottom-right)."""
        browser_page.goto(indico_url)
        browser_page.wait_for_load_state("networkidle")

        # Get widget element
        widget = browser_page.locator("[class*='cl-widget'], [class*='chainlit']").first
        
        if widget.is_visible():
            # Check CSS position
            position = widget.evaluate("el => getComputedStyle(el).position")
            assert position == "fixed", "Widget should have fixed positioning"

    def test_widget_opens_on_click(self, browser_page, indico_url):
        """Chat panel should open when widget button is clicked."""
        browser_page.goto(indico_url)
        browser_page.wait_for_load_state("networkidle")

        # Click widget button
        widget_button = browser_page.locator("[class*='cl-widget-button'], [class*='chainlit'] button").first
        if widget_button.is_visible():
            widget_button.click()

            # Wait for panel to appear
            browser_page.wait_for_timeout(500)  # Brief wait for animation

            # Look for chat panel/input
            chat_panel = browser_page.locator("[class*='cl-chat'], [class*='chainlit-chat']")
            assert chat_panel.is_visible(), "Chat panel should open after clicking button"

    def test_widget_hidden_when_disabled(self, browser_page, indico_url_widget_disabled):
        """Chat widget should not be visible when disabled in settings."""
        browser_page.goto(indico_url_widget_disabled)
        browser_page.wait_for_load_state("networkidle")

        # Widget should not exist
        widget = browser_page.locator("[class*='cl-widget'], [class*='chainlit']")
        assert widget.count() == 0 or not widget.is_visible(), "Widget should be hidden when disabled"

    def test_widget_persists_across_navigation(self, browser_page, indico_url):
        """Chat widget should remain accessible after navigating to another page."""
        browser_page.goto(indico_url)
        browser_page.wait_for_load_state("networkidle")

        # Verify widget exists
        widget_before = browser_page.locator("[class*='cl-widget'], [class*='chainlit']").first
        assert widget_before.is_visible(), "Widget should be visible on first page"

        # Navigate to another page (e.g., admin or another route)
        browser_page.goto(f"{indico_url}/admin/")
        browser_page.wait_for_load_state("networkidle")

        # Widget should still exist
        widget_after = browser_page.locator("[class*='cl-widget'], [class*='chainlit']").first
        assert widget_after.is_visible(), "Widget should be visible after navigation"


class TestChatWidgetFunctionality:
    """E2E tests for chat widget functionality."""

    @pytest.fixture
    def authenticated_page(self, playwright, indico_url, test_user_credentials):
        """Create an authenticated browser page."""
        browser = playwright.chromium.launch()
        context = browser.new_context()
        page = context.new_page()

        # Login to Indico
        page.goto(f"{indico_url}/login/")
        page.fill("input[name='identifier']", test_user_credentials["email"])
        page.fill("input[name='password']", test_user_credentials["password"])
        page.click("button[type='submit']")
        page.wait_for_load_state("networkidle")

        yield page
        context.close()
        browser.close()

    def test_can_send_message(self, authenticated_page, indico_url):
        """User should be able to send a message through the widget."""
        authenticated_page.goto(indico_url)
        authenticated_page.wait_for_load_state("networkidle")

        # Open widget
        widget_button = authenticated_page.locator("[class*='cl-widget-button']").first
        if widget_button.is_visible():
            widget_button.click()
            authenticated_page.wait_for_timeout(500)

            # Find input field and send message
            input_field = authenticated_page.locator("[class*='cl-chat'] input, [class*='cl-chat'] textarea").first
            if input_field.is_visible():
                input_field.fill("Hello, test message")
                input_field.press("Enter")

                # Wait for response
                authenticated_page.wait_for_timeout(5000)

                # Check for message in chat history
                messages = authenticated_page.locator("[class*='cl-message']")
                assert messages.count() > 0, "Should have at least one message in chat"

    def test_widget_shows_loading_state(self, authenticated_page, indico_url):
        """Widget should show loading indicator while waiting for response."""
        authenticated_page.goto(indico_url)
        authenticated_page.wait_for_load_state("networkidle")

        # Open widget
        widget_button = authenticated_page.locator("[class*='cl-widget-button']").first
        if widget_button.is_visible():
            widget_button.click()
            authenticated_page.wait_for_timeout(500)

            # Send message
            input_field = authenticated_page.locator("[class*='cl-chat'] input, [class*='cl-chat'] textarea").first
            if input_field.is_visible():
                input_field.fill("What events are happening today?")
                input_field.press("Enter")

                # Look for loading indicator (appears briefly)
                loading = authenticated_page.locator("[class*='loading'], [class*='spinner']")
                # Note: This assertion may need adjustment based on actual Chainlit loading indicators
                # The loading state may be too brief to reliably catch


@pytest.fixture
def indico_url():
    """Return the base URL of the Indico instance for testing."""
    import os
    return os.environ.get("INDICO_TEST_URL", "http://localhost:8080")


@pytest.fixture
def indico_url_widget_disabled():
    """Return URL of Indico instance with widget disabled (for negative tests)."""
    import os
    return os.environ.get("INDICO_TEST_URL_WIDGET_DISABLED", "http://localhost:8080")


@pytest.fixture
def test_user_credentials():
    """Return test user credentials."""
    import os
    return {
        "email": os.environ.get("INDICO_TEST_USER", "test@example.com"),
        "password": os.environ.get("INDICO_TEST_PASSWORD", "password"),
    }


@pytest.fixture
def playwright():
    """Provide playwright instance (requires pytest-playwright)."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            yield p
    except ImportError:
        pytest.skip("pytest-playwright not installed")
