// Cleanup test: box-select, delete, undo/redo, brush, then optionally save (and restore the original).
//   node tools/test_clean.mjs <out-prefix> [project] [export] [--save]
import puppeteer from "puppeteer-core";
const args = process.argv.slice(2);
const save = args.includes("--save");
const [prefix = "clean", project = "office", exp = "imported/playroom"] = args.filter((a) => !a.startsWith("--"));
const url = `http://127.0.0.1:5173/clean.html?project=${encodeURIComponent(project)}&export=${encodeURIComponent(exp)}`;
const browser = await puppeteer.launch({ executablePath: "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", headless: "new",
  args: ["--use-angle=d3d11", "--enable-gpu", "--ignore-gpu-blocklist"], protocolTimeout: 600000 });
const page = await browser.newPage();
await page.setViewport({ width: 1280, height: 800 });
page.on("pageerror", (e) => console.log("[pageerror]", e.message));
page.on("console", (m) => m.type() === "error" && console.log("[console.error]", m.text()));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const t0 = Date.now();
await page.goto(url, { waitUntil: "domcontentloaded" });
await page.waitForFunction(() => document.getElementById("loading")?.classList.contains("done") || /Could not/.test(document.getElementById("lmsg")?.textContent ?? ""),
  { timeout: 300000 });
const lmsg = await page.evaluate(() => document.getElementById("lmsg").textContent);
if (/Could not/.test(lmsg)) { console.log("FAILED:", lmsg); await browser.close(); process.exit(1); }
console.log(`loaded in ${((Date.now() - t0) / 1000).toFixed(1)} s`);
await sleep(2500);
await page.screenshot({ path: `${prefix}_0_loaded.png` });
const counts = () => page.evaluate(() => window.__clean.counts());

// Box select the middle of the view.
await page.mouse.move(520, 300);
await page.mouse.down();
await page.mouse.move(640, 380, { steps: 5 });
await page.mouse.move(760, 460, { steps: 5 });
await page.mouse.up();
await sleep(400);
const a = await counts();
console.log("after box select:", a);
await page.screenshot({ path: `${prefix}_1_selected.png` });
await page.keyboard.press("Delete");
await sleep(400);
const b = await counts();
console.log("after Delete:", b, "| deleted == previously selected:", b.d === a.s && b.s === 0);
await page.screenshot({ path: `${prefix}_2_deleted.png` });
await page.keyboard.down("Control"); await page.keyboard.press("KeyZ"); await page.keyboard.up("Control");
await sleep(300);
const c = await counts();
console.log("after Ctrl+Z:", c, "| restored and still selected:", c.d === 0 && c.s === a.s);
await page.keyboard.down("Control"); await page.keyboard.press("KeyY"); await page.keyboard.up("Control");
await sleep(300);
const d = await counts();
console.log("after Ctrl+Y:", d, "| deleted again:", d.d === a.s);
// Brush stroke along the left part of the view.
await page.keyboard.press("KeyB");
await page.mouse.move(300, 550);
await page.mouse.down();
for (let k = 0; k <= 12; k++) await page.mouse.move(300 + k * 20, 550 - k * 8);
await page.mouse.up();
await sleep(300);
const e = await counts();
console.log("after brush stroke:", e, "| brush selected something:", e.s > 0);
await page.screenshot({ path: `${prefix}_3_brush.png` });
console.log("stats bar:", await page.evaluate(() => document.getElementById("stats").innerText.replace(/\s+/g, " ")));
if (save) {
  await page.keyboard.press("Escape");
  await page.evaluate(() => document.getElementById("save").click());
  await page.waitForFunction(() => /Saved|Could not save/.test(document.getElementById("toast").innerText), { timeout: 600000 });
  console.log("save:", await page.evaluate(() => document.getElementById("toast").innerText));
}
await browser.close();
