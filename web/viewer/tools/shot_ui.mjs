// Click-through check: screenshot the scene, open the first info card, then an audio marker.
//   node tools/shot_ui.mjs <out-prefix> [url]
import puppeteer from "puppeteer-core";
const [prefix = "ui", url = "http://127.0.0.1:5173/"] = process.argv.slice(2);
const browser = await puppeteer.launch({
  executablePath: "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  headless: "new",
  args: ["--use-angle=d3d11", "--enable-gpu", "--ignore-gpu-blocklist", "--autoplay-policy=no-user-gesture-required"],
});
const page = await browser.newPage();
await page.setViewport({ width: 1280, height: 720 });
page.on("console", (m) => m.type() !== "debug" && !m.text().includes("X3203") && console.log(`[console.${m.type()}]`, m.text()));
page.on("pageerror", (e) => console.log("[pageerror]", e.message));
page.on("response", (r) => r.status() >= 400 && console.log("[http]", r.status(), r.url()));
await page.goto(url, { waitUntil: "domcontentloaded" });
await page.waitForFunction(() => document.getElementById("loading")?.classList.contains("done"), { timeout: 30000 });
await new Promise((r) => setTimeout(r, 2500));
await page.screenshot({ path: `${prefix}_scene.png` });
const info = await page.evaluate(() => [...document.querySelectorAll(".marker")].map((m) => ({
  id: m.dataset.id, kind: m.dataset.kind, visible: m.style.display !== "none" })));
console.log("markers:", JSON.stringify(info));
const clickMarker = async (kind) => {
  const ok = await page.evaluate((k) => {
    const el = [...document.querySelectorAll(".marker")].find((m) => m.dataset.kind === k && m.style.display !== "none")
      ?? [...document.querySelectorAll(".marker")].find((m) => m.dataset.kind === k);
    if (!el) return false;
    el.style.display = ""; el.click(); return true;
  }, kind);
  await new Promise((r) => setTimeout(r, 1500));
  return ok;
};
console.log("info card opened:", await clickMarker("info"));
await page.screenshot({ path: `${prefix}_card.png` });
await page.evaluate(() => document.querySelector("#card [data-next]")?.click());
await new Promise((r) => setTimeout(r, 800));
await page.screenshot({ path: `${prefix}_card2.png` });
await page.keyboard.press("Escape");
console.log("audio marker:", await clickMarker("audio"));
await new Promise((r) => setTimeout(r, 2500));
console.log("audio bar:", await page.evaluate(() => ({ open: document.getElementById("audiobar").classList.contains("open"),
  text: document.getElementById("audiobar").innerText.replace(/\s+/g, " ") })));
await page.screenshot({ path: `${prefix}_audio.png` });
await browser.close();
