/**
 * Indico Assistant Chat Widget
 *
 * This script loads the Chainlit Copilot widget and configures it with
 * settings from the IndicoAssistant global (provided by get_vars_js()).
 *
 * Features:
 * - Dynamic script loading of Chainlit Copilot
 * - JWT-based authentication for logged-in users
 * - Theme detection (light/dark mode)
 * - Graceful degradation when Chainlit server is unavailable
 *
 * @see specs/008-chat-widget/plan.md for architecture details
 */

(function () {
  "use strict";

  // Check if IndicoAssistant config is available
  if (typeof IndicoAssistant === "undefined") {
    console.warn("[IndicoAssistant] Configuration not found, widget disabled");
    return;
  }

  // Check if widget is enabled
  if (!IndicoAssistant.enabled) {
    return;
  }

  // Check for Chainlit server URL
  if (!IndicoAssistant.chainlitUrl) {
    return;
  }

  const THEME_DATA_ATTR = "data-chainlit-theme";
  const LIVE_REGION_ID = "assistant-live-region";
  const ACCESSIBILITY_LABEL = "Indico Assistant chat";
  const STATUS_ID = "assistant-widget-status";
  const INLINE_STYLE_ID = "assistant-inline-style";
  const INLINE_STYLE_TEXT = `
/* Primary selectors (when Chainlit exposes cl-* classes) */
:root[data-chainlit-theme="light"] [class*="cl-widget"] [class*="cl-chat"],
:root[data-chainlit-theme="light"] [class*="chainlit"] [class*="chat"],
#chainlit-copilot [class*="cl-chat"],
#chainlit-copilot [class*="chat"],
#chainlit-copilot [data-testid*="chat"],
#chainlit-copilot [class*="conversation"],
#chainlit-copilot [class*="panel"],
#chainlit-copilot [class*="container"] {
  background: rgba(255, 255, 255, 0.9) !important;
  border: 1px solid rgba(0, 0, 0, 0.08) !important;
  box-shadow: 0 8px 26px rgba(0, 0, 0, 0.12) !important;
}

:root[data-chainlit-theme="dark"] [class*="cl-widget"] [class*="cl-chat"],
:root[data-chainlit-theme="dark"] [class*="chainlit"] [class*="chat"],
#chainlit-copilot [data-theme="dark"] [class*="cl-chat"],
#chainlit-copilot [data-theme="dark"] [class*="chat"],
#chainlit-copilot [data-theme="dark"] [data-testid*="chat"],
#chainlit-copilot [data-theme="dark"] [class*="conversation"],
#chainlit-copilot [data-theme="dark"] [class*="panel"],
#chainlit-copilot [data-theme="dark"] [class*="container"] {
  background: rgba(17, 24, 39, 0.9) !important;
  border: 1px solid rgba(255, 255, 255, 0.12) !important;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5) !important;
}

:root[data-chainlit-theme="light"] [class*="cl-widget-button"],
:root[data-chainlit-theme="light"] [class*="chainlit"] button,
:root[data-chainlit-theme="dark"] [class*="cl-widget-button"],
:root[data-chainlit-theme="dark"] [class*="chainlit"] button,
#chainlit-copilot button,
#chainlit-copilot [role="button"] {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 36 36'%3E%3Ccircle cx='18' cy='18' r='18' fill='%23ffffff' fill-opacity='0.15'/%3E%3Ccircle cx='18' cy='18' r='14' fill='none' stroke='%23ffffff' stroke-width='2'/%3E%3Ctext x='18' y='22' text-anchor='middle' font-size='14' font-family='Arial, sans-serif' fill='%23ffffff' font-weight='700'%3Ei%3C/text%3E%3C/svg%3E") !important;
  background-repeat: no-repeat !important;
  background-position: center !important;
  background-size: 20px 20px !important;
}
`;

  /**
   * Parse an RGB/RGBA/hex CSS color string into an RGB tuple.
   * @param {string} value
   * @returns {{r:number,g:number,b:number}|null}
   */
  function parseCssColor(value) {
    if (!value) {
      return null;
    }
    const trimmed = value.trim();
    const rgbMatch = trimmed.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/i);
    if (rgbMatch) {
      return {
        r: Number(rgbMatch[1]),
        g: Number(rgbMatch[2]),
        b: Number(rgbMatch[3]),
      };
    }
    const hexMatch = trimmed.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i);
    if (hexMatch) {
      const hex = hexMatch[1];
      const expand = hex.length === 3 ? hex.split("").map((c) => c + c).join("") : hex;
      const int = parseInt(expand, 16);
      return {
        r: (int >> 16) & 255,
        g: (int >> 8) & 255,
        b: int & 255,
      };
    }
    return null;
  }

  /**
   * Compute a simple relative luminance value (0 = dark, 1 = light).
   * @param {{r:number,g:number,b:number}} rgb
   * @returns {number}
   */
  function getLuminance(rgb) {
    if (!rgb) {
      return 1;
    }
    const toLinear = (channel) => {
      const c = channel / 255;
      return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
    };
    const r = toLinear(rgb.r);
    const g = toLinear(rgb.g);
    const b = toLinear(rgb.b);
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  }

  /**
   * Infer theme from an arbitrary CSS color value.
   * @param {string} colorValue
   * @returns {'light'|'dark'|null}
   */
  function inferThemeFromColor(colorValue) {
    const rgb = parseCssColor(colorValue);
    if (!rgb) {
      return null;
    }
    const luminance = getLuminance(rgb);
    return luminance < 0.45 ? "dark" : "light";
  }

  /**
   * Detect the current Indico theme using CSS variables and fallbacks.
   * @returns {'light'|'dark'} The detected theme
   */
  function detectTheme() {
    const rootStyle = getComputedStyle(document.documentElement);

    const cssThemeKeys = ["--indico-theme", "--ui-theme", "--theme", "--color-scheme"];
    for (const key of cssThemeKeys) {
      const value = rootStyle.getPropertyValue(key).trim().toLowerCase();
      if (value === "dark" || value === "light") {
        return value;
      }
    }

    // Check for Indico's dark mode class on body
    if (document.body.classList.contains("dark-theme")) {
      return "dark";
    }

    // Try to infer theme from background colors
    const bgCandidates = [
      rootStyle.getPropertyValue("--page-background"),
      rootStyle.getPropertyValue("--body-bg"),
      rootStyle.getPropertyValue("--background-color"),
      getComputedStyle(document.body).backgroundColor,
    ];

    for (const color of bgCandidates) {
      const inferred = inferThemeFromColor(color);
      if (inferred) {
        return inferred;
      }
    }

    // Check for prefers-color-scheme media query
    if (
      window.matchMedia &&
      window.matchMedia("(prefers-color-scheme: dark)").matches
    ) {
      return "dark";
    }

    return "light";
  }

  /**
   * Apply the detected theme to the document for CSS overrides and diagnostics.
   * @param {'light'|'dark'} theme
   */
  function applyTheme(theme) {
    if (!theme) {
      return;
    }
    document.documentElement.setAttribute(THEME_DATA_ATTR, theme);
    window.__IndicoAssistantTheme = theme;
  }

  /**
   * Inject the widget stylesheet located alongside the JS bundle.
   */
  function injectStylesheet() {
    if (!document.getElementById(INLINE_STYLE_ID)) {
      const style = document.createElement("style");
      style.id = INLINE_STYLE_ID;
      style.textContent = INLINE_STYLE_TEXT;
      document.head.appendChild(style);
    }

    const scriptEl = document.currentScript;
    if (!scriptEl || !scriptEl.src) {
      return;
    }

    try {
      const scriptUrl = new URL(scriptEl.src, window.location.href);
      const cssUrl = `${scriptUrl.origin}/api/assistant/widget/css/chat_widget.css`;
      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = cssUrl;
      link.dataset.indicoAssistantCss = "true";
      document.head.appendChild(link);
    } catch (err) {
      // Inline fallback already applied; ignore fetch errors.
    }
  }

  function injectShadowStyles(root) {
    if (!root || root.__assistantStyled) {
      return;
    }
    const style = document.createElement("style");
    style.textContent = INLINE_STYLE_TEXT;
    root.appendChild(style);
    root.__assistantStyled = true;
  }

  function injectShadowHostStyles() {
    const host = document.getElementById("chainlit-copilot");
    if (host && host.shadowRoot) {
      injectShadowStyles(host.shadowRoot);
      const inner = host.shadowRoot.getElementById("cl-shadow-root");
      if (inner) {
        injectShadowStyles(inner);
      }
    }
  }

  function ensureShadowStyles(retries = 20, delay = 150) {
    // Try repeatedly because Chainlit attaches the shadow root asynchronously.
    const attempt = () => {
      injectShadowHostStyles();
      const host = document.getElementById("chainlit-copilot");
      const applied = !!host?.shadowRoot?.getElementById(INLINE_STYLE_ID) ||
        !!host?.shadowRoot?.getElementById("cl-shadow-root")?.querySelector(`#${INLINE_STYLE_ID}`);
      if (!applied && retries > 0) {
        retries -= 1;
        setTimeout(attempt, delay);
      }
    };
    attempt();
  }

  function watchShadowRoots() {
    // Apply immediately to existing shadow roots
    document.querySelectorAll("*").forEach((node) => {
      if (node.shadowRoot) {
        injectShadowStyles(node.shadowRoot);
      }
    });
    injectShadowHostStyles();

    const observer = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        mutation.addedNodes.forEach((node) => {
          if (node.shadowRoot) {
            injectShadowStyles(node.shadowRoot);
          }
          injectShadowHostStyles();
          if (node.querySelectorAll) {
            node.querySelectorAll("*").forEach((child) => {
              if (child.shadowRoot) {
                injectShadowStyles(child.shadowRoot);
              }
            });
          }
        });
      }
    });

    observer.observe(document.documentElement, {
      childList: true,
      subtree: true,
    });
  }

  function injectIntoIframe(iframe) {
    try {
      const doc = iframe.contentDocument || iframe.contentWindow?.document;
      if (!doc || doc.getElementById(INLINE_STYLE_ID)) {
        return;
      }
      const style = doc.createElement("style");
      style.id = INLINE_STYLE_ID;
      style.textContent = INLINE_STYLE_TEXT;
      doc.head.appendChild(style);
    } catch (err) {
      // Cross-origin or not ready yet; ignore.
    }
  }

  function watchIframes() {
    // Apply to existing iframes (Chainlit widget uses an iframe)
    document.querySelectorAll("iframe").forEach((iframe) => {
      if (iframe.dataset.assistantStyled) {
        return;
      }
      iframe.addEventListener("load", () => injectIntoIframe(iframe));
      injectIntoIframe(iframe);
      iframe.dataset.assistantStyled = "true";
    });

    const observer = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        mutation.addedNodes.forEach((node) => {
          if (node.tagName === "IFRAME") {
            const iframe = node;
            iframe.addEventListener("load", () => injectIntoIframe(iframe));
            injectIntoIframe(iframe);
          } else if (node.querySelectorAll) {
            node.querySelectorAll("iframe").forEach((iframe) => {
              iframe.addEventListener("load", () => injectIntoIframe(iframe));
              injectIntoIframe(iframe);
            });
          }
        });
      }
    });

    observer.observe(document.documentElement, {
      childList: true,
      subtree: true,
    });
  }

  /**
   * Create or update a transient status bubble for loading/error messages.
   * @param {'loading'|'error'|'none'} state
   * @param {string} [message]
   */
  function setStatus(state, message) {
    if (state === "none") {
      if (statusNode && statusNode.parentNode) {
        statusNode.parentNode.removeChild(statusNode);
      }
      statusNode = null;
      return;
    }

    if (!statusNode) {
      statusNode = document.createElement("div");
      statusNode.id = STATUS_ID;
      statusNode.setAttribute("role", "status");
      statusNode.style.position = "fixed";
      statusNode.style.right = "16px";
      statusNode.style.bottom = "16px";
      statusNode.style.zIndex = "2147483000";
      statusNode.style.padding = "10px 12px";
      statusNode.style.borderRadius = "12px";
      statusNode.style.fontSize = "13px";
      statusNode.style.fontFamily = "inherit";
      statusNode.style.boxShadow = "0 8px 24px rgba(0,0,0,0.18)";
      statusNode.style.display = "flex";
      statusNode.style.alignItems = "center";
      statusNode.style.gap = "8px";
      statusNode.style.maxWidth = "260px";
      statusNode.style.pointerEvents = "none";
      document.body.appendChild(statusNode);
    }

    const spinner = "<span style=\"width:10px;height:10px;border:2px solid rgba(255,255,255,0.7);border-top-color:transparent;border-radius:999px;display:inline-block;animation:assistant-spin 0.8s linear infinite;\"></span>";

    if (state === "loading") {
      statusNode.style.background = "#1f77d0";
      statusNode.style.color = "#fff";
      statusNode.innerHTML = `${spinner}<span>${message || "Connecting assistant..."}</span>`;
    } else {
      statusNode.style.background = "#b42318";
      statusNode.style.color = "#fff";
      statusNode.innerHTML = `<span style=\"font-weight:700;\">!</span><span>${message || "Assistant unavailable"}</span>`;
    }

    // Inject minimal keyframes once
    if (!document.getElementById("assistant-spin-style")) {
      const style = document.createElement("style");
      style.id = "assistant-spin-style";
      style.textContent = "@keyframes assistant-spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }";
      document.head.appendChild(style);
    }
  }

  /**
   * Ensure a polite live region exists for announcing new messages.
   * @returns {HTMLElement}
   */
  function ensureLiveRegion() {
    const existing = document.getElementById(LIVE_REGION_ID);
    if (existing) {
      return existing;
    }

    const liveRegion = document.createElement("div");
    liveRegion.id = LIVE_REGION_ID;
    liveRegion.setAttribute("aria-live", "polite");
    liveRegion.setAttribute("role", "status");
    liveRegion.style.position = "absolute";
    liveRegion.style.width = "1px";
    liveRegion.style.height = "1px";
    liveRegion.style.overflow = "hidden";
    liveRegion.style.clip = "rect(0 0 0 0)";
    liveRegion.style.clipPath = "inset(50%)";
    liveRegion.style.whiteSpace = "nowrap";
    liveRegion.style.border = "0";
    liveRegion.style.padding = "0";
    liveRegion.style.margin = "-1px";
    document.body.appendChild(liveRegion);
    return liveRegion;
  }

  /**
   * Locate key widget elements.
   * @returns {{root:HTMLElement|null,toggle:HTMLElement|null,panel:HTMLElement|null}}
   */
  function findWidgetElements() {
    const root = document.querySelector("[class*='cl-widget'], [class*='chainlit']");
    const toggle = root
      ? root.querySelector(
          "button[class*='cl-widget'], button[class*='cl-widget-button'], button[class*='chainlit']"
        )
      : null;
    const panel = root
      ? root.querySelector("[class*='cl-chat'], [class*='chainlit-chat'], [class*='cl-conversation']")
      : null;
    return { root, toggle, panel };
  }

  /**
   * Determine if the panel is currently visible.
   * @param {HTMLElement|null} panel
   * @returns {boolean}
   */
  function isPanelVisible(panel) {
    if (!panel) {
      return false;
    }
    const style = window.getComputedStyle(panel);
    return style.visibility !== "hidden" && style.display !== "none" && panel.offsetParent !== null;
  }

  /**
   * Set ARIA roles/labels on widget elements.
   * @param {HTMLElement|null} root
   * @param {HTMLElement|null} toggle
   * @param {HTMLElement|null} panel
   */
  function applyWidgetAria(root, toggle, panel) {
    if (root && !root.dataset.assistantAria) {
      root.setAttribute("role", "complementary");
      root.setAttribute("aria-label", ACCESSIBILITY_LABEL);
      root.dataset.assistantAria = "true";
    }

    if (toggle && !toggle.dataset.assistantAria) {
      toggle.setAttribute("aria-label", "Open Indico Assistant chat");
      toggle.setAttribute("aria-haspopup", "dialog");
      toggle.dataset.assistantAria = "true";
    }

    if (panel && !panel.dataset.assistantAria) {
      panel.setAttribute("role", "dialog");
      panel.setAttribute("aria-modal", "false");
      panel.setAttribute("aria-label", "Indico Assistant chat panel");
      panel.dataset.assistantAria = "true";
    }
  }

  /**
   * Close the widget panel if possible.
   * @param {HTMLElement|null} panel
   * @param {HTMLElement|null} toggle
   */
  function closeWidget(panel, toggle) {
    if (!isPanelVisible(panel)) {
      return;
    }
    if (!lastFocusedBeforeOpen) {
      lastFocusedBeforeOpen = toggle || document.activeElement;
    }
    if (typeof window.clHideWidget === "function") {
      window.clHideWidget();
    } else if (toggle) {
      toggle.click();
    }

    if (lastFocusedBeforeOpen && typeof lastFocusedBeforeOpen.focus === "function") {
      lastFocusedBeforeOpen.focus();
    }
  }

  /**
   * Focus trap within the widget panel.
   * @param {HTMLElement} panel
   * @param {HTMLElement|null} toggle
   */
  function bindKeyboard(panel, toggle) {
    if (!panel || panel.dataset.assistantKbBound) {
      return;
    }

    const keyHandler = (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        closeWidget(panel, toggle);
        return;
      }

      if (event.key !== "Tab") {
        return;
      }

      const focusableSelectors = [
        "a[href]",
        "button:not([disabled])",
        "textarea:not([disabled])",
        "input:not([disabled])",
        "select:not([disabled])",
        "[tabindex]:not([tabindex='-1'])",
      ];
      const focusable = Array.from(panel.querySelectorAll(focusableSelectors.join(","))).filter(
        (el) => !el.hasAttribute("disabled") && el.getAttribute("tabindex") !== "-1"
      );

      if (focusable.length === 0) {
        return;
      }

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;

      if (event.shiftKey) {
        if (active === first || !panel.contains(active)) {
          event.preventDefault();
          last.focus();
        }
      } else if (active === last) {
        event.preventDefault();
        first.focus();
      }
    };

    panel.addEventListener("keydown", keyHandler, true);
    panel.dataset.assistantKbBound = "true";
  }

  /**
   * Observe message mutations and announce updates via the live region.
   * @param {HTMLElement} panel
   */
  function observeMessagesForLiveRegion(panel) {
    if (!panel || panel.dataset.assistantLiveBound) {
      return;
    }

    const liveRegion = ensureLiveRegion();

    const announceLatest = () => {
      const messages = panel.querySelectorAll("[class*='message']");
      if (!messages.length) {
        return;
      }
      const last = messages[messages.length - 1];
      const text = (last.textContent || "").trim();
      if (text) {
        liveRegion.textContent = text.slice(-500);
      }
    };

    const observer = new MutationObserver(announceLatest);
    observer.observe(panel, { childList: true, subtree: true });
    panel.dataset.assistantLiveBound = "true";
  }

  /**
   * Setup accessibility affordances after widget mount.
   */
  function setupAccessibility() {
    ensureLiveRegion();
    let attempts = 0;
    const maxAttempts = 8;
    let intervalId = null;

    const tick = () => {
      const { root, toggle, panel } = findWidgetElements();

      if (root && isPanelVisible(panel)) {
        lastFocusedBeforeOpen = lastFocusedBeforeOpen || document.activeElement;
      }

      applyWidgetAria(root, toggle, panel);

      if (panel) {
        bindKeyboard(panel, toggle);
        observeMessagesForLiveRegion(panel);
      }

      attempts += 1;
      if (intervalId && (attempts >= maxAttempts || (root && toggle && panel))) {
        clearInterval(intervalId);
      }
    };

    intervalId = setInterval(tick, 400);
    tick();
  }

  let currentTheme = null;
  let lastFocusedBeforeOpen = null;
  let statusNode = null;

  /**
   * Get persisted Chainlit thread ID from localStorage.
   * Chainlit Copilot stores its thread ID under this key by default.
   * @returns {string|null} The thread ID or null if not found
   */
  function getPersistedThreadId() {
    try {
      return localStorage.getItem("chainlit-copilot-thread-id");
    } catch (e) {
      return null;
    }
  }

  /**
   * Load the Chainlit Copilot script dynamically
   * @param {string} chainlitUrl - The base URL of the Chainlit server
   * @returns {Promise<void>}
   */
  function loadChainlitScript(chainlitUrl) {
    return new Promise((resolve, reject) => {
      // Check if script is already loaded
      if (window.mountChainlitWidget) {
        resolve();
        return;
      }

      const script = document.createElement("script");
      script.src = `${chainlitUrl}/copilot/index.js`;
      script.async = true;

      script.onload = () => {
        console.debug("[IndicoAssistant] Chainlit script loaded");
        resolve();
      };

      script.onerror = () => {
        console.error(
          "[IndicoAssistant] Failed to load Chainlit script from",
          chainlitUrl
        );
        reject(new Error("Failed to load Chainlit Copilot script"));
      };

      document.head.appendChild(script);
    });
  }

  /**
   * Initialize the Chainlit Copilot widget
   */
  async function initWidget() {
    try {
      setStatus("loading", "Connecting assistant...");
      injectStylesheet();
      // Early attempt to style shadow host before script load
      const host = document.getElementById("chainlit-copilot");
      if (host) {
        injectShadowStyles(host.shadowRoot);
        const inner = host.shadowRoot?.getElementById("cl-shadow-root");
        if (inner) {
          injectShadowStyles(inner);
        }
      }
      document.documentElement.setAttribute("data-assistant-ready", "loading");

      // Load the Chainlit script
      await loadChainlitScript(IndicoAssistant.chainlitUrl);

      // Determine theme
      const themePreference = IndicoAssistant.theme || "auto";
      const resolvedTheme =
        themePreference === "auto" ? detectTheme() : themePreference;
      currentTheme = resolvedTheme;
      applyTheme(resolvedTheme);

      // Build widget config
      const widgetConfig = {
        chainlitServer: IndicoAssistant.chainlitUrl,
        theme: resolvedTheme,
        authType: IndicoAssistant.authToken ? "jwt" : "header",
      };

      // Force Authorization header for all Chainlit requests when we have a token
      if (IndicoAssistant.authToken && !window.__assistantFetchPatched) {
        window.__assistantFetchPatched = true;
        const chainlitOrigin = (() => {
          try {
            return new URL(IndicoAssistant.chainlitUrl).origin;
          } catch (err) {
            return null;
          }
        })();
        const originalFetch = window.fetch.bind(window);
        window.fetch = async (input, init = {}) => {
          const url = typeof input === "string" ? input : input && input.url;
          if (chainlitOrigin && url && url.startsWith(chainlitOrigin)) {
            const headers = new Headers((init && init.headers) || (input && input.headers) || {});
            headers.set("Authorization", `Bearer ${IndicoAssistant.authToken}`);
            return originalFetch(input, { ...init, headers });
          }
          return originalFetch(input, init);
        };
      }

      if (IndicoAssistant.authToken && !window.__assistantXhrPatched) {
        window.__assistantXhrPatched = true;
        const chainlitOrigin = (() => {
          try {
            return new URL(IndicoAssistant.chainlitUrl).origin;
          } catch (err) {
            return null;
          }
        })();
        const originalOpen = XMLHttpRequest.prototype.open;
        XMLHttpRequest.prototype.open = function (method, url, ...rest) {
          this.__assistantUrl = url;
          return originalOpen.call(this, method, url, ...rest);
        };
        const originalSend = XMLHttpRequest.prototype.send;
        XMLHttpRequest.prototype.send = function (...args) {
          try {
            const url = this.__assistantUrl;
            if (chainlitOrigin && url && url.startsWith(chainlitOrigin)) {
              this.setRequestHeader("Authorization", `Bearer ${IndicoAssistant.authToken}`);
            }
          } catch (err) {
            // ignore
          }
          return originalSend.apply(this, args);
        };
      }

      // Restore thread if available (session continuity)
      const persistedThreadId = getPersistedThreadId();
      if (persistedThreadId) {
        widgetConfig.threadId = persistedThreadId;
      }

      // Add auth token if available (authenticated users)
      if (IndicoAssistant.authToken) {
        widgetConfig.accessToken = IndicoAssistant.authToken;
      }

      // Mount the widget
      if (typeof window.mountChainlitWidget === "function") {
        window.mountChainlitWidget(widgetConfig);
        startThemeWatch(widgetConfig);
        setupAccessibility();
        // Ensure styles apply inside potential shadow DOM used by Chainlit widget
        watchShadowRoots();
        // Ensure styles apply inside the Chainlit iframe document
        watchIframes();
        // Retry until shadow root exists and styles applied
        ensureShadowStyles();
        document.documentElement.setAttribute("data-assistant-ready", "true");
        setStatus("none");
      } else {
        document.documentElement.setAttribute("data-assistant-ready", "error");
        setStatus("error", "Assistant UI unavailable");
      }
    } catch (error) {
      document.documentElement.setAttribute("data-assistant-ready", "error");
      setStatus("error", "Assistant not reachable");
      // Graceful degradation - don't break the page
    }
  }

  // Initialize when DOM is ready
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initWidget);
  } else {
    initWidget();
  }

  /**
   * Watch for theme changes via media queries or DOM class toggles.
   * @param {object} widgetConfig
   */
  function startThemeWatch(widgetConfig) {
    const applyAndMaybeUpdate = (newTheme) => {
      if (newTheme && newTheme !== currentTheme) {
        currentTheme = newTheme;
        applyTheme(newTheme);
        // Attempt a soft update if Chainlit exposes a setter; otherwise rely on CSS overrides
        if (window.clUpdateTheme && typeof window.clUpdateTheme === "function") {
          window.clUpdateTheme(newTheme);
        }
        widgetConfig.theme = newTheme;
      }
    };

    const prefersAuto = !IndicoAssistant.theme || IndicoAssistant.theme === "auto";

    if (window.matchMedia) {
      const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
      const mediaHandler = (event) => {
        if (prefersAuto) {
          applyAndMaybeUpdate(event.matches ? "dark" : "light");
        }
      };

      if (mediaQuery.addEventListener) {
        mediaQuery.addEventListener("change", mediaHandler);
      } else if (mediaQuery.addListener) {
        mediaQuery.addListener(mediaHandler);
      }
    }

    if (window.MutationObserver) {
      const observer = new MutationObserver(() => {
        if (prefersAuto) {
          applyAndMaybeUpdate(detectTheme());
        }
      });

      observer.observe(document.documentElement, {
        attributes: true,
        attributeFilter: ["class", "data-theme"],
      });
      observer.observe(document.body, {
        attributes: true,
        attributeFilter: ["class", "data-theme"],
      });
    }
  }
})();
