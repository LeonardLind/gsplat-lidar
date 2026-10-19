// Tablet controls test: emulates an iPad (touch, 1180x820) and drives the on-screen sticks with real touch events.
//   node tools/test_touch.mjs <out-prefix> [url]
// Checks: left stick moves, right stick looks, drag-to-look, walk/drone switch, drone up/down, both thumbs at once,
// and that the desktop help panel is hidden. Saves <prefix>-walk.png and <prefix>-drone.png.
import puppeteer from "puppeteer-core";
const [prefix = "touch", url = "http://127.0.0.1:5173/?touch=1"] = process.argv.slice(2);
const browser = await puppeteer.launch({
  executablePath: "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  headless: "new",
  args: ["--use-angle=d3d11", "--enable-gpu", "--ignore-gpu-blocklist", "--window-size=1180,820"],
});
const page = await browser.newPage();
await page.setViewport({ width: 1180, height: 820, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
page.on("pageerror", (e) => console.log("[pageerror]", e.message));
await page.goto(url, { waitUntil: "domcontentloaded" });
await page.waitForFunction(() => document.getElementById("loading")?.classList.contains("done"), { timeout: 60000 });
await new Promise((r) => setTimeout(r, 1500));

let fails = 0;
const check = (name, ok, detail = "") => { console.log(`${ok ? "PASS" : "FAIL"}  ${name} ${detail}`); if (!ok) fails++; };
const state = () => page.evaluate(() => { const p = window.__gsl.player; return { x: p.feet.x, y: p.feet.y, z: p.feet.z, yaw: p.yaw, pitch: p.pitch, mode: p.mode }; });
const centre = async (sel) => page.$eval(sel, (e) => { const r = e.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; });
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);

check("touch mode on, help panel hidden", await page.evaluate(() => document.body.classList.contains("touch") && getComputedStyle(document.getElementById("hud")).display === "none"));

// 1. left stick forward -> the player moves
const L = await centre(".tstick.left");
let s0 = await state();
let t = await page.touchscreen.touchStart(L.x, L.y);
await t.move(L.x, L.y - 62);
await wait(1500);
let s1 = await state();
await t.end();
check("left stick moves the player", dist(s0, s1) > 0.5, `moved ${dist(s0, s1).toFixed(2)} m`);
await wait(200);
let s1b = await state();
await wait(300);
check("player stops when the stick is released", dist(s1b, await state()) < 0.05);

// 2. right stick right -> yaw turns clockwise (yaw decreases)
const R = await centre(".tstick.right");
s0 = await state();
t = await page.touchscreen.touchStart(R.x, R.y);
await t.move(R.x + 62, R.y);
await wait(900);
s1 = await state();
await t.end();
check("right stick turns the view", s1.yaw < s0.yaw - 0.3, `yaw ${s0.yaw.toFixed(2)} -> ${s1.yaw.toFixed(2)}`);

// 3. drag on the picture looks around
s0 = await state();
t = await page.touchscreen.touchStart(600, 300);
await t.move(700, 300);
await t.move(760, 340);
await t.end();
s1 = await state();
check("dragging the picture looks around", Math.abs(s1.yaw - s0.yaw) > 0.3 && s1.pitch < s0.pitch, `yaw ${(s1.yaw - s0.yaw).toFixed(2)}, pitch ${(s1.pitch - s0.pitch).toFixed(2)}`);

// 4. both thumbs at once: move forward while turning
s0 = await state();
const tl = await page.touchscreen.touchStart(L.x, L.y);
const tr = await page.touchscreen.touchStart(R.x, R.y);
await tl.move(L.x, L.y - 62);
await tr.move(R.x - 62, R.y);
await wait(1200);
s1 = await state();
await tl.end();
await tr.end();
check("both sticks work at the same time", dist(s0, s1) > 0.4 && s1.yaw > s0.yaw + 0.3, `moved ${dist(s0, s1).toFixed(2)} m, yaw ${(s1.yaw - s0.yaw).toFixed(2)}`);
await page.screenshot({ path: `${prefix}-walk.png` });

// 5. switch to drone, then up / down
await page.touchscreen.tap(...(await Promise.all([page.$eval(".tswitch button:nth-child(2)", (e) => { const r = e.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; })])).flat());
await wait(300);
s0 = await state();
check("Drone button switches the mode", s0.mode === "fly", `mode ${s0.mode}`);
const up = await page.$eval(".tbtns.drone button:nth-child(2)", (e) => { const r = e.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; });
const down = await page.$eval(".tbtns.drone button:nth-child(1)", (e) => { const r = e.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; });
t = await page.touchscreen.touchStart(up.x, up.y);
await wait(1000);
s1 = await state();
await t.end();
check("up button raises the drone", s1.z > s0.z + 0.8, `z ${s0.z.toFixed(2)} -> ${s1.z.toFixed(2)}`);
t = await page.touchscreen.touchStart(down.x, down.y);
await wait(700);
const s2 = await state();
await t.end();
check("down button lowers the drone", s2.z < s1.z - 0.5, `z ${s1.z.toFixed(2)} -> ${s2.z.toFixed(2)}`);
// look up + push forward in drone mode: flies along the view (gains height)
await page.screenshot({ path: `${prefix}-drone.png` });

// 6. back to walk: lands on the ground
await page.touchscreen.tap(...(await page.$eval(".tswitch button:nth-child(1)", (e) => { const r = e.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; })));
await wait(1500);
const s3 = await state();
check("Walk button lands the player again", s3.mode === "walk" && s3.z < s2.z + 0.01, `mode ${s3.mode}, z ${s3.z.toFixed(2)}`);

console.log(fails ? `\n${fails} check(s) FAILED` : "\nall touch checks passed");
await browser.close();
process.exit(fails ? 1 : 0);
