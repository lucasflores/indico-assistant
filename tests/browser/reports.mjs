// Spec 021 on the local stack: issue reports from the chat panel.
//   SC-001: a report from an offer and one from the title bar's ⚑, each in at most three choices besides typing,
//           each listed on the profile page right after (RUNS times).
//   SC-002: an offer after each thumbs down and under each out-of-scope answer (RUNS each); a double-clicked Send
//           makes one report; no report exists that the run did not send.
// Run as a non-admin: WALK_USER=6 RUNS=10 node reports.mjs [--headful]. At the end it counts, then deletes, the
// reports it made. It resets the user's report and chat limits in the dev Redis (counted first): 10 runs send more
// than the 20 reports a day one user may.
import { execFileSync } from "node:child_process";
import { browserAs, INDICO } from "./lib.mjs";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const results = [];
const check = (name, ok, detail = "") => { results.push(ok); console.log(`${ok ? "ok  " : "FAIL"} ${name} ${detail}`); };
const USER = Number(process.env.WALK_USER || 6);
const RUNS = Number(process.env.RUNS || 10);
const CHAINLIT = process.env.CHAINLIT_URL || "http://127.0.0.1:8001";
const { browser, page } = await browserAs(USER, { headless: !process.argv.includes("--headful") });
const chat = () => page.frames().find((f) => f.url().startsWith(CHAINLIT) && !f.url().includes("login"));
async function until(pred, ms = 10000) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) { if (await pred().catch(() => false)) return true; await sleep(150); }
  return false;
}

function resetLimits() {  // this user's counters only; the dev Redis cache is db 1 (indico.conf REDIS_CACHE_URL)
  const keys = execFileSync("redis-cli", ["-n", "1", "--scan", "--pattern", "LIMITS:LIMITER/assistant-*"]).toString().split("\n")
    .filter((k) => new RegExp(`assistant-(report|chat)-\\d+/${USER}/`).test(k));  // (…-chat-1/<user>/200/1/day)
  console.log(`     (resetting ${keys.length} limit counters of user ${USER})`);
  for (const key of keys) execFileSync("redis-cli", ["-n", "1", "del", key]);
}

const api = (path, init = {}) => page.evaluate(async (path, init) => {
  const csrf = document.getElementById("csrf-token")?.content;
  const response = await fetch(path, { ...init, headers: { ...(init.headers || {}), "X-CSRF-Token": csrf } });
  return { status: response.status, body: response.status === 204 ? null : await response.json().catch(() => null) };
}, path, init);
const myReportIds = async () => ((await api("/api/assistant/reports")).body?.reports || []).map((r) => r.report_id);
const onProfile = (id) => page.evaluate(async (id) =>
  (await (await fetch("/user/assistant-reports/")).text()).includes(`#${id} `), id);

const inFrame = (fn, ...args) => chat().evaluate(fn, ...args);
const answers = () => inFrame(() => document.querySelectorAll('[data-step-type="assistant_message"]').length);
const offers = () => inFrame(() => [...document.querySelectorAll("button")]
  .filter((b) => b.textContent.trim() === "Report a problem").length);
const sorry = () => inFrame(() => (document.body.innerText.match(/Tell the team about it\?/g) || []).length);
const forms = () => inFrame(() => document.querySelectorAll("[data-issue-report]").length);
const sentNotes = () => inFrame(() => document.querySelectorAll("[data-issue=sent]").length);

async function ask(text) {
  const before = await answers();
  const input = await chat().waitForSelector("#chat-input");
  await input.click();
  await input.type(text);
  await input.press("Enter");
  return until(async () => (await answers()) > before && !(await inFrame(() => !!document.querySelector(".animate-pulse, [data-loading=true]"))), 120000);
}

