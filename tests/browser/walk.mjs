// Spec 020 panel walk against the local stack: the conversation survives navigation (SC-001, SC-002),
// an answer asked for just before leaving arrives (SC-004), focus stays on the page (FR-003), the page does
// not shift (FR-006a), answer links open in the page (FR-006b), Esc and the width (FR-006d), a closed panel
// stays closed (US1 AS-2).
//   node walk.mjs [--headful]
import { browserAs, INDICO } from "./lib.mjs";

const START = process.env.WALK_START || `${INDICO}/event/351/`;
const PAGES = Number(process.env.WALK_PAGES || 10);
const QUESTION = "Who are the speakers of this event?";
const results = [];
const check = (name, ok, detail = "") => { results.push({ name, ok, detail }); console.log(`${ok ? "ok  " : "FAIL"} ${name} ${detail}`); };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const { browser, page } = await browserAs(1, { headless: !process.argv.includes("--headful") });

async function state() {
  return page.evaluate(() => document.documentElement.dataset.assistantPanel || "none");
}
async function waitState(wanted, ms = 15000) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) { if ((await state()) === wanted) return true; await sleep(100); }
  return false;
}
function chatFrame() {
  return page.frames().find((f) => f.url().startsWith("http://127.0.0.1:8001") && !f.url().includes("indico-login"));
}
async function frameText() {
  const frame = chatFrame();
  return frame ? frame.evaluate(() => document.body.innerText) : "";
}
async function waitFrameText(pred, ms = 120000) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) { if (pred(await frameText().catch(() => ""))) return true; await sleep(500); }
  return false;
}
// whether the question has an answer after it (Chainlit marks messages with data-step-type)
async function answered(question) {
  const frame = chatFrame();
  if (!frame) return false;
  return frame.evaluate((question) => {
    const steps = [...document.querySelectorAll("[data-step-type]")];
    const asked = steps.findIndex((s) => s.dataset.stepType === "user_message" && s.innerText.includes(question));
    return asked >= 0 && steps.slice(asked + 1).some((s) => s.dataset.stepType === "assistant_message" &&
                                                         s.innerText.trim().length > 0);
  }, question).catch(() => false);
}
async function waitAnswer(question, ms = 150000) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) { if (await answered(question)) return true; await sleep(500); }
  return false;
}
async function ask(text) {
  const frame = chatFrame();
  const input = await frame.waitForSelector("#chat-input", { timeout: 20000 });
  await sleep(1500);  // the websocket connects after the input renders
  await input.click();
  await input.type(text);
  await input.press("Enter");
}
async function timings() {
  return page.evaluate(() => {
    const nav = performance.getEntriesByType("navigation")[0];
    return { load: nav.loadEventEnd, ready: window.__assistantReadyAt ?? null,
             initialMargin: window.__assistantInitialMargin ?? null,
             margin: getComputedStyle(document.documentElement).marginRight,
             focusInPanel: !!document.activeElement?.closest?.("#assistant-panel") };
  });
}
const pathOf = (url) => new URL(url).pathname.replace(/\/?$/, "/");
async function followALink(visited) {
  const href = await page.evaluate((visited) => {
    const path = (u) => new URL(u).pathname.replace(/\/?$/, "/");
    const links = [...document.querySelectorAll("a[href]")].map((a) => a.href)
      .filter((h) => h.startsWith(location.origin) &&
              /^\/((event\/\d+\/((timetable|contributions)\/)?)|(category\/\d+\/))?$/.test(path(h)))
      .filter((h) => path(h) !== path(location.href));
    return links.find((h) => !visited.includes(path(h))) || links[0] || null;  // new pages first
  }, visited);
  if (!href) return null;
  visited.push(pathOf(href));
  await Promise.all([page.waitForNavigation({ waitUntil: "load" }), page.evaluate((h) => {
    [...document.querySelectorAll("a[href]")].find((a) => a.href === h).click();
  }, href)]);
  return href;
}

