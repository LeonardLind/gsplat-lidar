// Gaze test: aim the camera at each marker, wait 3.5 s, check that its card opens / audio plays.
import puppeteer from "puppeteer-core";
const [prefix = "gaze", url = "http://127.0.0.1:5173/"] = process.argv.slice(2);
const browser = await puppeteer.launch({ executablePath: "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", headless: "new",
  args: ["--use-angle=d3d11", "--enable-gpu", "--ignore-gpu-blocklist", "--autoplay-policy=no-user-gesture-required"] });
const page = await browser.newPage();
await page.setViewport({ width: 1280, height: 720 });
page.on("pageerror", (e) => console.log("[pageerror]", e.message));
await page.goto(url, { waitUntil: "domcontentloaded" });
await page.waitForFunction(() => document.getElementById("loading")?.classList.contains("done"), { timeout: 30000 });
await new Promise((r) => setTimeout(r, 1500));
const ids = await page.evaluate(() => window.__gsl.markers.markers.map((m) => m.id));
for (const id of ids) {
  await page.evaluate((id) => {
    const g = window.__gsl, m = g.markers.markers.find((x) => x.id === id);
    g.card.close(); g.bar.stop();
    const e = g.player.eye(); const dx = m.position[0] - e.x, dy = m.position[1] - e.y, dz = m.position[2] - e.z;
    // Walk the player towards the marker if it is out of gaze range, then aim.
    const d = Math.hypot(dx, dy);
    if (Math.hypot(dx, dy, dz) > 6) { g.player.feet.x += dx * (1 - 4 / d); g.player.feet.y += dy * (1 - 4 / d); }
    const e2 = g.player.eye(); const ex = m.position[0] - e2.x, ey = m.position[1] - e2.y, ez = m.position[2] - e2.z;
    g.player.yaw = Math.atan2(ey, ex); g.player.pitch = Math.atan2(ez, Math.hypot(ex, ey));
  }, id);
  await new Promise((r) => setTimeout(r, 450));
  const mid = await page.evaluate(() => ({ gazed: window.__gsl.markers.gazed?.id ?? null,
    ring: document.querySelector("#crosshair .ring").style.strokeDashoffset }));
  if (id === ids[0]) await page.screenshot({ path: `${prefix}_progress.png` });
  await new Promise((r) => setTimeout(r, 900));
  const res = await page.evaluate(() => ({ card: window.__gsl.card.isOpen, audio: document.getElementById("audiobar").classList.contains("open") }));
  console.log(id, "gazed after 0.45 s:", mid.gazed, "ring offset", Number(mid.ring).toFixed(1), "-> after 1.35 s:", JSON.stringify(res));
}
// Card open: the player must still be able to walk, and walking away closes the card.
await page.evaluate(() => { const g = window.__gsl; const m = g.markers.markers.find((x) => x.kind === "info"); g.card.close();
  const e = g.player.eye(); g.player.yaw = Math.atan2(m.position[1] - e.y, m.position[0] - e.x);
  g.player.pitch = Math.atan2(m.position[2] - e.z, Math.hypot(m.position[0] - e.x, m.position[1] - e.y)); });
await new Promise((r) => setTimeout(r, 1500));
const before = await page.evaluate(() => ({ card: window.__gsl.card.isOpen, x: window.__gsl.player.feet.x, y: window.__gsl.player.feet.y }));
await page.evaluate(() => { window.__gsl.player.collide = false; window.__gsl.player.yaw += Math.PI; });
await page.keyboard.down("KeyW"); await new Promise((r) => setTimeout(r, 2500)); await page.keyboard.up("KeyW");
const after = await page.evaluate(() => ({ card: window.__gsl.card.isOpen, x: window.__gsl.player.feet.x, y: window.__gsl.player.feet.y }));
console.log("card open before walking:", before.card, "| moved", Math.hypot(after.x - before.x, after.y - before.y).toFixed(2), "m with the card open | card after walking away:", after.card);
await browser.close();
