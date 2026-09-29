// Spec 020 SC-003 on the local stack: in one conversation, "this event" and "this meeting" follow the page.
// Alternates between two meetings the user manages, 10 times: each time a question about "this event" is
// answered about the page's meeting, and "move this meeting" plans a change to it (plans are not confirmed).
//   A_EVENT=351 B_EVENT=354 node sc003.mjs
import { browserAs, INDICO } from "./lib.mjs";

const A = { id: process.env.A_EVENT || "351", title: process.env.A_TITLE || "Sync with Makoto" };
const B = { id: process.env.B_EVENT || "354", title: process.env.B_TITLE || "Planning with Makoto" };
const TRIES = Number(process.env.TRIES || 10);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const { browser, page } = await browserAs(1, { headless: !process.argv.includes("--headful") });

const chat = () => page.frames().find((f) => f.url().startsWith("http://127.0.0.1:8001") && !f.url().includes("login"));
async function ready() {
  for (let i = 0; i < 150; i++) {
    if (await page.evaluate(() => document.documentElement.dataset.assistantPanel === "ready")) return;
    await sleep(100);
  }
  throw new Error("panel not ready");
}
const answers = () => chat().evaluate(() => [...document.querySelectorAll("[data-step-type='assistant_message']")]
  .map((s) => s.innerText.trim()).filter(Boolean));
// after a navigation the panel redraws a plan still waiting (R7): wait until nothing more is drawn
async function settled() {
  let last = -1;
  for (let i = 0; i < 20; i++) {
    const now = (await answers()).length;
    if (now === last) return;
    last = now;
    await sleep(1000);
  }
}
async function ask(text) {
  const before = (await answers()).length;
  const input = await chat().waitForSelector("#chat-input", { timeout: 20000 });
  await sleep(1500);
  await input.click();
  await input.type(text);
  await input.press("Enter");
  for (let i = 0; i < 300; i++) {
    const now = await answers();
    if (now.length > before) { await sleep(800); return (await answers()).slice(before).join("\n"); }
    await sleep(500);
  }
  return "";
}

const scores = { question: 0, action: 0 };
try {
  await page.goto(`${INDICO}/event/${A.id}/`, { waitUntil: "load" });
  await page.click("#assistant-toggle");
  await ready();
  for (let n = 0; n < TRIES; n++) {
    const here = n % 2 === 0 ? A : B;
    const other = here === A ? B : A;
    if (n > 0) { await page.goto(`${INDICO}/event/${here.id}/`, { waitUntil: "load" }); await ready(); await settled(); }
    const answer = await ask("What is this event about?");
    // an answer, not a plan card: a question must not revise the plan still waiting
    const right = answer.includes(here.title) && !answer.includes(other.title) && !/Here is the plan|Change the meeting/.test(answer);
    scores.question += right;
    console.log(`${right ? "ok  " : "FAIL"} question on ${here.id}: ${answer.slice(0, 110).replace(/\n/g, " ")}`);
    const plan = await ask("Move this meeting to 4pm");
    const planned = plan.includes(here.title) && !plan.includes(other.title);
    scores.action += planned;
    console.log(`${planned ? "ok  " : "FAIL"} action on ${here.id}: ${plan.slice(0, 110).replace(/\n/g, " ")}`);
  }
} finally {
  await browser.close();
}
console.log(`SC-003: this event ${scores.question}/${TRIES}, this meeting ${scores.action}/${TRIES}`);
process.exit(scores.question === TRIES && scores.action === TRIES ? 0 : 1);
