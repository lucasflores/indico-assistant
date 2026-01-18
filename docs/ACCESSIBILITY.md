# Chat Widget Accessibility Guide

This guide explains how to validate keyboard and screen reader behavior for the
Indico Assistant chat widget.

## Keyboard Navigation Checklist

1. Navigate to any Indico page with the widget enabled.
2. Press `Tab` until the chat button is focused (button has an outline).
3. Press `Enter` or `Space` to open the chat panel.
4. Within the panel, press `Tab` / `Shift+Tab` to cycle through focusable
   elements (message list, input, send/feedback controls). Focus should remain
   trapped inside the panel.
5. Press `Escape` to close the panel and return focus to the button.

## Screen Reader Validation (VoiceOver/NVDA/JAWS)

1. Ensure the widget is enabled and visible on the page.
2. Start the screen reader and move focus to the chat button. Confirm it
   announces "Indico Assistant chat" with role "complementary" and a button
   description.
3. Activate the button to open the panel. Confirm the panel announces as a
   dialog/region with label "Indico Assistant chat panel".
4. Send a message and wait for an assistant response. Verify the latest
   response is announced via the live region (polite) without stealing focus.
5. Press `Escape` to close the panel and verify focus returns to the trigger
   button.

## Notes

- The widget injects a polite live region (`#assistant-live-region`) and applies
  ARIA labels/roles to the root, button, and panel elements. These attributes
  are applied after the Chainlit widget mounts.
- If the page uses custom themes, ensure CSS variables are available so the
  widget can inherit colors while maintaining sufficient contrast.
