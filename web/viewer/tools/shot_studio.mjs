// Studio check: open studio.html, wait for the project to load, full-page screenshot.
//   node tools/shot_studio.mjs <out.png> [project] [url]
import puppeteer from "puppeteer-core";
const [out = "studio.png", project = "", url = "http://127.0.0.1:5173/studio.html"] = process.argv.slice(2);
const browser = await puppeteer.launch({ executablePath: "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", headless: "new" });
const page = await browser.newPage();
await page.setViewport({ width: 1360, height: 900 });
if (project) await page.evaluateOnNewDocument((p) => localStorage.setItem("studio.project", p), project);
page.on("console", (m) => m.type() === "error" && console.log("[console.error]", m.text()));
page.on("pageerror", (e) => console.log("[pageerror]", e.message));
page.on("response", (r) => r.status() >= 400 && console.log("[http]", r.status(), r.url()));
await page.goto(url, { waitUntil: "networkidle2" });
await page.waitForFunction(() => document.querySelector(".stages") || document.querySelector(".empty"), { timeout: 30000 });
await new Promise((r) => setTimeout(r, 2500));
console.log(await page.evaluate(() => ({
  lanes: document.querySelectorAll(".lane").length, bars: document.querySelectorAll(".bar").length,
  stages: [...document.querySelectorAll(".stages tr")].map((r) => r.innerText.replace(/\s+/g, " ")),
})));
await page.screenshot({ path: out, fullPage: true });
await browser.close();
