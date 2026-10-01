/**
 * Indico Assistant panel (spec 020; the page side of contracts/panel.md).
 *
 * Injected (deferred, cacheable) only for logged-in users with the assistant enabled. The assistant is
 * Chainlit's full app in a panel docked to the right of every page, with its Past Chats sidebar. It comes
 * back open, on the same conversation, after every navigation:
 * - the per-user state is kept in the browser: open and width in localStorage, the open conversation per tab
 *   (sessionStorage), so two tabs keep their own; a new tab starts on the last one used;
 * - each Indico login starts on a new chat: the script tag's data-login is a token set at login (plugin.py),
 *   and a conversation kept from an earlier login is not reopened;
 * - an inline <head> snippet (plugin.py) reserves an open panel's width before the page paints;
 * - the frame signs in with a fresh token for this page (it carries the page's event) sent by
 *   postMessage, never in a URL, and reports back: ready, the open conversation, Indico links, Esc.
 * Page views with the panel closed cost nothing but this file and the button that opens it.
 */
(function () {
  "use strict";

  const SCRIPT = document.currentScript;
  const USER = SCRIPT && SCRIPT.dataset.user;
  if (!USER) return;
  const STATE_KEY = `indico-assistant:${USER}`;
  const TAB_KEY = `indico-assistant-thread:${USER}`;  // this tab's conversation (review, PR #5)
  const LOGIN = SCRIPT.dataset.login || "";  // changes at each Indico login: then a new chat (Lucas, 2026-10-01)
  const TAB_LOGIN_KEY = `indico-assistant-login:${USER}`;  // the login this tab's conversation belongs to
  const CONFIG_URL = "/api/assistant/widget/config";
  // the panel's widths, from plugin.py (PANEL_WIDTHS), which reserves the same width before the page paints
  const DEFAULT_WIDTH = Number(SCRIPT.dataset.defaultWidth) || 440;
  const MIN_WIDTH = Number(SCRIPT.dataset.minWidth) || 320;
  const NARROW = Number(SCRIPT.dataset.narrow) || 768;  // below this the panel covers the page instead of pushing it
  const root = document.documentElement;

  let state = loadState();
  let panel = null;
  let frame = null;
  let config = null;  // {chainlitUrl, authToken}
  let frameHello = false;

  function loadState() {
    let loaded = { open: false, width: DEFAULT_WIDTH, threadId: null };
    try {
      loaded = Object.assign(loaded, JSON.parse(localStorage.getItem(STATE_KEY) || "{}"));
      if (LOGIN && loaded.login !== LOGIN) {  // the first page since logging in: a new chat, not the last one
        loaded.threadId = null;
        loaded.login = LOGIN;
        localStorage.setItem(STATE_KEY, JSON.stringify(loaded));
      }
      if (LOGIN && sessionStorage.getItem(TAB_LOGIN_KEY) !== LOGIN) {  // a tab left open since an earlier login
        sessionStorage.removeItem(TAB_KEY);
        sessionStorage.setItem(TAB_LOGIN_KEY, LOGIN);
      }
      const tab = sessionStorage.getItem(TAB_KEY);  // set once this tab has had a conversation, even a new chat
      if (tab !== null) loaded.threadId = tab || null;
    } catch (e) { /* private mode: nothing kept */ }
    return loaded;
  }

  function saveState() {
    try {
      const stored = JSON.parse(localStorage.getItem(STATE_KEY) || "{}").login;
      if (!LOGIN || !stored || stored === LOGIN)  // (fresh-review: a tab from an earlier login keeps only its own)
        localStorage.setItem(STATE_KEY, JSON.stringify(state));  // (its threadId: where a new tab starts)
      sessionStorage.setItem(TAB_KEY, state.threadId || "");
    } catch (e) { /* private mode: not kept */ }
  }

  function setMode(mode) {
    root.dataset.assistantPanel = mode;
    const report = panel && panel.querySelector("#assistant-panel-report");
    if (report) report.disabled = mode !== "ready";  // the frame must be there to draw the form (spec 021)
  }

  function clampWidth(width) {
    return Math.round(Math.max(MIN_WIDTH, Math.min(width || DEFAULT_WIDTH, window.innerWidth / 2)));
  }

  function applyWidth() {
    if (!panel) return;
    if (window.innerWidth < NARROW) {
      panel.style.width = "100vw";
      root.style.marginRight = "";
      return;
    }
    const width = clampWidth(state.width);
    panel.style.width = `${width}px`;
    root.style.marginRight = `${width}px`;
    root.style.setProperty("--assistant-width", `${width}px`);  // (where the edge tab sits while open)
    const handle = panel.querySelector("#assistant-panel-handle");  // (its value, for screen readers)
    handle.setAttribute("aria-valuenow", width);
    handle.setAttribute("aria-valuemax", Math.round(window.innerWidth / 2));
  }


  function eventIdFromPage() {
    const match = window.location.pathname.match(/^\/event\/(\d+)(\/|$)/);
    return match ? match[1] : null;
  }

  function chainlitOrigin() {
    try { return new URL(config.chainlitUrl).origin; } catch (e) { return null; }
  }

  function postToFrame(message) {
    const origin = chainlitOrigin();
    if (frame && frame.contentWindow && origin) {
      frame.contentWindow.postMessage(Object.assign({ source: "indico-assistant" }, message), origin);
    }
  }

  // the title bar's Report button: the chat draws an empty report form (spec 021 R2, contracts/panel.md)
  function askForReport() {
    postToFrame({ type: "report" });
    if (frame) frame.focus();  // the user pressed a button: the form is where they type next
  }

  function sendLogin() {
    if (!frameHello || !config) return;
    frameHello = false;  // one sign-in per load of the login page
    postToFrame({ type: "login", token: config.authToken, threadId: state.threadId || null });
  }

  function injectStylesheet() {
    if (document.getElementById("assistant-panel-css")) return;
    const link = document.createElement("link");
    link.id = "assistant-panel-css";
    link.rel = "stylesheet";
    const script = new URL(SCRIPT.src, window.location.href);
    link.href = `${script.origin}/api/assistant/widget/css/chat_widget.css${script.search}`;  // same ?v= as the script
    document.head.appendChild(link);
  }

  function showUnavailable() {
    setMode("unavailable");
    const placeholder = panel && panel.querySelector("#assistant-panel-placeholder");
    if (placeholder) {
      placeholder.textContent = "The assistant is unavailable right now.";
      placeholder.hidden = false;
    }
  }

  async function fetchConfig() {
    const eventId = eventIdFromPage();
    const response = await fetch(CONFIG_URL + (eventId ? `?event_id=${eventId}` : ""),
                                 { credentials: "same-origin", cache: "no-store" });
    if (!response.ok) throw new Error(`config ${response.status}`);
    const data = await response.json();
    if (!data.enabled || !data.authToken || !data.chainlitUrl) throw new Error("assistant unavailable");
    return data;
  }

  async function conversationExists(threadId) {
    if (!threadId) return false;
    try {
      const response = await fetch(`/api/assistant/sessions/${encodeURIComponent(threadId)}?messages=0`,
                                   { credentials: "same-origin", cache: "no-store" });
      // only a definite answer forgets it: a 429 or 5xx is a passing problem, not a gone conversation
      return !(response.status === 404 || response.status === 403 || response.status === 422);
    } catch (e) {
      return true;  // unknown: let Chainlit try
    }
  }

  function buildPanel() {
    panel = document.createElement("aside");
    panel.id = "assistant-panel";
    panel.setAttribute("aria-label", "Indico Assistant");
    panel.innerHTML = `
      <div id="assistant-panel-handle" role="separator" aria-orientation="vertical" aria-label="Resize the assistant"
           tabindex="0" aria-valuemin="${MIN_WIDTH}"></div>
      <div id="assistant-panel-bar">
        <span>Indico Assistant</span>
        <button id="assistant-panel-report" type="button" aria-label="Report a problem" title="Report a problem" disabled>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
               stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><path d="M4 22v-7"/></svg>
        </button>
        <button id="assistant-panel-close" type="button" aria-label="Hide the assistant" title="Hide (Esc)">»</button>
      </div>
      <div id="assistant-panel-placeholder" role="status">Loading the assistant…</div>`;
    frame = document.createElement("iframe");
    frame.id = "assistant-panel-frame";
    frame.title = "Indico Assistant chat";
    frame.setAttribute("allow", "clipboard-write");
    panel.appendChild(frame);
    document.body.appendChild(panel);
    panel.querySelector("#assistant-panel-close").addEventListener("click", closePanel);
    panel.querySelector("#assistant-panel-report").addEventListener("click", askForReport);
    panel.addEventListener("keydown", (event) => { if (event.key === "Escape") closePanel(); });
    bindResize(panel.querySelector("#assistant-panel-handle"));
    applyWidth();
  }

  async function openPanel() {
    if (panel) return;
    document.querySelectorAll("#assistant-panel.assistant-closing").forEach((e) => e.remove());  // (reopened mid-slide)
    injectStylesheet();
    state.open = true;
    saveState();
    setMode("loading");
    buildPanel();  // the frame appears at once, at its width; the placeholder shows until `ready`
    syncToggle();
    try {
      // the remembered conversation may be gone (deleted in another tab, retention): then a new chat, not
      // Chainlit's "Couldn't resume" error. Asked alongside the config, so it costs no time.
      const [data, known] = await Promise.all([fetchConfig(), conversationExists(state.threadId)]);
      config = data;
      if (!known && state.threadId) {
        state.threadId = null;
        saveState();
      }
    } catch (e) {
      showUnavailable();
      return;
    }
    const origin = chainlitOrigin();
    frame.src = `${origin}/public/indico-login.html?parent=${encodeURIComponent(window.location.origin)}`;
    sendLogin();
  }

  function closePanel() {
    const closing = panel;
    const hadFocus = closing && closing.contains(document.activeElement);
    panel = null;
    frame = null;
    slide();
    if (closing) {
      closing.classList.add("assistant-closing");
      setTimeout(() => closing.remove(), SLIDE_MS);
    }
    root.style.marginRight = "";
    root.style.removeProperty("--assistant-width");
    state.open = false;
    saveState();
    setMode("closed");
    syncToggle();
    if (hadFocus) toggleButton().focus();  // (focus goes back to what opens it)
  }

  // a click slides the panel in and out; a panel restored on page load is simply there (FR-003)
  const SLIDE_MS = 200;
  function slide() {
    root.classList.add("assistant-sliding");
    clearTimeout(slide.timer);
    slide.timer = setTimeout(() => root.classList.remove("assistant-sliding"), SLIDE_MS + 50);
  }

  function onMessage(event) {
    if (!config || event.origin !== chainlitOrigin() || !frame || event.source !== frame.contentWindow) return;
    const data = event.data || {};
    if (data.source !== "indico-assistant") return;
    switch (data.type) {
      case "hello":
        frameHello = true;
        sendLogin();
        break;
      case "ready": {
        const placeholder = panel && panel.querySelector("#assistant-panel-placeholder");
        if (placeholder) placeholder.hidden = true;
        window.__assistantReadyAt = performance.now();
        setMode("ready");
        break;
      }
      case "thread":
        state.threadId = typeof data.threadId === "string" ? data.threadId : null;
        saveState();
        break;
      case "navigate":
        try {
          const url = new URL(data.url);
          if (url.origin === window.location.origin) window.location.href = url.href;
        } catch (e) { /* ignore malformed */ }
        break;
      case "close":
        closePanel();
        break;
      case "login_failed":
        showUnavailable();
        break;
    }
  }

  function bindResize(handle) {
    // the keyboard too: arrows move the edge by 20 px (Shift: 100), Home/End go to the narrowest/widest
    handle.addEventListener("keydown", (event) => {
      if (window.innerWidth < NARROW) return;
      const step = event.shiftKey ? 100 : 20;
      const width = { ArrowLeft: state.width + step, ArrowRight: state.width - step,
                      Home: MIN_WIDTH, End: window.innerWidth / 2 }[event.key];
      if (width === undefined) return;
      event.preventDefault();
      state.width = clampWidth(width);
      applyWidth();
      saveState();
    });
    handle.addEventListener("pointerdown", (event) => {
      if (window.innerWidth < NARROW) return;
      event.preventDefault();
      handle.setPointerCapture(event.pointerId);
      frame.style.pointerEvents = "none";  // the frame would swallow the moves
      const move = (e) => {
        state.width = clampWidth(window.innerWidth - e.clientX);
        applyWidth();
      };
      const stop = () => {
        handle.removeEventListener("pointermove", move);
        handle.removeEventListener("pointerup", stop);
        handle.removeEventListener("pointercancel", stop);
        if (frame) frame.style.pointerEvents = "";
        saveState();
      };
      handle.addEventListener("pointermove", move);
      handle.addEventListener("pointerup", stop);
      handle.addEventListener("pointercancel", stop);
    });
  }

  // the one control that opens and closes the panel: a tab on the page's right edge, which moves with the panel
  // (it replaced a bottom-right bubble, which covered Indico's own buttons and did not read as a side panel)
  function toggleButton() {
    let button = document.getElementById("assistant-toggle");
    if (button) return button;
    button = document.createElement("button");
    button.type = "button";
    button.id = "assistant-toggle";
    button.setAttribute("aria-controls", "assistant-panel");
    button.innerHTML = '<span class="icon-bubble-quote" aria-hidden="true"></span><span>Assistant</span>'
      + '<span class="assistant-chevron" aria-hidden="true"></span>';  // (Indico's icon font)
    document.body.appendChild(button);
    button.addEventListener("click", () => {
      slide();
      if (panel) closePanel(); else openPanel();
    });
    return button;
  }

  function syncToggle() {
    const button = toggleButton();
    button.setAttribute("aria-expanded", String(!!panel));
    button.title = panel ? "Hide the assistant" : "Open the Indico Assistant";
  }

  function start() {
    window.addEventListener("message", onMessage);
    window.addEventListener("resize", applyWidth);
    if (state.open) {
      openPanel();  // reopens on this page without a click; focus stays on the page (FR-003)
    } else {
      setMode("closed");
      injectStylesheet();
      syncToggle();
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
