// Hand alignment of an SfM piece to the LiDAR floor plan (2D): the user drags the piece (camera path + points) over
// the plan; yaw, scale, shift and a mirror (flip up/down) are saved to /api/align/<name>.

export {}; // a module of its own: the other pages declare the same helper names

interface Plan { url: string; x0: number; x1: number; y0: number; y1: number; res: number }
interface Data {
  name: string; plan: Plan; cams: number[][]; pts: number[][]; room_height: number; model: string;
  init: { yaw: number; scale: number; tx: number; ty: number; mirror: boolean }; init_up: number;
}
interface T { yaw: number; scale: number; tx: number; ty: number; mirror: boolean }

const $ = <E extends HTMLElement>(id: string) => document.getElementById(id) as E;
const canvas = $<HTMLCanvasElement>("view");
const ctx = canvas.getContext("2d")!;
const pieceName = new URLSearchParams(location.search).get("piece") ?? "m1";

async function main() {
  const data: Data = await (await fetch(`/align/${pieceName}.json?${Date.now()}`)).json();
  $("name").textContent = `Piece ${pieceName} (${data.cams.length} cameras)`;
  const plan = new Image();
  plan.src = `/align/${data.plan.url}`;
  await plan.decode();
  // plan pixels for the live score: 50 = floor, 200 = wall/furniture
  const off = document.createElement("canvas");
  off.width = plan.width; off.height = plan.height;
  const octx = off.getContext("2d", { willReadFrequently: true })!;
  octx.drawImage(plan, 0, 0);
  const px = octx.getImageData(0, 0, plan.width, plan.height).data;

  const P = data.plan;
  let t: T = { ...data.init };
  let showPts = true;
  // view: metres -> screen
  const view = { cx: (P.x0 + P.x1) / 2, cy: (P.y0 + P.y1) / 2, k: 12 };
  let fitted = false;
  const resize = () => {
    canvas.width = innerWidth;
    canvas.height = innerHeight;
    if (!fitted) { // first time: fit the whole plan into the free part of the window (left of the panel)
      fitted = true;
      view.k = 0.96 * Math.min((innerWidth - 340) / (P.x1 - P.x0), innerHeight / (P.y1 - P.y0));
      view.cx -= 150 / view.k;
    }
    draw();
  };
  const toScreen = (x: number, y: number): [number, number] => [canvas.width / 2 + (x - view.cx) * view.k, canvas.height / 2 - (y - view.cy) * view.k];
  const toWorld = (sx: number, sy: number): [number, number] => [view.cx + (sx - canvas.width / 2) / view.k, view.cy - (sy - canvas.height / 2) / view.k];
  const place = (x: number, y: number): [number, number] => {
    const yy = t.mirror ? -y : x * 0 + y;
    const a = (t.yaw * Math.PI) / 180, c = Math.cos(a), s = Math.sin(a);
    return [t.scale * (c * x - s * yy) + t.tx, t.scale * (s * x + c * yy) + t.ty];
  };
  const planAt = (x: number, y: number): number => {
    const ix = Math.floor((x - P.x0) / P.res), iy = plan.height - 1 - Math.floor((y - P.y0) / P.res);
    if (ix < 0 || iy < 0 || ix >= plan.width || iy >= plan.height) return 0;
    return px[(iy * plan.width + ix) * 4];
  };

  function score() {
    let floor = 0, wall = 0, out = 0;
    for (const c of data.cams) {
      const [x, y] = place(c[0], c[1]);
      const v = planAt(x, y);
      if (v === 0) out++; else if (v > 150) wall++; else if (v > 30) floor++;
    }
    const n = data.cams.length;
    $("score").innerHTML = `Cameras over floor: <b>${((floor / n) * 100).toFixed(0)}%</b><br>in walls/furniture: ${((wall / n) * 100).toFixed(0)}% · outside the scan: ${((out / n) * 100).toFixed(0)}%`;
  }

  function draw() {
    ctx.fillStyle = "#101114";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    const [sx0, sy0] = toScreen(P.x0, P.y1);
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(plan, sx0, sy0, (P.x1 - P.x0) * view.k, (P.y1 - P.y0) * view.k);
    if (showPts) {
      ctx.fillStyle = "rgba(255,70,70,0.55)";
      for (let i = 0; i < data.pts.length; i += 2) {
        const [x, y] = place(data.pts[i][0], data.pts[i][1]);
        const [sx, sy] = toScreen(x, y);
        ctx.fillRect(sx - 1, sy - 1, 2, 2);
      }
    }
    ctx.fillStyle = "rgb(80,255,100)";
    for (const c of data.cams) {
      const [x, y] = place(c[0], c[1]);
      const [sx, sy] = toScreen(x, y);
      ctx.beginPath(); ctx.arc(sx, sy, 2.4, 0, Math.PI * 2); ctx.fill();
    }
    score();
    for (const [id, v] of [["yaw", t.yaw], ["scale", t.scale], ["tx", t.tx], ["ty", t.ty]] as const) {
      $<HTMLInputElement>(id).value = String(v);
      $<HTMLInputElement>(id + "n").value = Number(v).toFixed(id === "scale" ? 3 : 2);
    }
  }

  // sliders / numbers
  for (const id of ["yaw", "scale", "tx", "ty"] as const) {
    const r = $<HTMLInputElement>(id), n = $<HTMLInputElement>(id + "n");
    if (id === "tx") { r.min = String(P.x0 - 10); r.max = String(P.x1 + 10); }
    if (id === "ty") { r.min = String(P.y0 - 10); r.max = String(P.y1 + 10); }
    const set = (v: number) => { (t as unknown as Record<string, number>)[id] = v; draw(); };
    r.addEventListener("input", () => set(parseFloat(r.value)));
    n.addEventListener("change", () => set(parseFloat(n.value)));
  }
  $("mirror").onclick = () => { t.mirror = !t.mirror; draw(); };
  $("points").onclick = () => { showPts = !showPts; $("points").textContent = showPts ? "Hide points" : "Show points"; draw(); };
  $("reset").onclick = () => { t = { ...data.init }; draw(); };
  $("save").onclick = async () => {
    const r = await fetch(`/api/align/${pieceName}`, { method: "POST", body: JSON.stringify({ ...t, up: data.init_up, room_height: data.room_height }) });
    $("msg").textContent = r.ok ? "Saved. Tell Claude the alignment is done." : `Could not save (${r.status})`;
  };

  // mouse: drag = move the piece, right/middle drag = pan, wheel = zoom
  let drag: { x: number; y: number; mode: "piece" | "pan" } | null = null;
  canvas.addEventListener("contextmenu", (e) => e.preventDefault());
  canvas.addEventListener("pointerdown", (e) => {
    canvas.setPointerCapture(e.pointerId);
    drag = { x: e.clientX, y: e.clientY, mode: e.button === 0 ? "piece" : "pan" };
    canvas.classList.toggle("moving", drag.mode === "piece");
  });
  canvas.addEventListener("pointermove", (e) => {
    if (!drag) return;
    const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    drag.x = e.clientX; drag.y = e.clientY;
    if (drag.mode === "piece") { t.tx += dx / view.k; t.ty -= dy / view.k; }
    else { view.cx -= dx / view.k; view.cy += dy / view.k; }
    draw();
  });
  canvas.addEventListener("pointerup", () => { drag = null; canvas.classList.remove("moving"); });
  canvas.addEventListener("wheel", (e) => {
    e.preventDefault();
    const [wx, wy] = toWorld(e.clientX, e.clientY);
    view.k *= e.deltaY < 0 ? 1.15 : 1 / 1.15;
    const [nx, ny] = toWorld(e.clientX, e.clientY);
    view.cx += wx - nx; view.cy += wy - ny;
    draw();
  }, { passive: false });
  addEventListener("keydown", (e) => {
    if ((e.target as HTMLElement).tagName === "INPUT") return;
    const fine = e.shiftKey ? 0.2 : 1;
    if (e.code === "KeyQ") t.yaw += fine;
    else if (e.code === "KeyE") t.yaw -= fine;
    else if (e.code === "KeyZ") t.scale *= 1 - 0.01 * fine;
    else if (e.code === "KeyX") t.scale *= 1 + 0.01 * fine;
    else if (e.code === "KeyM") t.mirror = !t.mirror;
    else return;
    draw();
  });
  addEventListener("resize", resize);
  resize();
}

main().catch((e) => { document.body.textContent = `Could not start: ${e}. Run: python -m app.lidar.align_data <registration dir> <piece>`; });
