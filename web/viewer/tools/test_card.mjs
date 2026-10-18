// Anchored-card test: gaze-open an info card, check it sits above its marker and follows it when looking
// around, slide to the next picture, then look away and check it closes.
//   node tools/test_card.mjs <out-prefix> [url]
import puppeteer from "puppeteer-core";
const [prefix = "card", url = "http://127.0.0.1:5173/"] = process.argv.slice(2);
const browser = await puppeteer.launch({ executablePath: "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", headless: "new",
  args: ["--use-angle=d3d11", "--enable-gpu", "--ignore-gpu-blocklist", "--autoplay-policy=no-user-gesture-required"] });
const page = await browser.newPage();
await page.setViewport({ width: 1280, height: 720 });
page.on("pageerror", (e) => console.log("[pageerror]", e.message));
await page.goto(url, { waitUntil: "domcontentloaded" });
await page.waitForFunction(() => document.getElementById("loading")?.classList.contains("done"), { timeout: 30000 });
await new Promise((r) => setTimeout(r, 1500));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
// Card rectangle vs. its marker icon on screen.
const geom = () => page.evaluate(() => {
  const c = document.getElementById("card").getBoundingClientRect();
  const id = window.__gsl.markers.activeId;
  const m = id && document.querySelector(`.marker[data-id="${id}"] .icon`)?.getBoundingClientRect();
  return { open: window.__gsl.card.isOpen, card: [c.left, c.top, c.right, c.bottom].map(Math.round),
    marker: m ? [Math.round((m.left + m.right) / 2), Math.round(m.top)] : null };
});
const id = await page.evaluate(() => {
  const g = window.__gsl, m = g.markers.markers.find((x) => (x.images?.length ?? 0) > 1) ?? g.markers.markers.find((x) => x.kind !== "audio");
  const e = g.player.eye(); const dx = m.position[0] - e.x, dy = m.position[1] - e.y, dz = m.position[2] - e.z;
  const d = Math.hypot(dx, dy);
  if (Math.hypot(dx, dy, dz) > 4) { g.player.feet.x += dx * (1 - 3 / d); g.player.feet.y += dy * (1 - 3 / d); }
  const e2 = g.player.eye(); const ex = m.position[0] - e2.x, ey = m.position[1] - e2.y, ez = m.position[2] - e2.z;
  g.player.yaw = Math.atan2(ey, ex); g.player.pitch = Math.atan2(ez, Math.hypot(ex, ey));
  return m.id;
});
await sleep(1150);
await page.screenshot({ path: `${prefix}_fadein.png` });
await sleep(600);
const g1 = await geom();
console.log(id, "after gaze:", JSON.stringify(g1), "| card centred over marker:", g1.marker && Math.abs((g1.card[0] + g1.card[2]) / 2 - g1.marker[0]) < 3,
  "| gap card->marker px:", g1.marker && g1.marker[1] - g1.card[3]);
await page.screenshot({ path: `${prefix}_open.png` });
// Look 15° to the right and a little down: the card must move with the marker.
await page.evaluate(() => { window.__gsl.player.yaw -= 0.26; window.__gsl.player.pitch -= 0.12; });
await sleep(300);
const g2 = await geom();
console.log("after turning:", JSON.stringify(g2), "| moved px:", g2.card[0] - g1.card[0], g2.card[1] - g1.card[1]);
await page.evaluate(() => document.querySelector("#card [data-next]")?.click());
await sleep(200);
await page.screenshot({ path: `${prefix}_sliding.png` });
await sleep(500);
await page.screenshot({ path: `${prefix}_next.png` });
// Crosshair clicks: pretend the pointer is locked, turn the view so the crosshair is on a card button,
// and click the canvas (where a locked pointer's clicks land): the button under the crosshair must get it.
await page.evaluate(() => {
  const c = document.getElementById("view");
  Object.defineProperty(document, "pointerLockElement", { configurable: true, get: () => c });
  document.exitPointerLock = () => {};
});
const aimAt = async (sel) => {
  // Turn gradually, like a mouse would: a fifth of the remaining angle every 50 ms.
  for (let k = 0; k < 20; k++) {
    await page.evaluate((sel) => {
      const r = document.querySelector(sel).getBoundingClientRect(), g = window.__gsl;
      const f = innerHeight / 2 / Math.tan((70 / 2) * Math.PI / 180);
      g.player.yaw -= 0.2 * Math.atan(((r.left + r.right) / 2 - innerWidth / 2) / f);
      g.player.pitch += 0.2 * Math.atan((innerHeight / 2 - (r.top + r.bottom) / 2) / f);
    }, sel);
    await sleep(50);
  }
  await sleep(100);
  return page.evaluate((sel) => ({ aimed: document.querySelector(sel).classList.contains("aimed"),
    crossAim: document.getElementById("crosshair").classList.contains("aim") }), sel);
};
console.log("aim at next:", JSON.stringify(await aimAt("#card [data-next]")));
await page.screenshot({ path: `${prefix}_aim.png` });
const dotBefore = await page.evaluate(() => [...document.querySelectorAll("#card .dots i")].findIndex((d) => d.classList.contains("on")));
await page.evaluate(() => document.getElementById("view").click());
await sleep(300);
const dotAfter = await page.evaluate(() => [...document.querySelectorAll("#card .dots i")].findIndex((d) => d.classList.contains("on")));
console.log("crosshair click on next: picture", dotBefore, "->", dotAfter);
console.log("aim at fullscreen:", JSON.stringify(await aimAt("#card [data-full]")));
await page.evaluate(() => document.getElementById("view").click());
await sleep(500);
console.log("expanded:", await page.evaluate(() => ({ full: window.__gsl.card.isFullscreen, body: document.body.classList.contains("card-expanded") })));
await page.screenshot({ path: `${prefix}_expanded.png` });
await page.keyboard.press("Escape");
await sleep(300);
const g3 = await geom();
console.log("after Esc:", JSON.stringify({ ...g3, full: await page.evaluate(() => window.__gsl.card.isFullscreen) }));
await page.evaluate(() => delete document.pointerLockElement);
// Turn until the marker is out of view: the card must close.
await page.evaluate(() => { window.__gsl.player.yaw -= 1.4; });
await sleep(300);
console.log("after looking away:", JSON.stringify(await geom()));
await browser.close();
