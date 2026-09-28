// Shared helpers for the spec 020 browser walk (local stack only).
import { execFileSync } from "node:child_process";
import os from "node:os";
import puppeteer from "puppeteer";

export const INDICO = process.env.INDICO_URL || "http://127.0.0.1:8000";
const CHROME = process.env.CHROME_PATH || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const HOME = os.homedir();

// Over plain HTTP Indico names its session cookie `indico_session_http`.
export function mintSession(userId = 1) {
  const python = process.env.INDICO_PYTHON || `${HOME}/indico-assistant/instance/env/bin/python`;
  const out = execFileSync(python, [new URL("./mint_session.py", import.meta.url).pathname, String(userId)], {
    env: { ...process.env, INDICO_CONFIG: process.env.INDICO_CONFIG || `${HOME}/indico-assistant/instance/indico.conf` },
    stdio: ["ignore", "pipe", "ignore"],
  });
  return out.toString().trim().split("\n").pop();
}

export async function browserAs(userId = 1, { headless = true } = {}) {
  const browser = await puppeteer.launch({ executablePath: CHROME, headless, args: ["--window-size=1400,900"] });
  const page = await browser.newPage();
  await page.setViewport({ width: 1400, height: 900 });
  const url = new URL(INDICO);
  await page.setCookie({ name: "indico_session_http", value: mintSession(userId), domain: url.hostname, path: "/" });
  return { browser, page };
}
