// Splat cleanup: select Gaussians (box or brush, through the whole depth or only near the camera),
// delete them, undo/redo, and save. Works on the export's master PLY; saving sends a bitmask of the
// deleted Gaussians to the studio server, which writes a cleaned copy, rebuilds the web splat and the
// collision voxels, and keeps the original (see app/server/clean.py).

import "./clean.css";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { SparkRenderer, SplatFileType, SplatMesh } from "@sparkjsdev/spark";

type Tool = "orbit" | "rect" | "brush";
interface Info {
  count: number; source: string; source_bytes: number; samples: { i: number; xyz: [number, number, number] }[];
  has_mask: boolean; edits: { deleted: number } | null; name: string; project: string; export: string;
  transform?: { scale: number; quaternion_xyzw: [number, number, number, number]; position: [number, number, number] };
  start?: { position: [number, number, number]; yawDeg: number }; eye_height: number;
}
// Undo entries: "sel" flips the selected flag of these Gaussians; "del" deleted them (and unselected them).
type Op = { kind: "sel" | "del"; idx: Uint32Array };

const SEL = 1, DEL = 2;
const TINT = [255, 128, 24];
const $ = <T extends HTMLElement = HTMLElement>(id: string) => document.getElementById(id) as T;
const qs = new URLSearchParams(location.search);
const project = qs.get("project") ?? "", exportRel = qs.get("export") ?? "";
const API = "/studio-api";
const target = `project=${encodeURIComponent(project)}&export=${encodeURIComponent(exportRel)}`;

function toast(html: string, err = false, ms = 3500): void {
  const t = $("toast");
  t.innerHTML = html;
  t.className = `show${err ? " err" : ""}`;
  clearTimeout((toast as unknown as { h?: number }).h);
  if (ms) (toast as unknown as { h?: number }).h = window.setTimeout(() => (t.className = ""), ms);
}

async function getJson<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, { cache: "no-store", ...init });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error ?? `HTTP ${r.status}`);
  return data as T;
}

