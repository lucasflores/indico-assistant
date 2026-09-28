# Panel contract: the Indico page and the Chainlit frame

**Feature**: 020-chat-persistence

Two scripts talk with `window.postMessage`:

- the **page**, `indico_assistant/static/js/chat_widget.js` on the Indico origin;
- the **frame**, `chainlit_app/public/indico-login.html` plus `custom_js` `chainlit_app/public/indico_panel.js`,
  on the Chainlit origin.

Every message is `{"source": "indico-assistant", "type": …, …}`. Each side checks `event.origin` against the
other side's origin and ignores anything else. The page learns the frame's origin from the widget config
(`chainlitUrl`). The frame learns the page's origin from a query parameter on `indico-login.html`
(`?parent=<origin>`), and checks it against Chainlit's configured `allow_origins`.

## Page → frame

| `type` | Fields | When |
|---|---|---|
| `login` | `token`, `threadId` (or null), `theme` (`light`/`dark`) | The login page reports `hello`. The page answers with a fresh token from `/widget/config?event_id=<page event>` |
| `theme` | `theme` | Indico's theme changes while the panel is open |

## Frame → page

| `type` | Fields | When |
|---|---|---|
| `hello` | | `indico-login.html` loaded and is listening |
| `ready` | | The chat is drawn: the page removes its placeholder (FR-006a) |
| `thread` | `threadId` (null for a new chat) | The frame's route changed to `/thread/<id>` or `/`: the page stores it (FR-001) |
| `navigate` | `url` | A link to the Indico origin was clicked in an answer: the page sets `location.href` (FR-006b) |
| `close` | | Esc was pressed inside the frame (FR-006d) |
| `login_failed` | `status` | `POST /auth/jwt` failed: the page shows "Assistant unavailable" and keeps the page working (FR-006, constitution IV) |

## Page state (per user, per browser)

`localStorage["indico-assistant:<user id>"] = {open, width, threadId}` (see data-model.md). The page writes it on:

- open and close;
- the end of a resize drag;
- every `thread` message.

The inline `<head>` snippet reads only `open` and `width`, to reserve the margin before the first paint.

## Panel behaviour

- **Open.** Right-docked, full height, `width` px, default 440, clamped to 320…50% of the viewport. The page
  gets `margin-right: width`. Below 768 px wide, the panel covers the page instead, with no margin.
- **Resize.** Dragging the left edge resizes it; the width is saved on release.
- **Close.** The panel's own close button, Esc in the page while the panel has focus, or `close` from the
  frame. The margin is removed and `open: false` is stored.
- **Reopen on load.** The frame loads without taking focus (FR-003). No `focus()` is called; the user tabs or
  clicks in.
- **Launcher.** The existing lazy launcher button opens the panel when it is closed. While the panel is open,
  the button is hidden.

## Test hooks (the browser walk, T021)

| Hook | Meaning |
|---|---|
| `#assistant-launcher` | the launcher button (hidden while the panel is open) |
| `#assistant-panel`, `#assistant-panel-frame`, `#assistant-panel-handle`, `#assistant-panel-close` | the panel, its iframe, the drag handle, the close button |
| `<html data-assistant-panel="closed\|loading\|ready\|unavailable">` | the panel's state |
| `window.__assistantReadyAt` | `performance.now()` when the frame reported `ready` (SC-002) |
| `window.__assistantInitialMargin` | the `margin-right` the inline `<head>` snippet reserved, before the page painted (FR-006a) |
