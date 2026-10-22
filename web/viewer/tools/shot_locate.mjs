// Loads the "where was this?" page headless, makes a test click on the plan and saves a screenshot.
//   node tools/shot_locate.mjs <out.png>
import puppeteer from "puppeteer-core";
const [out = "locate.png"] = process.argv.slice(2);
const browser = await puppeteer.launch({
  executablePath: "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  headless: "new",
  args: ["--window-size=1600,950"],
});
const page = await browser.newPage();
await page.setViewport({ width: 1600, height: 950 });
page.on("pageerror", (e) => console.log("[pageerror]", e.message));
await page.goto("http://127.0.0.1:5173/locate.html", { waitUntil: "networkidle0" });
await new Promise((r) => setTimeout(r, 800));
console.log("rows:", await page.$$eval(".moment", (e) => e.length), " thumbs loaded:", await page.$$eval(".thumbs img", (e) => e.filter((i) => i.complete && i.naturalWidth > 0).length));
await page.mouse.click(1100, 400); // a click on the plan marks the active row (chunk 0 start) and moves on
await page.mouse.move(1200, 600);
await page.mouse.down(); await page.mouse.move(1260, 560, { steps: 5 }); await page.mouse.up(); // drag = position + heading for the next row
console.log("count:", await page.$eval("#count", (e) => e.textContent));
await page.screenshot({ path: out });
await browser.close();
