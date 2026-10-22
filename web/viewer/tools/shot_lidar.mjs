// Screenshots of the explorer's LiDAR layer: node tools/shot_lidar.mjs <out-prefix> [url] [x y z yawDeg pitchDeg]
// Shots: splat only, splat + LiDAR (RGB), LiDAR only (RGB, intensity, height), LiDAR at 60 % over the splat,
// LiDAR only with the ceiling cut. Errors in the page are printed (and fail the run).
import puppeteer from "puppeteer-core";
const [prefix = "lidar", url = "http://127.0.0.1:5173/?touch=0", ...pose] = process.argv.slice(2);
const browser = await puppeteer.launch({
  executablePath: process.env.GSL_BROWSER ?? "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  headless: "new",
  args: ["--use-angle=d3d11", "--enable-gpu", "--ignore-gpu-blocklist", "--window-size=1280,720"],
});
const page = await browser.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
await page.setViewport({ width: 1280, height: 720 });
await page.goto(url, { waitUntil: "domcontentloaded" });
await page.waitForFunction(() => document.getElementById("loading")?.classList.contains("done"), { timeout: 120000 });
await page.waitForFunction(() => document.body.classList.contains("has-lidar"), { timeout: 120000 });
await page.evaluate(() => { document.getElementById("hud").style.display = "none"; });
if (pose.length === 5) {
  await page.evaluate((x, y, z, yaw, pitch) => {
    const p = window.__gsl.player;
    p.collide = false; p.mode = "fly"; p.feet.set(x, y, z);
    p.yaw = (yaw * Math.PI) / 180; p.pitch = (pitch * Math.PI) / 180;
  }, ...pose.map(Number));
}
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const shot = async (name) => { await wait(1500); await page.screenshot({ path: `${prefix}-${name}.png` }); };
const press = async (...keys) => { for (const k of keys) { await page.keyboard.press(k); await wait(100); } };
const shift = async (k) => { await page.keyboard.down("Shift"); await page.keyboard.press(k); await page.keyboard.up("Shift"); };
await shot("1-splat");
await press("KeyL"); await shot("2-splat+lidar");
await shift("KeyL"); await shot("3-lidar-rgb");
await press("KeyK"); await shot("4-lidar-intensity");
await press("KeyK"); await shot("5-lidar-height");
await press("KeyK"); await shift("KeyL"); await press("KeyO"); await shot("6-lidar60-over-splat");
await press("KeyO", "KeyO"); await shift("KeyL");
for (let i = 0; i < 6; i++) await press("BracketLeft");
const status = await page.evaluate(() => document.getElementById("status").textContent);
await shot("7-lidar-cut");
console.log(`status after the cut: ${status}`);
await browser.close();
if (errors.length) { console.error(errors.join("\n")); process.exit(1); }
console.log("7 screenshots, no page errors");
