// Tape measure check: floor-to-ceiling at a spot in the office should read about the LiDAR room height (2.7 m).
//   node tools/test_measure.mjs [url]   (GSL_BROWSER=<chrome.exe> if Edge does not start)
import puppeteer from "puppeteer-core";
const url = process.argv[2] ?? "http://127.0.0.1:5173/?touch=0";
const browser = await puppeteer.launch({
  executablePath: process.env.GSL_BROWSER ?? "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  headless: "new", args: ["--use-angle=d3d11", "--enable-gpu", "--ignore-gpu-blocklist"],
});
const page = await browser.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
await page.setViewport({ width: 1280, height: 720 });
await page.goto(url, { waitUntil: "domcontentloaded" });
await page.waitForFunction(() => document.getElementById("loading")?.classList.contains("done") && document.body.classList.contains("has-lidar"), { timeout: 120000 });
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
await page.keyboard.press("KeyT");
const look = async (pitch) => {
  await page.evaluate((pitch) => { const p = window.__gsl.player; p.mode = "fly"; p.collide = false; p.pitch = pitch; }, pitch);
  await wait(400);
  await page.mouse.click(640, 360);
  await wait(300);
};
await page.evaluate(() => { const p = window.__gsl.player; const f = p.feet.clone(); p.feet.set(f.x, f.y, 0.0); });
await page.mouse.click(640, 360); await wait(300); // the first click grabs the mouse (pointer lock), as in normal use
await look(-1.55);
await look(1.55);
const text = await page.evaluate(() => document.querySelector(".measure-label")?.textContent ?? "");
const status = await page.evaluate(() => document.getElementById("status").textContent);
console.log(`label: ${text} | status: ${status}`);
await browser.close();
if (errors.length) { console.error(errors.join("\n")); process.exit(1); }