try {
  // open the panel and ask something
  await page.goto(START, { waitUntil: "load" });
  await page.click("#assistant-launcher");
  check("panel opens", await waitState("ready"));
  await ask(QUESTION);
  check("first answer", await waitAnswer(QUESTION));
  const LINKED = "Which upcoming events are in the category Nothing Science? Link each one.";
  await ask(LINKED);  // (answers that list events cite them with links: FR-006b below)
  const second = await waitAnswer(LINKED);
  check("second answer", second, second ? "" : JSON.stringify((await frameText()).slice(-400)));

  // SC-001 / SC-002 / FR-003 / FR-006a over a walk of linked pages
  const visited = [pathOf(page.url())];
  const delays = [];
  for (let n = 0; n < PAGES; n++) {
    const href = await followALink(visited);
    if (!href) { check(`page ${n + 1}: a link to follow`, false, "no unvisited event/category link"); break; }
    const ready = await waitState("ready");
    const t = await timings();
    const shown = await waitFrameText((x) => x.includes(QUESTION), 10000);
    if (t.ready !== null) delays.push(t.ready - t.load);
    check(`page ${n + 1} ${new URL(href).pathname}`, ready && shown && !t.focusInPanel && t.initialMargin === t.margin,
          `ready=${ready} conversation=${shown} focusInPanel=${t.focusInPanel} margin ${t.initialMargin}→${t.margin}`);
  }
  delays.sort((a, b) => a - b);
  const median = delays.length ? delays[Math.floor(delays.length / 2)] : Infinity;
  check("SC-002 median load→ready under 2 s", median < 2000, `${Math.round(median)} ms over ${delays.length} pages`);

  // FR-006b: a link in an answer opens in the page
  // answers link to Indico with relative paths ("/event/351"): they must open in the Indico page
  const raw = await chatFrame().evaluate(() => {
    const a = [...document.querySelectorAll("[data-step-type] a[href]")].find((x) => /\/event\/\d+/.test(x.getAttribute("href")));
    return a ? a.getAttribute("href") : null;
  });
  if (raw) {
    const link = new URL(raw, INDICO).href;
    await Promise.all([page.waitForNavigation({ waitUntil: "load" }), chatFrame().evaluate((raw) => {
      [...document.querySelectorAll("[data-step-type] a[href]")].find((x) => x.getAttribute("href") === raw).click();
    }, raw)]);
    check("FR-006b answer link opens in the page", pathOf(page.url()) === pathOf(link) && (await waitState("ready")),
          `${raw} → ${page.url()}`);
  } else {
    check("FR-006b answer link opens in the page", false, "no Indico link in the answers");
  }

  // FR-005: a plan waiting for confirmation comes back after navigating, with working buttons (Cancel here:
  // it writes nothing; the fresh token behind Confirm is covered by test_plan_token.py)
  const PLAN = "Create a meeting called Walk check tomorrow at 9am in Nothing Science";
  await ask(PLAN);
  const buttons = () => chatFrame().evaluate(() => [...document.querySelectorAll("button")].map((b) => b.innerText.trim()));
  let planShown = await waitAnswer(PLAN);
  await followALink(visited);
  await waitState("ready");
  let restored = false;
  for (let i = 0; i < 40 && !restored; i++) { restored = (await buttons()).includes("Confirm"); if (!restored) await sleep(250); }
  if (restored) {
    await chatFrame().evaluate(() => [...document.querySelectorAll("button")].find((b) => b.innerText.trim() === "Cancel").click());
  }
  check("FR-005 a waiting plan comes back with working buttons",
        planShown && restored && (await waitFrameText((x) => /Cancelled; nothing was changed/.test(x), 15000)));

  // SC-004: ask, leave at once, the answer arrives on the next page
  const SLOW = "List every contribution of this event with its speakers and duration";
  await ask(SLOW);
  await sleep(300);
  await followALink(visited);
  await waitState("ready");
  check("SC-004 an answer asked for before leaving arrives", await waitAnswer(SLOW));

  // FR-006d: width survives a reload; Esc closes; closed stays closed (US1 AS-2)
  const handle = await page.$("#assistant-panel-handle");
  const box = await handle.boundingBox();
  await page.mouse.move(box.x + box.width / 2, box.y + 40);
  await page.mouse.down();
  await page.mouse.move(box.x - 120, box.y + 40, { steps: 8 });
  await page.mouse.up();
  const width = await page.$eval("#assistant-panel", (e) => e.getBoundingClientRect().width);
  await page.reload({ waitUntil: "load" });
  await waitState("ready");
  const widthAfter = await page.$eval("#assistant-panel", (e) => e.getBoundingClientRect().width);
  check("FR-006d width is remembered", Math.abs(width - widthAfter) < 2, `${width} → ${widthAfter}`);

  const input = await chatFrame().waitForSelector("#chat-input");
  await input.click();
  await page.keyboard.press("Escape");
  check("FR-006d Esc closes", await waitState("closed", 3000));
  await page.goto(START, { waitUntil: "load" });
  await sleep(1000);
  check("US1 AS-2 a closed panel stays closed", (await state()) === "closed" &&
        (await page.evaluate(() => getComputedStyle(document.documentElement).marginRight)) === "0px");
  await page.click("#assistant-launcher");
  await waitState("ready");
  check("reopened on the same conversation", await waitFrameText((x) => x.includes(QUESTION), 10000));
} finally {
  await page.screenshot({ path: new URL("./walk-last.png", import.meta.url).pathname });
  await browser.close();
}
const failed = results.filter((r) => !r.ok);
console.log(`${results.length - failed.length}/${results.length} checks passed`);
process.exit(failed.length ? 1 : 0);
