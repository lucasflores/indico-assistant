// Spec 020, review of PR #5: two tabs keep their own conversation. Tab A has one, tab B starts another; a
// page load in tab A still shows A's (the open conversation is per tab), and a brand-new tab starts on the last.
//   WALK_USER=6 node tabs.mjs
import { browserAs, INDICO } from "./lib.mjs";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const results = [];
const check = (name, ok, detail = "") => { results.push(ok); console.log(`${ok ? "ok  " : "FAIL"} ${name} ${detail}`); };
const USER = Number(process.env.WALK_USER || 1);
const { browser, page: a } = await browserAs(USER, { headless: !process.argv.includes("--headful") });
const chat = (p) => p.frames().find((f) => f.url().startsWith("http://127.0.0.1:8001") && !f.url().includes("login"));
async function until(pred, ms = 10000) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) { if (await pred().catch(() => false)) return true; await sleep(100); }
  return false;
}
const ready = (p) => until(() => p.evaluate(() => document.documentElement.dataset.assistantPanel === "ready"), 20000);
const says = (p, text) => chat(p).evaluate((text) => document.body.innerText.includes(text), text);
async function ask(p, text) {
  const input = await chat(p).waitForSelector("#chat-input");
  await sleep(1500);
  await input.click();
  await input.type(text);
  await input.press("Enter");
  await until(() => chat(p).evaluate(() => [...document.querySelectorAll("[data-step-type='assistant_message']")]
    .some((s) => s.innerText.trim().length > 0)), 120000);
  await sleep(1500);  // (the thread id reaches the page)
}
const A_TEXT = `Tabs check A ${Date.now()}`, B_TEXT = `Tabs check B ${Date.now()}`;

try {
  await a.goto(`${INDICO}/event/351/`, { waitUntil: "load" });
  if (await a.$("#assistant-launcher:not([hidden])")) await a.click("#assistant-launcher");
  await ready(a);
  await ask(a, A_TEXT);

  const b = await browser.newPage();
  await b.setViewport({ width: 1400, height: 900 });
  await b.goto(`${INDICO}/event/351/`, { waitUntil: "load" });
  await ready(b);
  check("a new tab starts on the last conversation", await until(() => says(b, A_TEXT), 8000));
  await chat(b).evaluate(() => document.getElementById("new-chat-button").click());
  await sleep(300);
  await chat(b).evaluate(() => {  // Chainlit asks before a new chat: confirm in the last dialog
    const confirm = [...([...document.querySelectorAll("[role=dialog]")].pop()?.querySelectorAll("button") || [])]
      .find((x) => /confirm/i.test(x.innerText));
    if (confirm) confirm.click();
  });
  await until(() => chat(b).evaluate(() => location.pathname === "/"), 5000);
  await ask(b, B_TEXT);

  await a.reload({ waitUntil: "load" });
  await ready(a);
  const own = await until(() => says(a, A_TEXT), 8000);
  check("tab A keeps its conversation after tab B started another", own && !(await says(a, B_TEXT)));
  await b.reload({ waitUntil: "load" });
  await ready(b);
  check("and tab B keeps its own", await until(() => says(b, B_TEXT), 8000) && !(await says(b, A_TEXT)));
} finally {
  await a.screenshot({ path: new URL("./tabs-last.png", import.meta.url).pathname });
  await browser.close();
}
console.log(`${results.filter(Boolean).length}/${results.length} checks passed`);
process.exit(results.every(Boolean) ? 0 : 1);