async function main(): Promise<void> {
  const info = await getJson<Info>(`${API}/clean/info?${target}`);
  document.title = `Cleanup – ${info.name}`;
  $("title").textContent = info.name;

  const canvas = $<HTMLCanvasElement>("view");
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: false });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5));
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0d0e11);
  const camera = new THREE.PerspectiveCamera(60, 1, 0.02, 1000);
  camera.up.set(0, 0, 1);
  const spark = new SparkRenderer({ renderer });
  scene.add(spark);

  const lmsg = $("lmsg"), lprog = $("lprog");
  lmsg.textContent = `Loading ${info.name}: ${(info.count / 1e6).toFixed(2)} M Gaussians (${Math.round(info.source_bytes / 1e6)} MB)…`;
  const mesh = new SplatMesh({
    url: `${API}/clean/source.ply?${target}`,
    fileType: SplatFileType.PLY,
    onProgress: (e: ProgressEvent) => {
      const total = e.total || info.source_bytes;
      lprog.style.width = `${Math.min(100, (100 * e.loaded) / total)}%`;
    },
  });
  if (info.transform) {
    mesh.quaternion.set(...info.transform.quaternion_xyzw);
    mesh.scale.setScalar(info.transform.scale);
    mesh.position.set(...info.transform.position);
  }
  scene.add(mesh);
  await mesh.initialized;
  lmsg.textContent = "Preparing…";
  await new Promise((r) => setTimeout(r, 30));

  const packed = mesh.packedSplats!;
  const N = packed.numSplats;
  if (N !== info.count) throw new Error(`the viewer loaded ${N} Gaussians, the file has ${info.count}`);
  const words = packed.packedArray!;
  // Spark keeps the file order; check a few centres anyway (stored as 16-bit floats, so loosely).
  for (const s of info.samples) {
    const c = packed.getSplat(s.i).center;
    const tol = (v: number) => 0.01 + Math.abs(v) * 2e-3;
    if (Math.abs(c.x - s.xyz[0]) > tol(s.xyz[0]) || Math.abs(c.y - s.xyz[1]) > tol(s.xyz[1]) || Math.abs(c.z - s.xyz[2]) > tol(s.xyz[2]))
      throw new Error(`Gaussian ${s.i} is not where the file has it: the order does not match, so saving is unsafe`);
  }

  // World-space centres (for selection), original colour words, and per-Gaussian flags.
  mesh.updateMatrixWorld(true);
  const pos = new Float32Array(N * 3);
  const mw = mesh.matrixWorld.elements;
  mesh.forEachSplat((i, c) => {
    pos[i * 3] = mw[0] * c.x + mw[4] * c.y + mw[8] * c.z + mw[12];
    pos[i * 3 + 1] = mw[1] * c.x + mw[5] * c.y + mw[9] * c.z + mw[13];
    pos[i * 3 + 2] = mw[2] * c.x + mw[6] * c.y + mw[10] * c.z + mw[14];
  });
  const orig = new Uint32Array(N);
  for (let i = 0; i < N; i++) orig[i] = words[i * 4];
  const flags = new Uint8Array(N);
  let dirty = false;

  const paint = (i: number) => {
    const f = flags[i], w = orig[i];
    if (f & DEL) words[i * 4] = w & 0x00ffffff; // alpha 0: hidden
    else if (f & SEL) {
      const r = w & 255, g = (w >>> 8) & 255, b = (w >>> 16) & 255;
      const mix = (a: number, t: number) => Math.round(a * 0.35 + t * 0.65);
      words[i * 4] = (mix(r, TINT[0]) | (mix(g, TINT[1]) << 8) | (mix(b, TINT[2]) << 16) | (w & 0xff000000)) >>> 0;
    } else words[i * 4] = w;
  };
  const touch = () => (dirty = true);

  // Earlier saved cleanup: start from it (not undoable here; "Restore original" brings everything back).
  let baseDeleted = 0;
  if (info.has_mask) {
    const bits = new Uint8Array(await (await fetch(`${API}/clean/mask.bin?${target}`, { cache: "no-store" })).arrayBuffer());
    for (let i = 0; i < N; i++) if (bits[i >> 3] & (1 << (i & 7))) (flags[i] = DEL, paint(i), baseDeleted++);
    touch();
    $("reset").hidden = false;
  }

  // ------------------------------------------------------------------ camera

  const controls = new OrbitControls(camera, canvas);
  controls.enableDamping = true;
  controls.dampingFactor = 0.12;
  controls.screenSpacePanning = true;
  // Bulk of the splat (2nd-98th percentile of the centres): far-away background Gaussians do not count.
  const sample = Math.max(1, Math.floor(N / 50000));
  const axis = (k: number) => {
    const v: number[] = [];
    for (let i = 0; i < N; i += sample) v.push(pos[i * 3 + k]);
    v.sort((a, b) => a - b);
    return [v[Math.floor(v.length * 0.02)], v[Math.floor(v.length * 0.98)]];
  };
  const [x0, x1] = axis(0), [y0, y1] = axis(1), [z0, z1] = axis(2);
  const centre = new THREE.Vector3((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2);
  const size = Math.max(x1 - x0, y1 - y0, z1 - z0);
  camera.near = Math.max(0.01, size / 3000);
  camera.far = size * 20;
  $<HTMLInputElement>("depth").max = String(Math.max(2, Math.ceil(size * 1.2)));
  const overview = () => {
    controls.target.copy(centre);
    camera.position.copy(centre).add(new THREE.Vector3(0.7, -0.9, 0.8).normalize().multiplyScalar(size * 0.95));
    controls.update();
  };
  const startView = () => {
    // Where the explorer starts, at eye height, looking the same way; orbit around a point just ahead.
    if (!info.start) return overview();
    const [sx, sy, sz] = info.start.position;
    const yaw = (info.start.yawDeg * Math.PI) / 180;
    camera.position.set(sx, sy, sz + info.eye_height);
    controls.target.set(sx + 1.5 * Math.cos(yaw), sy + 1.5 * Math.sin(yaw), sz + info.eye_height - 0.15);
    controls.update();
  };
  startView();
  $("view-start").addEventListener("click", startView);
  $("view-over").addEventListener("click", overview);

  // Fly with WASD (Q/E down/up, Shift faster): moves the camera and its pivot together.
  const keys = new Set<string>();
  addEventListener("keydown", (e) => !(e.ctrlKey || e.metaKey) && !(e.target as HTMLElement).closest("input") && keys.add(e.code));
  addEventListener("keyup", (e) => keys.delete(e.code));
  addEventListener("blur", () => keys.clear());
  const flySpeed = Math.min(3, Math.max(0.6, size * 0.08));
  const fly = (dt: number) => {
    const f = new THREE.Vector3(), r = new THREE.Vector3(), up = new THREE.Vector3(0, 0, 1);
    camera.getWorldDirection(f);
    r.crossVectors(f, up).normalize();
    const move = new THREE.Vector3();
    if (keys.has("KeyW")) move.add(f);
    if (keys.has("KeyS")) move.sub(f);
    if (keys.has("KeyD")) move.add(r);
    if (keys.has("KeyA")) move.sub(r);
    if (keys.has("KeyE")) move.add(up);
    if (keys.has("KeyQ")) move.sub(up);
    if (!move.lengthSq()) return;
    move.normalize().multiplyScalar(flySpeed * dt * (keys.has("ShiftLeft") || keys.has("ShiftRight") ? 3 : 1));
    camera.position.add(move);
    controls.target.add(move);
  };
  canvas.addEventListener("dblclick", (e) => {
    // Pivot on the splat surface under the cursor.
    const ray = new THREE.Raycaster();
    ray.setFromCamera(new THREE.Vector2((e.clientX / innerWidth) * 2 - 1, -(e.clientY / innerHeight) * 2 + 1), camera);
    const hit = ray.intersectObject(mesh, false)[0];
    if (hit) (controls.target.copy(hit.point), toast("Pivot set", false, 1200));
  });

  // ------------------------------------------------------------------ tools and options

  let tool: Tool = "rect";
  let brushPx = +(localStorage.getItem("clean.brush") ?? 40);
  let depthOn = false;
  let depthMax = 3;
  const setTool = (t: Tool) => {
    tool = t;
    document.querySelectorAll<HTMLElement>("[data-tool]").forEach((b) => b.classList.toggle("on", b.dataset.tool === t));
    // Left button selects in the select tools; the right button always orbits, the middle one pans.
    controls.mouseButtons = t === "orbit"
      ? { LEFT: THREE.MOUSE.ROTATE, MIDDLE: THREE.MOUSE.DOLLY, RIGHT: THREE.MOUSE.PAN }
      : { LEFT: null as unknown as THREE.MOUSE, MIDDLE: THREE.MOUSE.PAN, RIGHT: THREE.MOUSE.ROTATE };
    $("opt-brush").style.display = t === "brush" ? "" : "none";
    $("brush").style.display = "none";
    canvas.style.cursor = t === "orbit" ? "grab" : "crosshair";
    const move = "<kbd>W</kbd><kbd>A</kbd><kbd>S</kbd><kbd>D</kbd> fly · <kbd>Q</kbd>/<kbd>E</kbd> down/up";
    $("help").innerHTML = t === "orbit"
      ? `Left-drag: turn · right-drag: pan · wheel: zoom · double-click: pivot here · ${move} · <kbd>R</kbd> box · <kbd>B</kbd> brush`
      : `Left-drag: ${t === "rect" ? "box" : "paint"} select (<kbd>Shift</kbd> add · <kbd>Ctrl</kbd> remove) · right-drag: turn ·
         wheel: zoom · ${move} · <kbd>Del</kbd> delete · <kbd>Ctrl</kbd>+<kbd>Z</kbd> undo${t === "brush" ? " · <kbd>[</kbd> <kbd>]</kbd> size" : ""}`;
  };
  document.querySelectorAll<HTMLElement>("[data-tool]").forEach((b) => b.addEventListener("click", () => setTool(b.dataset.tool as Tool)));
  const bsize = $<HTMLInputElement>("bsize"), depth = $<HTMLInputElement>("depth"), depthOnEl = $<HTMLInputElement>("depth-on");
  const syncOpts = () => {
    bsize.value = String(brushPx);
    $("bsize-v").textContent = `${brushPx} px`;
    depth.value = String(depthMax);
    depth.disabled = !depthOn;
    $("depth-v").textContent = depthOn ? `${depthMax.toFixed(1)} m` : "off";
  };
  bsize.addEventListener("input", () => {
    brushPx = +bsize.value;
    try { localStorage.setItem("clean.brush", String(brushPx)); } catch { /* ignore */ }
    syncOpts();
  });
  depthOnEl.addEventListener("change", () => ((depthOn = depthOnEl.checked), syncOpts()));
  depth.addEventListener("input", () => ((depthMax = +depth.value), syncOpts()));
  syncOpts();
  setTool("rect");

  // ------------------------------------------------------------------ selection

  const undo: Op[] = [], redo: Op[] = [];
  const counts = () => {
    let s = 0, d = 0;
    for (let i = 0; i < N; i++) (flags[i] & SEL && s++, flags[i] & DEL && d++);
    return { s, d };
  };
  let nSel = 0, nDel = baseDeleted;
  const updateUi = () => {
    $("stats").innerHTML = `<b>${(N / 1e6).toFixed(2)} M</b> Gaussians · <b class="s">${nSel.toLocaleString("en")}</b> selected ·
      <b class="d">${nDel.toLocaleString("en")}</b> deleted${baseDeleted ? ` (${baseDeleted.toLocaleString("en")} saved before)` : ""}`;
    $<HTMLButtonElement>("del").disabled = nSel === 0;
    $<HTMLButtonElement>("undo").disabled = !undo.length;
    $<HTMLButtonElement>("redo").disabled = !redo.length;
    $<HTMLButtonElement>("save").disabled = nDel === baseDeleted && !undo.length;
  };
  const flip = (idx: Uint32Array, kind: "sel" | "del", forward: boolean) => {
    for (const i of idx) {
      if (kind === "sel") flags[i] ^= SEL;
      else flags[i] = forward ? DEL : SEL; // undoing a delete brings the Gaussians back, still selected
      paint(i);
    }
    touch();
  };
  const commit = (op: Op) => {
    if (!op.idx.length) return;
    undo.push(op);
    if (undo.length > 200) undo.shift();
    redo.length = 0;
    ({ s: nSel, d: nDel } = counts());
    updateUi();
  };
  const doUndo = () => {
    const op = undo.pop();
    if (!op) return;
    flip(op.idx, op.kind, false);
    redo.push(op);
    ({ s: nSel, d: nDel } = counts());
    updateUi();
  };
  const doRedo = () => {
    const op = redo.pop();
    if (!op) return;
    flip(op.idx, op.kind, true);
    undo.push(op);
    ({ s: nSel, d: nDel } = counts());
    updateUi();
  };
  const deleteSelected = () => {
    const idx: number[] = [];
    for (let i = 0; i < N; i++) if ((flags[i] & (SEL | DEL)) === SEL) (idx.push(i), (flags[i] = DEL), paint(i));
    touch();
    commit({ kind: "del", idx: Uint32Array.from(idx) });
    if (idx.length) toast(`${idx.length.toLocaleString("en")} Gaussians deleted · Ctrl+Z to undo`, false, 2200);
  };
  const selectWhere = (pick: (i: number) => boolean) => {
    const idx: number[] = [];
    for (let i = 0; i < N; i++) {
      if (flags[i] & DEL) continue;
      if (((flags[i] & SEL) !== 0) !== pick(i)) (idx.push(i), (flags[i] ^= SEL), paint(i));
    }
    touch();
    commit({ kind: "sel", idx: Uint32Array.from(idx) });
  };

  /** Screen positions of all visible Gaussians for the current camera (NaN = not selectable). */
  const screenPositions = () => {
    camera.updateMatrixWorld();
    const m = new THREE.Matrix4().multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse).elements;
    const W = innerWidth, H = innerHeight;
    const sx = new Float32Array(N), sy = new Float32Array(N);
    const lim = depthOn ? depthMax : Infinity;
    for (let i = 0; i < N; i++) {
      const x = pos[i * 3], y = pos[i * 3 + 1], z = pos[i * 3 + 2];
      const w = m[3] * x + m[7] * y + m[11] * z + m[15];
      if (w <= camera.near || w > lim || flags[i] & DEL) {
        sx[i] = NaN;
        continue;
      }
      sx[i] = ((m[0] * x + m[4] * y + m[8] * z + m[12]) / w + 1) * 0.5 * W;
      sy[i] = (1 - (m[1] * x + m[5] * y + m[9] * z + m[13]) / w) * 0.5 * H;
    }
    return { sx, sy };
  };

  // Box select.
  const rectEl = $("rect"), brushEl = $("brush");
  let drag: { x0: number; y0: number; mode: "set" | "add" | "sub" } | null = null;
  // Brush stroke: the camera is fixed during a stroke, so project once and bucket the points in a grid.
  let stroke: { cells: Int32Array; order: Int32Array; cols: number; rows: number; cell: number; sx: Float32Array; sy: Float32Array;
    mode: "add" | "sub"; idx: number[]; last: [number, number] | null } | null = null;

  const startStroke = (mode: "add" | "sub") => {
    const { sx, sy } = screenPositions();
    const cell = Math.max(8, brushPx);
    const cols = Math.ceil(innerWidth / cell) + 1, rows = Math.ceil(innerHeight / cell) + 1;
    const cellOf = new Int32Array(N);
    const starts = new Int32Array(cols * rows + 1);
    for (let i = 0; i < N; i++) {
      const x = sx[i], y = sy[i];
      if (!(x >= 0 && y >= 0 && x < innerWidth && y < innerHeight)) { cellOf[i] = -1; continue; }
      const c = Math.floor(y / cell) * cols + Math.floor(x / cell);
      cellOf[i] = c;
      starts[c + 1]++;
    }
    for (let c = 0; c < cols * rows; c++) starts[c + 1] += starts[c];
    const fill = starts.slice();
    const order = new Int32Array(starts[cols * rows]);
    for (let i = 0; i < N; i++) if (cellOf[i] >= 0) order[fill[cellOf[i]]++] = i;
    stroke = { cells: starts, order, cols, rows, cell, sx, sy, mode, idx: [], last: null };
  };
  const dab = (x: number, y: number) => {
    const s = stroke!;
    const r = brushPx / 2, r2 = r * r;
    const c0 = Math.max(0, Math.floor((x - r) / s.cell)), c1 = Math.min(s.cols - 1, Math.floor((x + r) / s.cell));
    const r0 = Math.max(0, Math.floor((y - r) / s.cell)), r1 = Math.min(s.rows - 1, Math.floor((y + r) / s.cell));
    const want = s.mode === "add";
    for (let row = r0; row <= r1; row++)
      for (let col = c0; col <= c1; col++) {
        const c = row * s.cols + col;
        for (let k = s.cells[c]; k < s.cells[c + 1]; k++) {
          const i = s.order[k];
          const dx = s.sx[i] - x, dy = s.sy[i] - y;
          if (dx * dx + dy * dy <= r2 && ((flags[i] & SEL) !== 0) !== want) {
            flags[i] ^= SEL;
            paint(i);
            s.idx.push(i);
          }
        }
      }
    touch();
  };
  const paintTo = (x: number, y: number) => {
    const s = stroke!;
    if (s.last) {
      const [lx, ly] = s.last;
      const steps = Math.ceil(Math.hypot(x - lx, y - ly) / Math.max(2, brushPx / 4));
      for (let k = 1; k <= steps; k++) dab(lx + ((x - lx) * k) / steps, ly + ((y - ly) * k) / steps);
    } else dab(x, y);
    s.last = [x, y];
  };

  canvas.addEventListener("pointerdown", (e) => {
    if (e.button !== 0 || tool === "orbit") return;
    canvas.setPointerCapture(e.pointerId);
    const sub = e.ctrlKey || e.metaKey || e.altKey;
    if (tool === "rect") {
      drag = { x0: e.clientX, y0: e.clientY, mode: sub ? "sub" : e.shiftKey ? "add" : "set" };
      rectEl.classList.toggle("sub", sub);
    } else {
      startStroke(sub ? "sub" : "add");
      brushEl.classList.toggle("sub", sub);
      paintTo(e.clientX, e.clientY);
    }
  });
  canvas.addEventListener("pointermove", (e) => {
    if (tool === "brush") {
      Object.assign(brushEl.style, { display: "block", left: `${e.clientX - brushPx / 2}px`, top: `${e.clientY - brushPx / 2}px`,
        width: `${brushPx}px`, height: `${brushPx}px` });
      if (stroke) paintTo(e.clientX, e.clientY);
    }
    if (drag) {
      const x = Math.min(drag.x0, e.clientX), y = Math.min(drag.y0, e.clientY);
      Object.assign(rectEl.style, { display: "block", left: `${x}px`, top: `${y}px`,
        width: `${Math.abs(e.clientX - drag.x0)}px`, height: `${Math.abs(e.clientY - drag.y0)}px` });
    }
  });
  canvas.addEventListener("pointerleave", () => (brushEl.style.display = "none"));
  canvas.addEventListener("pointerup", (e) => {
    if (drag) {
      const d = drag;
      drag = null;
      rectEl.style.display = "none";
      const x0 = Math.min(d.x0, e.clientX), x1 = Math.max(d.x0, e.clientX);
      const y0 = Math.min(d.y0, e.clientY), y1 = Math.max(d.y0, e.clientY);
      if (x1 - x0 < 3 && y1 - y0 < 3) {
        if (d.mode === "set") selectWhere(() => false); // a plain click clears the selection
        return;
      }
      const { sx, sy } = screenPositions();
      const inside = (i: number) => sx[i] >= x0 && sx[i] <= x1 && sy[i] >= y0 && sy[i] <= y1;
      selectWhere((i) => d.mode === "set" ? inside(i) : d.mode === "add" ? (flags[i] & SEL) !== 0 || inside(i)
        : (flags[i] & SEL) !== 0 && !inside(i));
    }
    if (stroke) {
      const s = stroke;
      stroke = null;
      commit({ kind: "sel", idx: Uint32Array.from(s.idx) });
    }
  });

  $("del").addEventListener("click", deleteSelected);
  $("undo").addEventListener("click", doUndo);
  $("redo").addEventListener("click", doRedo);
  $("none").addEventListener("click", () => selectWhere(() => false));
  $("invert").addEventListener("click", () => selectWhere((i) => (flags[i] & SEL) === 0));

  addEventListener("keydown", (e) => {
    if ((e.target as HTMLElement).closest("input")) return;
    const k = e.key.toLowerCase(), mod = e.ctrlKey || e.metaKey;
    if (mod && k === "z" && !e.shiftKey) (e.preventDefault(), doUndo());
    else if (mod && (k === "y" || (k === "z" && e.shiftKey))) (e.preventDefault(), doRedo());
    else if (mod && k === "s") (e.preventDefault(), void save());
    else if (mod && k === "i") (e.preventDefault(), selectWhere((i) => (flags[i] & SEL) === 0));
    else if (mod && k === "a") (e.preventDefault(), selectWhere(() => true));
    else if (k === "delete" || k === "backspace") (e.preventDefault(), deleteSelected());
    else if (k === "escape") selectWhere(() => false);
    else if (!mod && k === "f") overview();
    else if (k === "home") startView();
    else if (!mod && k === "o") setTool("orbit");
    else if (!mod && k === "r") setTool("rect");
    else if (!mod && k === "b") setTool("brush");
    else if (k === "[" || k === "]") {
      brushPx = Math.max(6, Math.min(200, Math.round(brushPx * (k === "]" ? 1.2 : 1 / 1.2))));
      syncOpts();
    }
  });

  // ------------------------------------------------------------------ save

  let saving = false;
  const save = async () => {
    if (saving || $<HTMLButtonElement>("save").disabled) return;
    saving = true;
    $<HTMLButtonElement>("save").disabled = true;
    try {
      const bits = new Uint8Array((N + 7) >> 3);
      for (let i = 0; i < N; i++) if (flags[i] & DEL) bits[i >> 3] |= 1 << (i & 7);
      const res = await getJson<{ deleted: number; count: number; job: string }>(`${API}/clean/apply?${target}`,
        { method: "POST", body: new Blob([bits]) });
      toast(`Applying: removing ${res.deleted.toLocaleString("en")} Gaussians, rebuilding the web splat and collision…`, false, 0);
      const job = await waitJob(res.job);
      if (job.status !== "done") throw new Error(`the cleanup job ${job.status}; see the studio's job log`);
      undo.length = redo.length = 0;
      baseDeleted = nDel;
      $("reset").hidden = false;
      toast(`Saved: ${res.deleted.toLocaleString("en")} Gaussians removed. <a href="/" target="_blank">Walk through it ↗</a>`, false, 8000);
    } catch (e) {
      toast(`Could not save: ${(e as Error).message}`, true, 8000);
    } finally {
      saving = false;
      updateUi();
    }
  };
  $("save").addEventListener("click", () => void save());
  $("reset").addEventListener("click", async () => {
    if (!confirm("Bring back every deleted Gaussian (all saved cleanup of this splat)?")) return;
    const res = await getJson<{ job: string }>(`${API}/clean/reset?${target}`, { method: "POST" });
    toast("Restoring the original…", false, 0);
    const job = await waitJob(res.job);
    if (job.status === "done") location.reload();
    else toast("Restoring failed; see the studio's job log", true, 8000);
  });
  addEventListener("beforeunload", (e) => {
    if (undo.length && !saving) e.preventDefault();
  });

  // ------------------------------------------------------------------ loop

  const resize = () => {
    renderer.setSize(innerWidth, innerHeight, false);
    camera.aspect = innerWidth / innerHeight;
    camera.updateProjectionMatrix();
  };
  addEventListener("resize", resize);
  resize();
  updateUi();
  $("loading").classList.add("done");
  (window as unknown as { __clean: unknown }).__clean = { camera, controls, flags, N, selectWhere, deleteSelected, doUndo, doRedo,
    counts, pos, setTool, screenPositions };
  let last = performance.now();
  renderer.setAnimationLoop((now) => {
    fly(Math.min(0.1, (now - last) / 1000));
    last = now;
    controls.update();
    if (dirty) {
      dirty = false;
      packed.needsUpdate = true;
      mesh.needsUpdate = true;
    }
    renderer.render(scene, camera);
  });
}

async function waitJob(id: string): Promise<{ status: string }> {
  for (;;) {
    const j = await getJson<{ status: string }>(`${API}/jobs/${id}`);
    if (!["queued", "running", "paused"].includes(j.status)) return j;
    await new Promise((r) => setTimeout(r, 1000));
  }
}

main().catch((e) => {
  $("lmsg").textContent = `Could not open the cleanup: ${(e as Error).message ?? e}`;
  $("lprog").style.background = "var(--bad)";
  console.error(e);
});
