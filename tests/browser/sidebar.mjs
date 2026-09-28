// Spec 020 US3 on the local stack: the Past Chats sidebar lists the user's conversations by day, pages
// through all of them, searches, opens any of them (SC-006: each within 2 s) and starts a new chat.
// Expects 100 conversations titled "SC006 seed 000" … "SC006 seed 099" for user 1 (oldest = 099).
//   node sidebar.mjs
import { browserAs, INDICO, mintSession } from "./lib.mjs";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const results = [];
const check = (name, ok, detail = "") => { results.push(ok); console.log(`${ok ? "ok  " : "FAIL"} ${name} ${detail}`); };
const { browser, page } = await browserAs(1, { headless: !process.argv.includes("--headful") });
const chat = () => page.frames().find((f) => f.url().startsWith("http://127.0.0.1:8001") && !f.url().includes("login"));
async function until(pred, ms = 10000, step = 50) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) { if (await pred().catch(() => false)) return Date.now() - t0; await sleep(step); }
  return null;
}
const press = (id) => chat().evaluate((id) => document.getElementById(id).click(), id);
const seeded = () => chat().evaluate(() => [...document.querySelectorAll("a[href^='/thread/']")]
  .filter((a) => a.innerText.includes("SC006 seed")).length);

try {
  await page.goto(`${INDICO}/event/351/`, { waitUntil: "load" });
  await page.click("#assistant-launcher");
  await until(() => page.evaluate(() => document.documentElement.dataset.assistantPanel === "ready"), 20000);

  // the list
  await press("sidebar-trigger-button");
  const listed = await until(() => chat().evaluate(() => document.querySelectorAll("a[href^='/thread/']").length > 0));
  check("SC-006 the sidebar lists conversations within 2 s", listed !== null && listed < 2000, `${listed} ms`);

  // every conversation, page after page (the sidebar loads more as it scrolls)
  let count = 0;
  for (let i = 0; i < 30; i++) {
    count = await seeded();
    if (count >= 100) break;
    await chat().evaluate(() => { const links = document.querySelectorAll("a[href^='/thread/']"); links[links.length - 1].scrollIntoView(); });
    await sleep(400);
  }
  check("all 100 conversations are reachable", count >= 100, `${count} listed`);
  const text = await chat().evaluate(() => document.body.innerText);
  check("US3 AS-1 grouped by day", ["Today", "Yesterday", "Previous 7 days", "Previous 30 days"].every((g) => text.includes(g)));

  // opening the oldest (SC-006)
  const t0 = Date.now();
  await chat().evaluate(() => [...document.querySelectorAll("a[href^='/thread/']")].find((a) => a.innerText.includes("SC006 seed 099")).click());
  const opened = await until(() => chat().evaluate(() => document.body.innerText.includes("Seeded answer number 99")));
  check("SC-006 the oldest opens within 2 s", opened !== null && Date.now() - t0 < 2000, `${Date.now() - t0} ms`);

  // US3 AS-2: the conversation picked is the one the next page restores
  await page.goto(`${INDICO}/category/0/`, { waitUntil: "load" });
  await until(() => page.evaluate(() => document.documentElement.dataset.assistantPanel === "ready"), 20000);
  check("US3 AS-2 the picked conversation is restored on the next page",
        (await until(() => chat().evaluate(() => document.body.innerText.includes("Seeded answer number 99")), 8000)) !== null);
  const remembered = await page.evaluate(() => JSON.parse(localStorage.getItem("indico-assistant:1") || "{}").threadId);

  // search (US3 AS-4); in a narrow panel the sidebar is a drawer that closed when the conversation opened
  if (!(await chat().evaluate(() => !!document.getElementById("search-chats-button")?.offsetParent))) {
    await press("sidebar-trigger-button");
  }
  await chat().waitForSelector("#search-chats-button", { visible: true, timeout: 5000 });
  await press("search-chats-button");
  // (in a narrow panel the sidebar drawer is a dialog too: the search dialog is the last one)
  const input = await chat().waitForFunction(() => [...document.querySelectorAll("[role=dialog]")].pop()?.querySelector("input"),
                                             { timeout: 5000 });
  await input.type("SC006 seed 042");
  const found = await until(() => chat().evaluate(() => {
    const text = [...document.querySelectorAll("[role=dialog]")].pop().innerText;
    return text.includes("SC006 seed 042") && !/SC006 seed (?!042)\d{3}/.test(text);
  }), 5000);
  check("US3 AS-4 search lists only the matching conversation", found !== null);
  await page.keyboard.press("Escape");

  // a new chat (US3 AS-3): empty, and the previous one is still listed
  await press("new-chat-button");
  await sleep(300);
  await chat().evaluate(() => {  // Chainlit asks before a new chat: confirm in the last dialog
    const confirm = [...([...document.querySelectorAll("[role=dialog]")].pop()?.querySelectorAll("button") || [])]
      .find((b) => /confirm/i.test(b.innerText));
    if (confirm) confirm.click();
  });
  const empty = await until(() => chat().evaluate(() => location.pathname === "/" &&
                                                      !document.body.innerText.includes("Seeded answer number 99")), 5000);
  if (!(await chat().evaluate(() => document.querySelectorAll("a[href^='/thread/']").length))) {
    await press("sidebar-trigger-button");  // (the drawer closed with the new chat)
    await until(() => chat().evaluate(() => document.querySelectorAll("a[href^='/thread/']").length > 0), 5000);
  }
  check("US3 AS-3 a new chat starts empty, the old one stays listed", empty !== null && (await seeded()) > 0,
        `empty=${empty !== null} url=${chat().url()}`);

  // SC-005: another user on this browser, even handed the first user's conversation id, sees none of it
  await page.setCookie({ name: "indico_session_http", value: mintSession(6), domain: new URL(INDICO).hostname, path: "/" });
  await page.evaluate((id) => localStorage.setItem("indico-assistant:6", JSON.stringify({ open: true, width: 440, threadId: id })),
                      remembered);
  await page.goto(`${INDICO}/event/351/`, { waitUntil: "load" });
  await until(() => page.evaluate(() => document.documentElement.dataset.assistantPanel === "ready"), 20000);
  await sleep(2500);  // (Chainlit refuses the thread and falls back to a new chat)
  await press("sidebar-trigger-button");
  await sleep(1500);
  const seen = await chat().evaluate(() => document.body.innerText);
  check("SC-005 another user sees none of it", !!remembered && !seen.includes("Seeded answer") && !seen.includes("SC006 seed"),
        `remembered=${!!remembered} answer=${seen.includes("Seeded answer")} listed=${seen.includes("SC006 seed")} url=${chat().url()}`);
} finally {
  await page.screenshot({ path: new URL("./sidebar-last.png", import.meta.url).pathname });
  await browser.close();
}
console.log(`${results.filter(Boolean).length}/${results.length} checks passed`);
process.exit(results.every(Boolean) ? 0 : 1);
