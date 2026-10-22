// Loads the LiDAR alignment page headless, prints the live score, optionally nudges the piece, saves a screenshot and
// checks that saving works.  node tools/shot_align.mjs <out.png> [piece]
import puppeteer from "puppeteer-core";
const [out = "align.png", piece = "m1"] = process.argv.slice(2);
const browser = await puppeteer.launch({
  executablePath: "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  headless: "new",
  args: ["--window-size=1500,950"],
});
const page = await browser.newPage();
await page.setViewport({ width: 1500, height: 950 });
page.on("pageerror", (e) => console.log("[pageerror]", e.message));
await page.goto(`http://127.0.0.1:5173/align.html?piece=${piece}`, { waitUntil: "networkidle0" });
await new Promise((r) => setTimeout(r, 800));
console.log("score:", await page.$eval("#score", (e) => e.textContent));
await page.screenshot({ path: out });
await page.click("#save");
await new Promise((r) => setTimeout(r, 500));
console.log("save message:", await page.$eval("#msg", (e) => e.textContent));
await browser.close();
