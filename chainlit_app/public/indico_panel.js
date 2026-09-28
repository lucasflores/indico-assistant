// The frame side of the Indico panel (spec 020 R6, contracts/panel.md), loaded as Chainlit's custom_js.
// It tells the Indico page when the chat is drawn, which conversation is open, which Indico links were
// clicked (so they open in the page, not in the panel), and when Esc was pressed. It does nothing when the
// app is opened on its own, outside Indico's panel.
(function () {
  "use strict";
  var parent = null;
  try { parent = sessionStorage.getItem("indico-assistant-parent"); } catch (e) {}
  if (!parent || window.parent === window) return;

  function post(message) {
    message.source = "indico-assistant";
    window.parent.postMessage(message, parent);
  }

  // Focus stays on the Indico page until the user turns to the panel (FR-003): the chat focuses its input on
  // load, which would pull the page's focus into the frame on every navigation.
  var engaged = false;
  ["pointerdown", "keydown"].forEach(function (name) {
    document.addEventListener(name, function () { engaged = true; }, true);
  });
  var nativeFocus = HTMLElement.prototype.focus;
  HTMLElement.prototype.focus = function () {
    if (engaged) return nativeFocus.apply(this, arguments);
  };

  // which conversation is open: /thread/<id>, or "/" for a new chat, reported when the path changes. A new
  // chat stays on "/": its id comes from the server once Indico has it (a window_message). (ponytail: "New
  // chat" then leaving before typing restores the previous conversation; nothing was made in the new one.)
  var lastPath;
  function reportThread() {
    if (location.pathname === lastPath) return;
    lastPath = location.pathname;
    var match = location.pathname.match(/^\/thread\/([0-9a-f-]{36})/i);
    if (match) post({ type: "thread", threadId: match[1] });
    else if (location.pathname === "/") post({ type: "thread", threadId: null });
  }
  ["pushState", "replaceState"].forEach(function (name) {
    var original = history[name];
    history[name] = function () {
      var result = original.apply(this, arguments);
      reportThread();
      return result;
    };
  });
  window.addEventListener("popstate", reportThread);

  // the chat is drawn once its input exists
  var readyTimer = setInterval(function () {
    if (document.getElementById("chat-input")) {
      clearInterval(readyTimer);
      reportThread();
      post({ type: "ready" });
    }
  }, 100);

  // links to Indico open in the page (FR-006b). Answers link to Indico with relative paths ("/event/351"),
  // which inside this frame would resolve to Chainlit: a relative link in a message is an Indico path. (The
  // sidebar's own links, /thread/<id>, are not in messages and stay Chainlit's.)
  document.addEventListener("click", function (event) {
    var link = event.target && event.target.closest && event.target.closest("a[href]");
    if (!link) return;
    var raw = link.getAttribute("href") || "";
    var inMessage = !!link.closest("[data-step-type]");
    var url;
    try { url = new URL(raw, inMessage && raw.charAt(0) === "/" && raw.charAt(1) !== "/" ? parent : location.href); }
    catch (e) { return; }
    if (url.origin !== parent) return;
    event.preventDefault();
    event.stopPropagation();
    post({ type: "navigate", url: url.href });
  }, true);

  // Deleting the conversation that is open leaves Chainlit showing it (US4 AS-3): once the delete has
  // succeeded, start a new chat instead.
  var nativeFetch = window.fetch.bind(window);
  window.fetch = function (input, init) {
    var result = nativeFetch(input, init);
    try {
      var url = typeof input === "string" ? input : input && input.url;
      if (init && init.method === "DELETE" && /\/project\/thread$/.test(url || "") && init.body) {
        var deleted = JSON.parse(init.body).threadId;
        result.then(function (response) {
          if (response.ok && location.pathname === "/thread/" + deleted) location.replace("/");
        });
      }
    } catch (e) { /* not ours to judge */ }
    return result;
  };

  // In the narrow panel the Past Chats toggle can be swallowed after a new conversation's first question
  // (Chainlit's drawer state goes stale: seen live, the first click did nothing, the second worked). After a
  // click, if the drawer did not open (or close), toggle once more with Chainlit's own shortcut (Ctrl+B).
  function drawerOpen() { return !!document.querySelector("[role=dialog] a[href^='/thread/'], [role=dialog] #new-chat-button"); }
  document.addEventListener("click", function (event) {
    if (!(event.target && event.target.closest && event.target.closest("#sidebar-trigger-button"))) return;
    var wasOpen = drawerOpen();
    setTimeout(function () {
      if (drawerOpen() === wasOpen) window.dispatchEvent(new KeyboardEvent("keydown", { key: "b", ctrlKey: true, bubbles: true }));
    }, 300);
  }, true);

  // Esc closes the panel (FR-006d), unless a Chainlit dialog or menu is open and takes it
  document.addEventListener("keydown", function (event) {
    if (event.key !== "Escape" || event.defaultPrevented) return;
    if (document.querySelector("[role=dialog], [role=menu], [data-state=open][role=listbox]")) return;
    post({ type: "close" });
  });
})();
