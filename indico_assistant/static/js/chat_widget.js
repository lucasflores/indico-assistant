/**
 * Indico Assistant panel (spec 020; the page side of contracts/panel.md).
 *
 * Injected (deferred, cacheable) only for logged-in users with the assistant enabled. The assistant is
 * Chainlit's full app in a panel docked to the right of every page, with its Past Chats sidebar. It comes
 * back open, on the same conversation, after every navigation:
 * - the per-user, per-browser state (open, width, current conversation) is kept in localStorage;
 * - an inline <head> snippet (plugin.py) reserves an open panel's width before the page paints;
 * - the frame signs in with a fresh token for this page (it carries the page's event) sent by
 *   postMessage, never in a URL, and reports back: ready, the open conversation, Indico links, Esc.
 * Page views with the panel closed cost nothing but this file and a launcher button.
 */
(function () {
  "use strict";

  const SCRIPT = document.currentScript;
  const USER = SCRIPT && SCRIPT.dataset.user;
  if (!USER) return;
  const STATE_KEY = `indico-assistant:${USER}`;
  const CONFIG_URL = "/api/assistant/widget/config";
  const DEFAULT_WIDTH = 440;
  const MIN_WIDTH = 320;
  const NARROW = 768;  // below this the panel covers the page instead of pushing it
  const root = document.documentElement;

  let state = loadState();
  let panel = null;
  let frame = null;
  let config = null;  // {chainlitUrl, authToken, theme}
  let frameHello = false;

  function loadState() {
    try {
      return Object.assign({ open: false, width: DEFAULT_WIDTH, threadId: null },
                           JSON.parse(localStorage.getItem(STATE_KEY) || "{}"));
    } catch (e) {
      return { open: false, width: DEFAULT_WIDTH, threadId: null };
    }
  }

  function saveState() {
    try { localStorage.setItem(STATE_KEY, JSON.stringify(state)); } catch (e) { /* private mode: not kept */ }
  }

  function setMode(mode) {
    root.dataset.assistantPanel = mode;
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
  }

  function detectTheme() {
    const style = getComputedStyle(document.documentElement);
    for (const key of ["--indico-theme", "--ui-theme", "--theme", "--color-scheme"]) {
      const value = style.getPropertyValue(key).trim().toLowerCase();
      if (value === "dark" || value === "light") return value;
    }
    if (document.body.classList.contains("dark-theme")) return "dark";
    const match = getComputedStyle(document.body).backgroundColor.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
    if (match) {
      const [r, g, b] = match.slice(1, 4).map(Number);
      if (0.2126 * r + 0.7152 * g + 0.0722 * b < 115) return "dark";
      return "light";
    }
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
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

  function sendLogin() {
    if (!frameHello || !config) return;
    frameHello = false;  // one sign-in per load of the login page
    postToFrame({ type: "login", token: config.authToken, threadId: state.threadId || null, theme: detectTheme() });
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

  function buildPanel() {
    panel = document.createElement("aside");
    panel.id = "assistant-panel";
    panel.setAttribute("aria-label", "Indico Assistant");
    panel.innerHTML = `
      <div id="assistant-panel-handle" role="separator" aria-orientation="vertical" aria-label="Resize the assistant"></div>
      <div id="assistant-panel-bar">
        <span>Indico Assistant</span>
        <button id="assistant-panel-close" type="button" aria-label="Close the assistant" title="Close (Esc)">×</button>
      </div>
      <div id="assistant-panel-placeholder" role="status">Loading the assistant…</div>`;
    frame = document.createElement("iframe");
    frame.id = "assistant-panel-frame";
    frame.title = "Indico Assistant chat";
    frame.setAttribute("allow", "clipboard-write");
    panel.appendChild(frame);
    document.body.appendChild(panel);
    panel.querySelector("#assistant-panel-close").addEventListener("click", closePanel);
    panel.addEventListener("keydown", (event) => { if (event.key === "Escape") closePanel(); });
    bindResize(panel.querySelector("#assistant-panel-handle"));
    applyWidth();
  }

  async function openPanel() {
    if (panel) return;
    injectStylesheet();
    hideLauncher();
    state.open = true;
    saveState();
    setMode("loading");
    buildPanel();  // the frame appears at once, at its width; the placeholder shows until `ready`
    try {
      config = await fetchConfig();
    } catch (e) {
      showUnavailable();
      return;
    }
    const origin = chainlitOrigin();
    frame.src = `${origin}/public/indico-login.html?parent=${encodeURIComponent(window.location.origin)}`;
    sendLogin();
  }

  function closePanel() {
    if (panel) panel.remove();
    panel = null;
    frame = null;
    root.style.marginRight = "";
    state.open = false;
    saveState();
    setMode("closed");
    showLauncher();
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

  function launcher() {
    let button = document.getElementById("assistant-launcher");
    if (!button) {
      button = document.createElement("button");
      button.type = "button";
      button.id = "assistant-launcher";
      button.title = "Indico Assistant";
      button.setAttribute("aria-label", "Open the Indico Assistant");
      button.textContent = "\u{1F4AC}";
      button.addEventListener("click", openPanel);
      document.body.appendChild(button);
    }
    return button;
  }

  function showLauncher() {
    injectStylesheet();
    launcher().hidden = false;
  }

  function hideLauncher() {
    const button = document.getElementById("assistant-launcher");
    if (button) button.hidden = true;
  }

  function start() {
    window.addEventListener("message", onMessage);
    window.addEventListener("resize", applyWidth);
    if (state.open) {
      openPanel();  // reopens on this page without a click; focus stays on the page (FR-003)
    } else {
      setMode("closed");
      showLauncher();
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