// the last form: fill it (a category only when asked), then Send (clicked `clicks` times at once)
async function sendLastForm(text, kind = null, clicks = 1) {
  const sentBefore = await sentNotes();
  await inFrame((text, kind) => {
    const form = [...document.querySelectorAll("[data-issue-report]")].pop();
    if (kind) form.querySelector(`[data-issue="kind-${kind}"]`).click();
    const area = form.querySelector("[data-issue=text]");
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value").set.call(area, text);
    area.dispatchEvent(new Event("input", { bubbles: true }));  // (React reads the typed value from the event)
  }, text, kind);
  await sleep(200);
  await inFrame((clicks) => {
    const send = [...document.querySelectorAll("[data-issue-report]")].pop().querySelector("[data-issue=send]");
    for (let i = 0; i < clicks; i++) send.click();  // a double click: two clicks before React disables it
  }, clicks);
  if (!(await until(async () => (await sentNotes()) > sentBefore, 15000))) return null;
  const text_ = await inFrame(() => [...document.querySelectorAll("[data-issue=sent]")].pop().innerText);
  return Number((text_.match(/#(\d+)/) || [])[1]) || null;
}

async function thumbsDownLastAnswer(comment) {
  await inFrame(() => [...document.querySelectorAll(".negative-feedback-off")].pop().click());
  const field = await chat().waitForFunction(() => [...document.querySelectorAll("[role=dialog]")].pop()?.querySelector("textarea"),
                                             { timeout: 5000 });
  await field.type(comment);
  await inFrame(() => document.getElementById("submit-feedback").click());
}

let before = null;  // the user's reports before the run: read once a page is loaded (fetch needs its origin)
const sent = [];
try {
  await page.goto(`${INDICO}/event/351/`, { waitUntil: "load" });
  before = new Set(await myReportIds());
  if (await page.$("#assistant-toggle[aria-expanded=false]")) await page.click("#assistant-toggle");
  check("the panel is ready and ⚑ is enabled",
        await until(async () => (await page.evaluate(() => document.documentElement.dataset.assistantPanel)) === "ready"
                    && !(await page.$eval("#assistant-panel-report", (b) => b.disabled)), 30000));
  await sleep(2500);  // (the Copilot-era gotcha: the socket needs a moment before Enter sends)

  let offered = 0, afterThumbs = 0, fromOffer = 0, fromButton = 0;
  for (let run = 1; run <= RUNS; run++) {
    resetLimits();
    // SC-002: an out-of-scope question carries an offer
    const offersBefore = await offers();
    await ask(`What will the weather be on Mars tomorrow? (report check ${Date.now()})`);
    if (await until(async () => (await offers()) > offersBefore, 5000)) offered++;
    // SC-001: a report from that offer: the offer (1), Send (2); the category is already chosen
    const formsBefore = await forms();
    await inFrame(() => [...document.querySelectorAll("button")].filter((b) => b.textContent.trim() === "Report a problem").pop().click());
    if (await until(async () => (await forms()) > formsBefore)) {
      const id = await sendLastForm(`Run ${run}: it should have known this.`);
      if (id && await onProfile(id)) { fromOffer++; sent.push(id); }
    }
    // SC-002: a thumbs down offers a report once
    const sorryBefore = await sorry();
    await thumbsDownLastAnswer(`run ${run}: not what I asked`);
    if (await until(async () => (await sorry()) > sorryBefore, 10000)) afterThumbs++;
    // SC-001: a report from ⚑: the button (1), a category (2), Send (3)
    const formsBefore2 = await forms();
    await page.click("#assistant-panel-report");
    if (await until(async () => (await forms()) > formsBefore2)) {
      const id = await sendLastForm(`Run ${run}: an idea from the title bar.`, "feature");
      if (id && await onProfile(id)) { fromButton++; sent.push(id); }
    }
  }
  check(`SC-001 a report from an offer, listed on the profile page`, fromOffer === RUNS, `${fromOffer}/${RUNS}`);
  check(`SC-001 a report from ⚑, listed on the profile page`, fromButton === RUNS, `${fromButton}/${RUNS}`);
  check(`SC-002 an offer under an out-of-scope answer`, offered === RUNS, `${offered}/${RUNS}`);
  check(`SC-002 an offer after a thumbs down`, afterThumbs === RUNS, `${afterThumbs}/${RUNS}`);

  // SC-002: a double-clicked Send makes one report
  resetLimits();
  const idsBefore = new Set(await myReportIds());
  const formsBefore = await forms();
  await page.click("#assistant-panel-report");
  await until(async () => (await forms()) > formsBefore);
  const id = await sendLastForm("Double click check.", "bug", 2);
  if (id) sent.push(id);
  await sleep(1500);  // (a second request, had one been made, lands by now)
  const made = (await myReportIds()).filter((r) => !idsBefore.has(r));
  check("SC-002 a double-clicked Send makes one report", made.length === 1, JSON.stringify(made));

  const unexpected = (await myReportIds()).filter((r) => !before.has(r) && !sent.includes(r));
  check("SC-002 no report exists that the run did not send", unexpected.length === 0, JSON.stringify(unexpected));
} finally {
  await page.screenshot({ path: new URL("./reports-last.png", import.meta.url).pathname });
  // only what this run made; nothing at all if the reports before it could not be read
  const mine = before ? (await myReportIds().catch(() => [])).filter((r) => !before.has(r)) : [];
  console.log(`     (deleting the ${mine.length} reports this run made)`);
  for (const id of mine) await api(`/api/assistant/reports/${id}`, { method: "DELETE" });
  await browser.close();
}
console.log(`${results.filter(Boolean).length}/${results.length} checks passed`);
process.exit(results.every(Boolean) ? 0 : 1);
