// "Where was this?": for each chunk of the walk the user marks, on the LiDAR plan, where the start / middle / end
// photos were taken (click = position, drag = position + the direction the front picture looks). Saved to
// /api/locate -> projects/office-x4/lidar/locate.json, read by app/lidar/solve_clicks.py.

export {}; // a module of its own: the other pages declare the same helper names

interface Plan { url: string; x0: number; x1: number; y0: number; y1: number; res: number }
interface Thumb { view: string; url: string }
interface Moment { label: string; frame: string; thumbs: Thumb[] }
interface Guess { path: number[][]; score: number; click_rms_m: number }
interface Chunk { id: number; model: string; n_frames: number; first_index: number; last_index: number; moments: Moment[]; check?: boolean; guess?: Guess | null }
interface Mark { x: number; y: number; heading?: number }
type Marks = Record<string, Record<string, Mark>>; // chunk id -> moment label -> mark

const $ = <E extends HTMLElement>(id: string) => document.getElementById(id) as E;
const canvas = $<HTMLCanvasElement>("plan");
const ctx = canvas.getContext("2d")!;

async function main() {
  const data: { plan: Plan; chunks: Chunk[] } = await (await fetch(`/locate/chunks.json?${Date.now()}`)).json();
  const P = data.plan;
  const plan = new Image();
  plan.src = "/locate/plan.png";
  await plan.decode();
  let marks: Marks = {};
  try { marks = await (await fetch("/api/locate")).json(); } catch { /* nothing saved yet */ }
  const colours = data.chunks.map((_, i) => `hsl(${(i * 137) % 360} 80% 62%)`);
  let active: { chunk: number; label: string } | null = null;

  // ---- list of chunks with photos
  const list = $("list");
  const nCheck = data.chunks.filter((c) => c.check).length;
  list.innerHTML = `<h1>Where was this?</h1><div class="hint">${data.chunks.length} continuous stretches of the walk, in walking order. Chunk 0 is the beginning of the first video.</div>`
    + (nCheck ? `<div class="hint" style="color:#ffb020"><b>${nCheck} chunks need a second look</b> (orange badge): Claude's best guess for their path is drawn on the plan as a dotted line while the chunk is selected. If the dotted line looks like the real walk, leave the clicks; if not, click the right spots again (a new click replaces the old one). <button id="onlycheck" class="on">Only chunks to check</button></div>` : "");
  const rows = new Map<string, HTMLElement>();
  const boxes: HTMLElement[] = [];
  for (const c of data.chunks) {
    const box = document.createElement("div");
    box.className = "chunk";
    boxes.push(box);
    box.dataset.check = c.check ? "1" : "0";
    const badge = c.check ? ` <span style="background:#ffb020;color:#111;border-radius:4px;padding:0 6px;font-size:11.5px;font-weight:600">check${c.guess ? ` · fit ${c.guess.score.toFixed(2)}, ${c.guess.click_rms_m} m from your clicks` : ""}</span>` : "";
    box.innerHTML = `<h2><span class="dot" style="background:${colours[c.id]}"></span>Chunk ${c.id}${badge} <span class="hint" style="margin:0">${c.n_frames} frames (${(c.n_frames * 0.4 / 60).toFixed(1)} min) · frames ${c.first_index}-${c.last_index}</span></h2>`;
    for (const m of c.moments) {
      const row = document.createElement("div");
      row.className = "moment";
      row.innerHTML = `<div class="lbl"><b>${m.label}</b><button>place</button></div><div class="thumbs">${m.thumbs.map((t) => `<div><span>${t.view}</span><img loading="lazy" src="/locate/${t.url}"></div>`).join("")}</div>`;
      row.querySelector("button")!.addEventListener("click", () => select(c.id, m.label));
      box.appendChild(row);
      rows.set(`${c.id}/${m.label}`, row);
    }
    list.appendChild(box);
  }
  // "only chunks to check" filter; flagged chunks first when it is on
  let onlyCheck = nCheck > 0;
  const applyFilter = () => {
    boxes.forEach((b) => { b.style.display = onlyCheck && b.dataset.check !== "1" ? "none" : ""; });
    const btn = document.getElementById("onlycheck");
    if (btn) { btn.classList.toggle("on", onlyCheck); btn.textContent = onlyCheck ? "Showing only chunks to check (click to show all)" : "Showing all chunks (click for only those to check)"; }
  };
  document.getElementById("onlycheck")?.addEventListener("click", () => { onlyCheck = !onlyCheck; applyFilter(); });
  applyFilter();

  function select(chunk: number, label: string) {
    active = { chunk, label };
    refresh();
    rows.get(`${chunk}/${label}`)!.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
  function refresh() {
    for (const [k, row] of rows) {
      const [c, l] = k.split("/");
      row.classList.toggle("active", !!active && active.chunk === +c && active.label === l);
      row.classList.toggle("done", !!marks[c]?.[l]);
      row.querySelector("button")!.classList.toggle("on", !!active && active.chunk === +c && active.label === l);
    }
    const nStart = data.chunks.filter((c) => marks[c.id]?.start && marks[c.id]?.end).length;
    $("count").textContent = `${nStart}/${data.chunks.length} chunks with start and end`;
    draw();
  }

  // ---- plan view
  const view = { cx: (P.x0 + P.x1) / 2, cy: (P.y0 + P.y1) / 2, k: 10 };
  let fitted = false;
  const resize = () => {
    canvas.width = canvas.clientWidth; canvas.height = canvas.clientHeight;
    if (!fitted) { fitted = true; view.k = 0.97 * Math.min(canvas.width / (P.x1 - P.x0), canvas.height / (P.y1 - P.y0)); }
    draw();
  };
  const toScreen = (x: number, y: number): [number, number] => [canvas.width / 2 + (x - view.cx) * view.k, canvas.height / 2 - (y - view.cy) * view.k];
  const toWorld = (sx: number, sy: number): [number, number] => [view.cx + (sx - canvas.width / 2) / view.k, view.cy - (sy - canvas.height / 2) / view.k];

  function draw() {
    ctx.fillStyle = "#101114"; ctx.fillRect(0, 0, canvas.width, canvas.height);
    const [sx0, sy0] = toScreen(P.x0, P.y1);
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(plan, sx0, sy0, (P.x1 - P.x0) * view.k, (P.y1 - P.y0) * view.k);
    // Claude's current guess for the path of the selected chunk (dotted, in the chunk's colour)
    const sel = active ? data.chunks[active.chunk] : null;
    if (sel?.guess) {
      ctx.strokeStyle = colours[sel.id]; ctx.lineWidth = 3; ctx.setLineDash([2, 6]);
      ctx.beginPath();
      sel.guess.path.forEach(([x, y], i) => { const [sx, sy] = toScreen(x, y); i ? ctx.lineTo(sx, sy) : ctx.moveTo(sx, sy); });
      ctx.stroke(); ctx.setLineDash([]);
      const [gx, gy] = toScreen(sel.guess.path[0][0], sel.guess.path[0][1]);
      ctx.fillStyle = colours[sel.id]; ctx.font = "bold 12px system-ui"; ctx.fillText("guess: start", gx + 8, gy + 14);
    }
    for (const c of data.chunks) {
      const mk = marks[c.id];
      if (!mk) continue;
      const order = ["start", "quarter", "middle", "three-quarters", "end"].filter((l) => mk[l]);
      ctx.strokeStyle = colours[c.id]; ctx.lineWidth = 2; ctx.setLineDash([6, 5]);
      ctx.beginPath();
      order.forEach((l, i) => { const [x, y] = toScreen(mk[l].x, mk[l].y); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
      ctx.stroke(); ctx.setLineDash([]);
      for (const l of order) {
        const m = mk[l]; const [x, y] = toScreen(m.x, m.y);
        ctx.fillStyle = colours[c.id];
        ctx.beginPath(); ctx.arc(x, y, l === "start" || l === "end" ? 7 : 4, 0, Math.PI * 2); ctx.fill();
        if (m.heading !== undefined) {
          ctx.strokeStyle = colours[c.id]; ctx.lineWidth = 3;
          ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x + Math.cos(m.heading) * 22, y - Math.sin(m.heading) * 22); ctx.stroke();
        }
        if (l === "start" || l === "end") { ctx.fillStyle = "#fff"; ctx.font = "bold 12px system-ui"; ctx.fillText(`${c.id}${l === "start" ? "s" : "e"}`, x + 9, y - 8); }
      }
    }
  }

  // click = position, drag = position + heading, right-drag = pan, wheel = zoom
  let down: { sx: number; sy: number; wx: number; wy: number; button: number; px: number; py: number } | null = null;
  canvas.addEventListener("contextmenu", (e) => e.preventDefault());
  canvas.addEventListener("pointerdown", (e) => {
    canvas.setPointerCapture(e.pointerId);
    const [wx, wy] = toWorld(e.offsetX, e.offsetY);
    down = { sx: e.offsetX, sy: e.offsetY, wx, wy, button: e.button, px: e.offsetX, py: e.offsetY };
  });
  canvas.addEventListener("pointermove", (e) => {
    if (!down) return;
    if (down.button !== 0) { view.cx -= (e.offsetX - down.px) / view.k; view.cy += (e.offsetY - down.py) / view.k; down.px = e.offsetX; down.py = e.offsetY; draw(); return; }
    if (!active) return;
    const dx = e.offsetX - down.sx, dy = e.offsetY - down.sy;
    const mk = (marks[active.chunk] ??= {});
    mk[active.label] = { x: down.wx, y: down.wy, ...(Math.hypot(dx, dy) > 15 ? { heading: Math.atan2(-dy, dx) } : {}) };
    draw();
  });
  canvas.addEventListener("pointerup", (e) => {
    if (down && down.button === 0 && active) {
      const dx = e.offsetX - down.sx, dy = e.offsetY - down.sy;
      const mk = (marks[active.chunk] ??= {});
      mk[active.label] = { x: down.wx, y: down.wy, ...(Math.hypot(dx, dy) > 15 ? { heading: Math.atan2(-dy, dx) } : {}) };
      // go on to the next photo row automatically
      const keys = [...rows.keys()];
      const i = keys.indexOf(`${active.chunk}/${active.label}`);
      const next = keys.slice(i + 1).find((k) => (rows.get(k)!.parentElement as HTMLElement).style.display !== "none");
      if (next) { const [c, l] = next.split("/"); select(+c, l); } else refresh();
    }
    down = null;
  });
  canvas.addEventListener("wheel", (e) => {
    e.preventDefault();
    const [wx, wy] = toWorld(e.offsetX, e.offsetY);
    view.k *= e.deltaY < 0 ? 1.15 : 1 / 1.15;
    const [nx, ny] = toWorld(e.offsetX, e.offsetY);
    view.cx += wx - nx; view.cy += wy - ny; draw();
  }, { passive: false });
  addEventListener("resize", resize);

  $("save").onclick = async () => {
    const r = await fetch("/api/locate", { method: "POST", body: JSON.stringify(marks) });
    $("msg").textContent = r.ok ? "Saved. Tell Claude when you are done." : `Could not save (${r.status})`;
    localStorage.setItem("locate-marks", JSON.stringify(marks));
  };
  resize();
  refresh();
  const first = data.chunks.find((c) => c.check) ?? data.chunks[0];
  select(first.id, "start");
}

main().catch((e) => { document.body.textContent = `Could not start: ${e}. Run: python -m app.lidar.locate_data <chunks.json> <views dir>`; });
