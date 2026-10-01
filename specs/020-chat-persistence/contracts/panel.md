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
| `login` | `token`, `threadId` (or null) | The login page reports `hello`. The page answers with a fresh token from `/widget/config?event_id=<page event>` |

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

`localStorage["indico-assistant:<user id>"] = {open, width, threadId, login}` (see data-model.md). The page writes it on:

- open and close;
- the end of a resize drag;
- every `thread` message.

The inline `<head>` snippet reads only `open` and `width`, to reserve the margin before the first paint.

## Panel behaviour

- **Open.** Right-docked, full height, `width` px, default 440, clamped to 320…50% of the viewport. The page
  gets `margin-right: width`. Below 768 px wide, the panel covers the page instead, with no margin.
- **Resize.** Dragging the left edge resizes it; the width is saved on release.
- **Close.** The tab, the panel's own hide button (»), Esc in the page while the panel has focus, or `close`
  from the frame. The margin is removed and `open: false` is stored. If the panel had focus, it goes to the tab.
- **Reopen on load.** The frame loads without taking focus (FR-003). No `focus()` is called; the user tabs or
  clicks in.
- **Tab.** One tab on the page's right edge, halfway down, opens and closes the panel (`aria-expanded`). While
  the panel is open, the tab sits on the panel's edge. A click slides the panel in and out; a panel restored on
  load does not slide. Below 768 px the open panel covers the tab, and » hides it.
  (Changed after spec 020, thread B: a bottom-right bubble covered Indico's own buttons, such as an event's share
  button, and did not read as a side panel. A button in Indico's session bar was tried too: that bar scrolls
  away, and on event pages it runs out of room while the panel is open.)

## Test hooks (the browser walk, T021)

| Hook | Meaning |
|---|---|
| `#assistant-toggle[aria-expanded]` | the tab that opens and closes the panel |
| `#assistant-panel`, `#assistant-panel-frame`, `#assistant-panel-handle`, `#assistant-panel-close` | the panel, its iframe, the drag handle, the close button |
| `<html data-assistant-panel="closed\|loading\|ready\|unavailable">` | the panel's state |
| `window.__assistantReadyAt` | `performance.now()` when the frame reported `ready` (SC-002) |
| `window.__assistantInitialMargin` | the `margin-right` the inline `<head>` snippet reserved, before the page painted (FR-006a) |

**Theme (changed while building):** Indico is light on every page. An event page's dark grey is only the
meeting theme's backdrop, so reading the page's background made the panel flip between light and dark as
the user moved around. The page sends no theme any more. Chainlit starts light (`default_theme`), and its own
switch is remembered across pages.
