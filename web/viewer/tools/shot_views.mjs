// Screenshots of the explorer from given poses: node tools/shot_views.mjs <out-prefix> <poses.json> [url]
// poses.json: [[x, y, z, yawDeg, pitchDeg], ...] in the scene's world frame (z up). Uses the debug handle window.__gsl.
import fs from "node:fs";
import puppeteer from "puppeteer-core";
const [prefix = "view", posesFile, url = "http://127.0.0.1:5173/?touch=0"] = process.argv.slice(2);
const poses = JSON.parse(fs.readFileSync(posesFile, "utf8"));
const browser = await puppeteer.launch({
  executablePath: process.env.GSL_BROWSER ?? "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  headless: "new",
  args: ["--use-angle=d3d11", "--enable-gpu", "--ignore-gpu-blocklist", "--window-size=1280,720"],
});
const page = await browser.newPage();
await page.setViewport({ width: 1280, height: 720 });
await page.goto(url, { waitUntil: "domcontentloaded" });
await page.waitForFunction(() => document.getElementById("loading")?.classList.contains("done"), { timeout: 90000 });
await page.evaluate(() => { document.getElementById("hud").style.display = "none"; });
for (let i = 0; i < poses.length; i++) {
  const [x, y, z, yaw, pitch] = poses[i];
  await page.evaluate((x, y, z, yaw, pitch) => {
    const p = window.__gsl.player;
    p.collide = false;
    p.mode = "fly";
    p.feet.set(x, y, z);
    p.yaw = (yaw * Math.PI) / 180;
    p.pitch = (pitch * Math.PI) / 180;
  }, x, y, z, yaw, pitch);
  await new Promise((r) => setTimeout(r, 1800));
  await page.screenshot({ path: `${prefix}-${i}.png` });
}
await browser.close();
console.log(`${poses.length} screenshots`);
