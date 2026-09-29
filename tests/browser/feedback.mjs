// Spec 020 feedback (T046-T047) on the local stack: the panel's thumbs are Indico feedback. A vote with a comment
// is kept after a reload, a switch replaces it, and clicking the same thumb again takes it back.
//   WALK_USER=6 node feedback.mjs
import { browserAs, INDICO } from "./lib.mjs";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const results = [];
const check = (name, ok, detail = "") => { results.push(ok); console.log(`${ok ? "ok  " : "FAIL"} ${name} ${detail}`); };
const USER = Number(process.env.WALK_USER || 1);
const { browser, page } = await browserAs(USER, { headless: !process.argv.includes("--headful") });
const chat = () => page.frames().find((f) => f.url().startsWith("http://127.0.0.1:8001") && !f.url().includes("login"));
async function until(pred, ms = 10000) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) { if (await pred().catch(() => false)) return true; await sleep(100); }
  return false;
}
const ready = () => until(() => page.evaluate(() => document.documentElement.dataset.assistantPanel === "ready"), 20000);
const shown = (cls) => chat().evaluate((cls) => !!document.querySelector(`.${cls}`), cls);
const press = (cls) => chat().evaluate((cls) => document.querySelector(`.${cls}`).click(), cls);
// what Indico keeps: the conversation's last answer's feedback, read as the page (the user's own session)
const kept = () => page.evaluate(async (user) => {
  const { threadId } = JSON.parse(localStorage.getItem(`indico-assistant:${user}`));
  const body = await (await fetch(`/api/assistant/sessions/${threadId}`, { cache: "no-store" })).json();
  return body.messages.filter((m) => m.role === "assistant").pop()?.feedback || null;
}, USER);
async function vote(cls, comment) {  // a thumb opens Chainlit's feedback dialog; its submit sends the vote
  await press(cls);
  const field = await chat().waitForFunction(() => [...document.querySelectorAll("[role=dialog]")].pop()?.querySelector("textarea"),
                                             { timeout: 5000 });
  if (comment) await field.type(comment);
  await chat().evaluate(() => document.getElementById("submit-feedback").click());
}

try {
  await page.goto(`${INDICO}/event/351/`, { waitUntil: "load" });
  if (await page.$("#assistant-toggle[aria-expanded=false]")) await page.click("#assistant-toggle");
  await ready();
  const input = await chat().waitForSelector("#chat-input");
  await sleep(1500);
  await input.click();
  await input.type(`Feedback check ${Date.now()}: what is this event about?`);
  await input.press("Enter");
  check("an answer has thumbs", await until(() => shown("negative-feedback-off"), 120000));

  await vote("negative-feedback-off", "wrong meeting");
  const down = await until(async () => (await kept())?.value === 0);
  const fb = await kept();
  check("a thumbs down with a comment is kept in Indico", down && fb.comment === "wrong meeting", JSON.stringify(fb));

  await page.reload({ waitUntil: "load" });
  await ready();
  check("and shown again after a reload", await until(() => shown("negative-feedback-on"), 10000));

  await vote("positive-feedback-off");
  check("switching to thumbs up replaces it",
        await until(async () => (await kept())?.value === 1) && await shown("positive-feedback-on"), JSON.stringify(await kept()));

  await press("positive-feedback-on");  // the same thumb again takes the vote back
  check("clicking it again takes the vote back", await until(async () => (await kept()) === null) && await shown("positive-feedback-off"));
  await page.reload({ waitUntil: "load" });
  await ready();
  await sleep(1500);
  check("and it stays taken back after a reload",
        await shown("positive-feedback-off") && !(await shown("positive-feedback-on")) && !(await shown("negative-feedback-on")));
} finally {
  await page.screenshot({ path: new URL("./feedback-last.png", import.meta.url).pathname });
  await browser.close();
}
console.log(`${results.filter(Boolean).length}/${results.length} checks passed`);
process.exit(results.every(Boolean) ? 0 : 1);
