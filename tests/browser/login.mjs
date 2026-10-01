// Each Indico login starts the panel on a new chat (Lucas, 2026-10-01). A login gives the session a new id, and the
// script tag's data-login changes with it; a conversation kept from the earlier login is not reopened. Within one
// login, page views keep the open conversation. No question is asked: it reuses one of the user's conversations.
//   WALK_USER=6 node login.mjs
import { execFileSync } from "node:child_process";
import { browserAs, INDICO, mintSession } from "./lib.mjs";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const results = [];
const check = (name, ok, detail = "") => { results.push(ok); console.log(`${ok ? "ok  " : "FAIL"} ${name} ${detail}`); };
const USER = Number(process.env.WALK_USER || 6);
const THREAD = execFileSync("psql", ["-d", "indico", "-Atc",
  `select id from plugin_assistant.chat_sessions where user_id = ${USER} order by updated_at desc limit 1`]).toString().trim();
if (!THREAD) throw new Error(`user ${USER} has no conversation to reopen`);
const { browser, page } = await browserAs(USER, { headless: !process.argv.includes("--headful") });
const chat = () => page.frames().find((f) => f.url().startsWith("http://127.0.0.1:8001") && !f.url().includes("login"));
async function until(pred, ms = 10000) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) { if (await pred().catch(() => false)) return true; await sleep(100); }
  return false;
}
const ready = () => until(() => page.evaluate(() => document.documentElement.dataset.assistantPanel === "ready"), 20000);
const login = () => page.evaluate(() => document.querySelector("script[data-user]")?.dataset.login || "");
async function keep(threadId) {  // what the panel stores once a conversation is open in this login
  await page.evaluate((key, threadId) => {
    const state = JSON.parse(localStorage.getItem(key) || "{}");
    localStorage.setItem(key, JSON.stringify({ ...state, open: true, threadId }));
    sessionStorage.setItem(key.replace("assistant:", "assistant-thread:"), threadId);
  }, `indico-assistant:${USER}`, threadId);
}
const shows = (path) => until(() => chat().evaluate(() => location.pathname).then((p) => p === path), 15000);

try {
  await page.goto(`${INDICO}/event/351/`, { waitUntil: "load" });
  const first = await login();
  await keep(THREAD);
  await page.reload({ waitUntil: "load" });
  await ready();
  check("within a login, a page view reopens the conversation", await shows(`/thread/${THREAD}`));

  await page.setCookie({ name: "indico_session_http", value: mintSession(USER), domain: new URL(INDICO).hostname, path: "/" });
  await page.reload({ waitUntil: "load" });
  const second = await login();
  await ready();
  check("a new login has a new marker", first && second && first !== second);
  check("and starts on a new chat", await shows("/"));

  await keep(THREAD);
  await page.reload({ waitUntil: "load" });
  await ready();
  check("a conversation opened in the new login is kept", await shows(`/thread/${THREAD}`));
} finally {
  await page.screenshot({ path: new URL("./login-last.png", import.meta.url).pathname });
  await browser.close();
}
console.log(`${results.filter(Boolean).length}/${results.length} checks passed`);
process.exit(results.every(Boolean) ? 0 : 1);
