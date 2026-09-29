// Spec 020 US4 on the local stack, through Chainlit's own sidebar menu: rename a conversation (kept after a
// reload), delete the open one (the panel shows a new chat), and a stale conversation id restores nothing,
// without an error.
//   node us4.mjs
import { browserAs, INDICO } from "./lib.mjs";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const results = [];
const check = (name, ok, detail = "") => { results.push(ok); console.log(`${ok ? "ok  " : "FAIL"} ${name} ${detail}`); };
const QUESTION = `US4 check ${Date.now()}`;
const RENAMED = `Renamed ${Date.now()}`;
const USER = Number(process.env.WALK_USER || 1);
const { browser, page } = await browserAs(USER, { headless: !process.argv.includes("--headful") });
const chat = () => page.frames().find((f) => f.url().startsWith("http://127.0.0.1:8001") && !f.url().includes("login"));
async function until(pred, ms = 10000) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) { if (await pred().catch(() => false)) return true; await sleep(100); }
  return false;
}
const ready = () => until(() => page.evaluate(() => document.documentElement.dataset.assistantPanel === "ready"), 20000);
const inFrame = (fn, ...args) => chat().evaluate(fn, ...args);
async function openSidebar() {  // (links stay in the DOM while the drawer is closed: check they are shown)
  if (!(await inFrame(() => [...document.querySelectorAll("a[href^='/thread/']")].some((a) => a.offsetParent)))) {
    await inFrame(() => document.getElementById("sidebar-trigger-button").click());
    await until(() => inFrame(() => [...document.querySelectorAll("a[href^='/thread/']")].some((a) => a.offsetParent)));
  }
}
const listed = (text) => inFrame((text) => [...document.querySelectorAll("a[href^='/thread/']")].some((a) => a.textContent.includes(text)), text);
async function menu(title, item) {  // the thread's "…" menu (Radix opens it on pointerdown)
  await inFrame((title) => {
    const row = [...document.querySelectorAll("li[data-sidebar=menu-item]")].find((li) => li.textContent.includes(title));
    const options = row.querySelector("#thread-options");
    options.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true, button: 0, pointerType: "mouse" }));
  }, title);
  await until(() => inFrame(() => !!document.querySelector("[role=menu]")), 3000);
  await inFrame((item) => [...document.querySelectorAll("[role=menuitem]")].find((m) => m.innerText.trim() === item).click(), item);
}
const lastDialogButton = (label) => inFrame((label) => {  // (the delete confirmation is an alertdialog)
  const buttons = [...([...document.querySelectorAll("[role=dialog], [role=alertdialog]")].pop()?.querySelectorAll("button") || [])];
  const button = buttons.find((b) => b.innerText.trim().toLowerCase() === label.toLowerCase());
  if (button) button.click();
  return !!button;
}, label);

try {
  await page.goto(`${INDICO}/event/351/`, { waitUntil: "load" });
  await page.click("#assistant-toggle");
  await ready();
  const input = await chat().waitForSelector("#chat-input");
  await sleep(1500);
  await input.click();
  await input.type(QUESTION);
  await input.press("Enter");
  await until(() => inFrame(() => [...document.querySelectorAll("[data-step-type='assistant_message']")]
    .some((s) => s.innerText.trim().length > 0)), 120000);

  // rename (US4 AS-1)
  await openSidebar();
  const t0 = Date.now();
  const appeared = await until(() => listed(QUESTION), 30000);
  check("a new conversation is in Past Chats", appeared, `${Date.now() - t0} ms after its answer`);
  if (!appeared) {
    console.log("sidebar lists:", await inFrame(() => [...document.querySelectorAll("a[href^='/thread/']")].slice(0, 5).map((a) => a.innerText)),
                "url:", chat().url());
  }
  await menu(QUESTION, "Rename");
  const field = await chat().waitForFunction(() => [...document.querySelectorAll("[role=dialog]")].pop()?.querySelector("input"),
                                             { timeout: 5000 });
  await field.evaluate((e) => e.select());
  await field.type(RENAMED);
  await lastDialogButton("Confirm");
  await sleep(1000);
  await page.reload({ waitUntil: "load" });
  await ready();
  await openSidebar();
  check("US4 AS-1 a rename is kept after a reload", await until(() => listed(RENAMED), 8000));

  // delete the open conversation (US4 AS-2, AS-3)
  await menu(RENAMED, "Delete");
  await until(() => inFrame(() => !!document.querySelector("[role=alertdialog]")), 5000);
  const confirmed = await lastDialogButton("Confirm") || await lastDialogButton("Delete");
  const gone = await until(async () => !(await listed(RENAMED)), 8000);
  const fresh = await until(() => inFrame(() => location.pathname === "/" && !document.body.innerText.includes("US4 check")), 8000);
  check("US4 AS-2/AS-3 deleting the open conversation leaves a new chat", confirmed && gone && fresh,
        `confirmed=${confirmed} gone=${gone} fresh=${fresh} url=${chat().url()}`);
  await page.reload({ waitUntil: "load" });
  await ready();
  check("and it is not restored", await until(() => inFrame(() => location.pathname === "/"), 8000));

  // a stale id (deleted elsewhere, retention): a new chat, no error
  await page.evaluate(() => {
    const key = Object.keys(localStorage).find((k) => k.startsWith("indico-assistant:"));
    const state = JSON.parse(localStorage.getItem(key));
    localStorage.setItem(key, JSON.stringify({ ...state, threadId: "3f2c0a7e-2b7e-4f0e-9a51-6f0a1c2d3e4f" }));
  });
  await page.reload({ waitUntil: "load" });
  await ready();
  await sleep(2000);
  const text = await inFrame(() => document.body.innerText);
  check("a stale conversation id opens a new chat without an error",
        (await inFrame(() => location.pathname)) === "/" && !/couldn.t resume|error|not found/i.test(text),
        JSON.stringify(text.slice(0, 120)));
} finally {
  await page.screenshot({ path: new URL("./us4-last.png", import.meta.url).pathname });
  await browser.close();
}
console.log(`${results.filter(Boolean).length}/${results.length} checks passed`);
process.exit(results.every(Boolean) ? 0 : 1);
