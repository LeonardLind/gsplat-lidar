// Headless check of the viewer: loads the page in the installed Edge, prints console output,
// waits for the splat to load and saves a screenshot.  node tools/shot.mjs <out.png> [url] [waitMs]
import puppeteer from "puppeteer-core";
const [out = "shot.png", url = "http://127.0.0.1:5173/", wait = "20000"] = process.argv.slice(2);
const browser = await puppeteer.launch({
  executablePath: "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  headless: "new",
  args: ["--use-angle=d3d11", "--enable-gpu", "--ignore-gpu-blocklist", "--enable-unsafe-webgpu", "--window-size=1280,720"],
});
const page = await browser.newPage();
await page.setViewport({ width: 1280, height: 720 });
page.on("console", (m) => console.log(`[console.${m.type()}]`, m.text()));
page.on("pageerror", (e) => console.log("[pageerror]", e.message));
page.on("requestfailed", (r) => console.log("[requestfailed]", r.url(), r.failure()?.errorText));
await page.goto(url, { waitUntil: "domcontentloaded" });
const t0 = Date.now();
try {
  await page.waitForFunction(() => document.getElementById("loading")?.classList.contains("done"), { timeout: +wait });
  console.log(`splat loaded after ${((Date.now() - t0) / 1000).toFixed(1)} s`);
} catch {
  console.log("splat NOT loaded; loading text:", await page.$eval("#loading", (e) => e.textContent));
}
await new Promise((r) => setTimeout(r, 2500));
await page.screenshot({ path: out });
console.log("gl:", await page.evaluate(() => {
  const gl = document.createElement("canvas").getContext("webgl2");
  const ext = gl?.getExtension("WEBGL_debug_renderer_info");
  return gl ? gl.getParameter(ext ? ext.UNMASKED_RENDERER_WEBGL : gl.RENDERER) : "no webgl2";
}));
await browser.close();
