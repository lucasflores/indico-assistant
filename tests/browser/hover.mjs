// Spec 020 panel look: hovering the sidebar's buttons and a conversation shows a small tooltip, not a page-sized box.
//   WALK_USER=6 node hover.mjs
import { browserAs, INDICO } from "./lib.mjs";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const results = [];
const check = (name, ok, detail = "") => { results.push(ok); console.log(`${ok ? "ok  " : "FAIL"} ${name} ${detail}`); };
const { browser, page } = await browserAs(Number(process.env.WALK_USER || 1), { headless: !process.argv.includes("--headful") });
const chat = () => page.frames().find((f) => f.url().startsWith("http://127.0.0.1:8001") && !f.url().includes("login"));
async function until(pred, ms = 10000) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) { if (await pred().catch(() => false)) return true; await sleep(100); }
  return false;
}
// the size of what hovering `selector` pops up (Radix puts tooltips in a popper wrapper)
async function hover(selector, again = true) {
  // (real mouse moves miss elements in the panel's sidebar drawer: dispatch what Radix listens for)
  await chat().waitForSelector(selector, { visible: true, timeout: 5000 });
  await chat().evaluate((selector) => {
    const e = [...document.querySelectorAll(selector)].find((e) => e.offsetParent);  // (a closed drawer keeps copies)
    for (const type of ["pointerover", "pointerenter", "pointermove"]) {
      e.dispatchEvent(new PointerEvent(type, { bubbles: type !== "pointerenter", pointerType: "mouse" }));
    }
  }, selector);
  await until(() => chat().evaluate(() => !!document.querySelector("[data-radix-popper-content-wrapper]")), 3000);
  await sleep(300);
  const box = await chat().evaluate(() => {
    const e = document.querySelector("[data-radix-popper-content-wrapper]");
    if (!e) return null;  // (Radix can skip a hover that follows another tooltip closing: tried once more)
    const r = e.getBoundingClientRect();
    return { w: Math.round(r.width), h: Math.round(r.height), text: e.innerText.trim().slice(0, 40) };
  });
  await chat().evaluate((selector) => {
    [...document.querySelectorAll(selector)].find((e) => e.offsetParent).dispatchEvent(new PointerEvent("pointerleave", { pointerType: "mouse" }));
  }, selector);
  await until(() => chat().evaluate(() => !document.querySelector("[data-radix-popper-content-wrapper]")), 3000);
  return box || !again ? box : hover(selector, false);
}

try {
  await page.goto(`${INDICO}/event/351/`, { waitUntil: "load" });
  if (await page.$("#assistant-launcher:not([hidden])")) await page.click("#assistant-launcher");
  await until(() => page.evaluate(() => document.documentElement.dataset.assistantPanel === "ready"), 20000);
  const small = (box) => !!box && box.h < 80 && box.w < 400;
  const trigger = await hover("#sidebar-trigger-button");
  check("hovering open sidebar shows a small tooltip", small(trigger), JSON.stringify(trigger));
  await chat().evaluate(() => document.getElementById("sidebar-trigger-button").click());
  await until(() => chat().evaluate(() => [...document.querySelectorAll("a[href^='/thread/']")].some((a) => a.offsetParent)));
  const fresh = await hover("#new-chat-button");
  check("hovering new chat shows a small tooltip", small(fresh), JSON.stringify(fresh));
  const search = await hover("#search-chats-button");
  check("hovering search shows a small tooltip", small(search), JSON.stringify(search));
  const thread = await hover("a[href^='/thread/']");
  check("hovering a conversation shows no page-sized box", !thread || small(thread), JSON.stringify(thread));
} finally {
  await page.screenshot({ path: new URL("./hover-last.png", import.meta.url).pathname });
  await browser.close();
}
console.log(`${results.filter(Boolean).length}/${results.length} checks passed`);
process.exit(results.every(Boolean) ? 0 : 1);
