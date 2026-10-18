// Splat Studio: footage -> timeline (captures) -> settings and estimate -> jobs -> training monitor -> results.
// Talks to the local job server (python -m app serve) through /studio-api.

import "./studio.css";
import {
  api, esc, fmt, type Capture, type DirListing, type Estimate, type Job, type Project, type Settings, type Status,
  type TrainProgress,
} from "./api";
import { drawChart } from "./chart";
import { captureId, Timeline } from "./timeline";

const $ = <T extends HTMLElement = HTMLElement>(id: string) => document.getElementById(id) as T;
const FPS_PRESETS = [{ fps: 1, name: "Quick" }, { fps: 2.5, name: "Standard" }, { fps: 4, name: "Dense" }];
const CAPS = [500_000, 1_000_000, 2_000_000, 3_000_000];
const VIEWER_URL = "http://127.0.0.1:8080";

let status: Status | null = null;
let project: Project | null = null;
let caps: Capture[] = [];
let selected = "";
let settings: Settings = { fps: 2.5, cap: 1_000_000, steps: null, viewer: true, people: true };
let estimate: Estimate | null = null;
let jobs: Job[] = [];
const openLogs = new Set<string>();
let train: { job: Job; data: TrainProgress | null } | null = null;
let showLive = true;

function toast(msg: string, err = false): void {
  const t = $("toast");
  t.textContent = msg;
  t.className = `show${err ? " err" : ""}`;
  clearTimeout((toast as unknown as { h?: number }).h);
  (toast as unknown as { h?: number }).h = window.setTimeout(() => (t.className = ""), err ? 6000 : 2800);
}

async function guard<T>(p: Promise<T>): Promise<T | undefined> {
  try {
    return await p;
  } catch (e) {
    toast(String((e as Error).message ?? e), true);
    return undefined;
  }
}

const debounce = <A extends unknown[]>(fn: (...a: A) => void, ms: number) => {
  let h = 0;
  return (...a: A) => (clearTimeout(h), (h = window.setTimeout(() => fn(...a), ms)));
};

// ------------------------------------------------------------------ project

async function loadProjects(): Promise<void> {
  const list = await api<{ name: string; clips: number }[]>("GET", "/projects");
  const sel = $<HTMLSelectElement>("project");
  const want = localStorage.getItem("studio.project") ?? list[0]?.name;
  sel.innerHTML = list.map((p) => `<option ${p.name === want ? "selected" : ""}>${esc(p.name)}</option>`).join("") ||
    `<option value="">(no projects)</option>`;
  if (list.length) await loadProject(sel.value);
  else renderAll();
}

async function loadProject(name: string): Promise<void> {
  try {
    localStorage.setItem("studio.project", name);
  } catch { /* private mode */ }
  project = await api<Project>("GET", `/projects/${encodeURIComponent(name)}`);
  caps = project.captures.map((c) => ({ ...c, id: captureId(c) }));
  const s = project.settings;
  settings = { fps: s.fps ?? 2.5, cap: s.cap ?? 1_000_000, steps: null, viewer: s.viewer ?? true, people: s.people ?? true,
    max_features: s.max_features ?? 8192 };
  selected = caps.find((c) => c.id === s.capture_id)?.id ?? caps[0]?.id ?? "";
  renderAll();
  refreshEstimate();
}

$("project").addEventListener("change", (e) => void guard(loadProject((e.target as HTMLSelectElement).value)));
$("new-project").addEventListener("click", async () => {
  const name = prompt("Name of the new project (letters, digits, - and _):")?.trim();
  if (!name) return;
  if (await guard(api("POST", "/projects", { name }))) {
    localStorage.setItem("studio.project", name);
    await loadProjects();
    openFiles();
  }
});

const saveCaptures = debounce(async () => {
  if (!project) return;
  await guard(api("PUT", `/projects/${encodeURIComponent(project.name)}/captures`,
    { captures: caps, settings: { ...settings, capture_id: selected } }));
}, 400);

function capturesChanged(next: Capture[]): void {
  const prevSel = caps.find((c) => c.id === selected);
  caps = next.map((c) => ({ ...c, id: captureId(c) }));
  // Keep the selection on the capture that holds the previously selected clips.
  selected = caps.find((c) => prevSel && c.clips.some((x) => prevSel.clips[0]?.id === x.id))?.id ?? caps[0]?.id ?? "";
  if (project) project.suggested = false;
  renderFootage();
  renderSettings();
  saveCaptures();
  refreshEstimate();
}

// ------------------------------------------------------------------ 1. footage

const timeline = new Timeline({
  change: capturesChanged,
  select(id) {
    selected = id;
    renderFootage();
    renderSettings();
    saveCaptures();
    refreshEstimate();
  },
});

function renderFootage(): void {
  const el = $("footage");
  if (!project) {
    el.innerHTML = `<h2><span class="num">1</span>Footage</h2><p class="sub">Create a project to start.</p>`;
    return;
  }
  const clips = project.clips;
  el.innerHTML = `
    <h2><span class="num">1</span>Footage <span class="spacer"></span><button id="add-clips" class="primary small">Add clips…</button></h2>
    <p class="sub">Raw 360 clips from the camera (.insv). Frame rate, resolution and lens calibration are read from each file.</p>
    ${clips.length ? `<div class="clips">${clips.map((c) => `
      <div class="clip">
        <button class="rm" title="Remove from the project (the file stays on disk)" data-rm="${esc(c.id)}">×</button>
        <div class="name" title="${esc(c.path)}">${esc(c.name)}</div>
        <div class="meta">${esc(c.model ?? "unknown camera")} · ${c.width ? `${c.width}×${c.height} ×${c.lenses}` : "?"} ·
          ${c.fps ? `${c.fps.toFixed(2)} fps` : "?"}</div>
        <div class="meta">${c.duration ? fmt.clock(c.duration) : "?"} · ${c.size_bytes ? fmt.bytes(c.size_bytes) : ""} ·
          ${c.start ? fmt.time(c.start) : "no time stamp"}</div>
        ${c.problems.map((p) => `<div class="warn">⚠ ${esc(p)}</div>`).join("")}
      </div>`).join("")}</div>` : `<div class="empty">No clips yet. <a href="#" id="add-first">Add clips…</a></div>`}
    ${project.suggested && project.reasons.length ? `<div class="suggest"><div>🔗</div><div>${project.reasons.map((r) =>
      `<b>Combined into one capture:</b> ${esc(r.text)}`).join("<br>")}<br>
      <span class="muted">They will be solved and trained together as one splat. Not one recording? Split them below.</span></div></div>` : ""}
    <div id="tl"></div>`;
  el.querySelector("#add-clips")?.addEventListener("click", openFiles);
  el.querySelector("#add-first")?.addEventListener("click", (e) => (e.preventDefault(), openFiles()));
  el.querySelectorAll<HTMLElement>("[data-rm]").forEach((b) => b.addEventListener("click", async () => {
    if (!confirm(`Remove clip ${b.dataset.rm} from the project? The video file is not deleted.`)) return;
    await guard(api("DELETE", `/projects/${encodeURIComponent(project!.name)}/clips/${encodeURIComponent(b.dataset.rm!)}`));
    await loadProject(project!.name);
  }));
  if (clips.length) timeline.render(project, caps, selected, el.querySelector("#tl") as HTMLElement);
}

// ------------------------------------------------------------------ file browser

let fbPath: string | null = null;
const fbSel = new Set<string>();

function openFiles(): void {
  fbSel.clear();
  const d = $<HTMLDialogElement>("files");
  d.showModal();
  void browse(fbPath ?? localStorage.getItem("studio.lastdir"));
}

async function browse(path: string | null): Promise<void> {
  const d = $<HTMLDialogElement>("files");
  const res = await guard(api<DirListing>("GET", `/fs${path ? `?path=${encodeURIComponent(path)}` : ""}`));
  if (!res) return;
  fbPath = res.path;
  if (res.path) try { localStorage.setItem("studio.lastdir", res.path); } catch { /* ignore */ }
  const have = new Set(project?.clips.map((c) => c.path.toLowerCase()));
  d.innerHTML = `
    <div class="fb">
      <header><h3>Add clips</h3>
        <div class="path"><input type="text" id="fb-path" value="${esc(res.path ?? "")}" placeholder="Folder path, e.g. D:\\DCIM\\Camera01">
          <button id="fb-go">Go</button></div></header>
      <ul>
        ${res.path !== null ? `<li data-dir="${esc(res.parent ?? "")}"><span class="ic">↑</span>${res.parent ? "Up" : "This PC"}</li>` : ""}
        ${res.dirs.map((x) => `<li data-dir="${esc(x.path)}"><span class="ic">📁</span>${esc(x.name)}</li>`).join("")}
        ${res.files.map((f) => `<li data-file="${esc(f.path)}" class="${fbSel.has(f.path) ? "sel" : ""}">
          <span class="ic">${have.has(f.path.toLowerCase()) ? "✓" : "🎞"}</span>${esc(f.name)}
          <span class="sz">${fmt.bytes(f.size)} · ${fmt.time(f.mtime)}</span></li>`).join("")}
        ${res.path && !res.dirs.length && !res.files.length ? `<li class="muted">No folders or video files here.</li>` : ""}
      </ul>
      <footer><span class="muted">Select one or more .insv files. Both clips of a battery swap can be added together.</span>
        <button id="fb-cancel">Cancel</button><button id="fb-add" class="primary" ${fbSel.size ? "" : "disabled"}>
          Add ${fbSel.size || ""} clip${fbSel.size === 1 ? "" : "s"}</button></footer>
    </div>`;
  d.querySelectorAll<HTMLElement>("[data-dir]").forEach((li) => li.addEventListener("click", () => void browse(li.dataset.dir || null)));
  d.querySelectorAll<HTMLElement>("[data-file]").forEach((li) => li.addEventListener("click", () => {
    const f = li.dataset.file!;
    if (have.has(f.toLowerCase())) return toast("Already in the project");
    fbSel.has(f) ? fbSel.delete(f) : fbSel.add(f);
    li.classList.toggle("sel", fbSel.has(f));
    const add = d.querySelector("#fb-add") as HTMLButtonElement;
    add.disabled = !fbSel.size;
    add.textContent = `Add ${fbSel.size || ""} clip${fbSel.size === 1 ? "" : "s"}`;
  }));
  const go = () => void browse((d.querySelector("#fb-path") as HTMLInputElement).value.trim() || null);
  d.querySelector("#fb-go")!.addEventListener("click", go);
  d.querySelector("#fb-path")!.addEventListener("keydown", (e) => (e as KeyboardEvent).key === "Enter" && go());
  d.querySelector("#fb-cancel")!.addEventListener("click", () => d.close());
  d.querySelector("#fb-add")!.addEventListener("click", async () => {
    const btn = d.querySelector("#fb-add") as HTMLButtonElement;
    btn.disabled = true;
    let n = 0;
    for (const path of fbSel) {
      btn.textContent = `Reading ${++n}/${fbSel.size}…`;
      await guard(api("POST", `/projects/${encodeURIComponent(project!.name)}/clips`, { path }));
    }
    d.close();
    await loadProject(project!.name);
    toast(`${fbSel.size} clip${fbSel.size === 1 ? "" : "s"} added`);
  });
}

// ------------------------------------------------------------------ 2. settings and estimate

const refreshEstimate = debounce(async () => {
  const cap = caps.find((c) => c.id === selected);
  if (!project || !cap) {
    estimate = null;
    return renderSettings();
  }
  estimate = (await guard(api<Estimate>("POST", `/projects/${encodeURIComponent(project.name)}/estimate`,
    { capture: cap, settings }))) ?? null;
  renderSettings();
}, 200);

function renderSettings(): void {
  const el = $("settings");
  const cap = caps.find((c) => c.id === selected);
  if (!project || !cap) {
    el.innerHTML = `<h2><span class="num">2</span>Frames, quality and time</h2><p class="sub">Add footage first.</p>`;
    return;
  }
  const e = estimate;
  const vram = status?.gpu.vram_mb ?? 0;
  const capWarn = (c: number) => vram && c > (vram >= 16000 ? 6e6 : vram >= 10000 ? 3e6 : 1.5e6);
  const busy = jobs.some((j) => ["running", "paused", "queued"].includes(j.status) && j.project === project!.name);
  const spacing = 1 / settings.fps;
  el.innerHTML = `
    <h2><span class="num">2</span>Frames, quality and time</h2>
    <p class="sub">For capture <b>${esc(cap.name)}</b>. Estimates use this PC's measured speeds where it has them.</p>
    <div class="settings">
      <div>
        <div class="field">
          <div class="lbl">Frames per second of video <span>${settings.fps.toFixed(1)} fps · one 360 frame every ${spacing.toFixed(2)} s
            (≈ ${(spacing * 1.0).toFixed(1)} m at walking pace)</span></div>
          <input type="range" id="fps" min="0.5" max="5" step="0.1" value="${settings.fps}">
          <div class="row" style="margin-top:6px"><div class="seg">${FPS_PRESETS.map((p) =>
            `<button data-fps="${p.fps}" class="${Math.abs(settings.fps - p.fps) < 0.01 ? "on" : ""}">${p.name} · ${p.fps} fps</button>`).join("")}</div></div>
          <div class="help">The sharpest frame in each time window is kept, and still moments are skipped. Each 360 frame gives
            10 camera views. More frames: more overlap for the camera solve, but a longer solve and more disk space.</div>
        </div>
        <div class="field">
          <div class="lbl">Splat size (most Gaussians) <span>more = finer detail, more VRAM</span></div>
          <div class="seg">${CAPS.map((c) => `<button data-cap="${c}" class="${settings.cap === c ? "on" : ""}" ${capWarn(c) ? `title="May not fit in ${Math.round(vram / 1024)} GB VRAM"` : ""}>
            ${c / 1e6} M${capWarn(c) ? " ⚠" : ""}</button>`).join("")}</div>
        </div>
        <div class="field">
          <div class="lbl">Training steps <span>${e ? `${e.looks_per_image}× each image` : ""}</span></div>
          <div class="row">
            <label class="check"><input type="checkbox" id="auto-steps" ${settings.steps == null ? "checked" : ""}> Recommended
              ${e ? `(${fmt.num(e.recommended_steps)})` : ""}</label>
            <input type="number" id="steps" min="1000" step="1000" value="${settings.steps ?? e?.recommended_steps ?? 30000}"
              ${settings.steps == null ? "disabled" : ""} style="width:110px">
          </div>
        </div>
        <div class="field">
          <label class="check"><input type="checkbox" id="people" ${settings.people ? "checked" : ""}> Remove the camera operator and
            people walking by</label>
          <div class="help">Finds people in every view. They are left out of the camera solve; the operator and anyone moving
            is left out of the splat, people standing or sitting still stay.</div>
        </div>
        <div class="field">
          <div class="lbl">Features per view (camera solve) <span>fewer = less GPU memory</span></div>
          <div class="seg">${[8192, 4096].map((n) => `<button data-feat="${n}" class="${(settings.max_features ?? 8192) === n ? "on" : ""}">
            ${n}${n === 8192 ? " (default)" : " (8 GB GPUs)"}</button>`).join("")}</div>
        </div>
        <div class="field">
          <label class="check"><input type="checkbox" id="viewer" ${settings.viewer ? "checked" : ""}> Live 3D view while training
            <span class="faint">(gsplat viewer, slightly slower training)</span></label>
        </div>
      </div>
      <div class="est">
        ${e ? `
        <div class="big">
          <div><b>${fmt.num(e.frames)}</b><span>360 frames</span></div>
          <div><b>${fmt.num(e.images)}</b><span>camera views</span></div>
          <div><b>${fmt.bytes(e.disk_bytes)}</b><span>disk space</span></div>
        </div>
        <table class="stages">
          ${e.stages.map((s) => `<tr class="${s.uptodate ? "done" : ""}"><td>${esc(s.label)}${s.uptodate ? " <span class='src'>already done</span>" :
            `<span class="src ${s.source}">${s.source}</span>`}${s.detail ? `<br><span class="faint">${esc(s.detail)}</span>` : ""}</td>
            <td class="t">${s.uptodate ? "–" : fmt.dur(s.seconds)}</td></tr>`).join("")}
          <tr class="total"><td>Total on ${esc(e.gpu.name.replace("NVIDIA GeForce ", ""))}</td><td class="t">${fmt.dur(e.total_seconds)}</td></tr>
        </table>
        <div class="note"><span class="src measured">measured</span> from earlier runs on this PC ·
          <span class="src benchmark">benchmark</span> from the GPU test · <span class="src">default</span> from the reference PC.
          ${e.has_bench ? "" : "<br>Training speed is not measured on this PC yet."}
          <button class="small ghost" id="bench" ${busy ? "disabled" : ""}>${e.has_bench ? "Re-measure this PC" : "Measure this PC (1 min)"}</button></div>`
        : `<div class="muted">Estimating…</div>`}
      </div>
    </div>
    <div class="runrow">
      <button class="primary" id="run" ${!e || busy ? "disabled" : ""}>Build the splat</button>
      <label class="muted">or redo from <select id="from"><option value="">(only what changed)</option>
        <option value="frames">frames</option><option value="views">views</option><option value="people">people</option><option value="sfm">camera solve</option>
        <option value="train">training</option></select></label>
      ${busy ? `<span class="muted">A job is running for this project.</span>` : ""}
    </div>`;
  const set = (patch: Partial<Settings>) => {
    settings = { ...settings, ...patch };
    saveCaptures();
    refreshEstimate();
  };
  const fps = el.querySelector("#fps") as HTMLInputElement;
  fps.addEventListener("input", () => {
    settings.fps = +fps.value;
    (el.querySelector(".field .lbl span") as HTMLElement).textContent =
      `${settings.fps.toFixed(1)} fps · one 360 frame every ${(1 / settings.fps).toFixed(2)} s (≈ ${(1 / settings.fps).toFixed(1)} m at walking pace)`;
    refreshEstimate();
  });
  fps.addEventListener("change", () => set({ fps: +fps.value }));
  el.querySelectorAll<HTMLElement>("[data-fps]").forEach((b) => b.addEventListener("click", () => set({ fps: +b.dataset.fps! })));
  el.querySelectorAll<HTMLElement>("[data-cap]").forEach((b) => b.addEventListener("click", () => set({ cap: +b.dataset.cap! })));
  el.querySelectorAll<HTMLElement>("[data-feat]").forEach((b) => b.addEventListener("click", () => set({ max_features: +b.dataset.feat! })));
  el.querySelector("#auto-steps")!.addEventListener("change", (ev) =>
    set({ steps: (ev.target as HTMLInputElement).checked ? null : e?.recommended_steps ?? 30000 }));
  el.querySelector("#steps")!.addEventListener("change", (ev) => set({ steps: Math.max(1000, +(ev.target as HTMLInputElement).value) }));
  el.querySelector("#viewer")!.addEventListener("change", (ev) => set({ viewer: (ev.target as HTMLInputElement).checked }));
  el.querySelector("#people")!.addEventListener("change", (ev) => set({ people: (ev.target as HTMLInputElement).checked }));
  el.querySelector("#bench")?.addEventListener("click", async () => {
    if (await guard(api("POST", "/bench"))) (toast("Measuring this PC… (about a minute)"), void poll());
  });
  el.querySelector("#run")!.addEventListener("click", async () => {
    const from = (el.querySelector("#from") as HTMLSelectElement).value || undefined;
    await guard(api("PUT", `/projects/${encodeURIComponent(project!.name)}/captures`,
      { captures: caps, settings: { ...settings, capture_id: selected } }));
    const job = await guard(api<Job>("POST", `/projects/${encodeURIComponent(project!.name)}/run`,
      { capture_id: selected, settings, from_stage: from }));
    if (job) {
      toast("Started. You can close this tab; the job keeps running.");
      await poll();
      $("jobs").scrollIntoView({ behavior: "smooth" });
    }
  });
}

// ------------------------------------------------------------------ 3. jobs

const ICON: Record<string, string> = { done: "✓", failed: "✕", interrupted: "!", running: "●", skipped: "–", pending: "○", cancelled: "–" };

function stepEta(s: Job["steps"][number]): string {
  if (s.status === "done" || s.status === "skipped") return s.started && s.ended ? fmt.dur(s.ended - s.started) : s.status === "skipped" ? "up to date" : "";
  if (s.status !== "running" || !s.started) return "";
  const el = Date.now() / 1000 - s.started;
  const pct = s.progress?.pct;
  if (s.kind === "train" && s.progress?.rate && s.total_steps) {
    const left = (s.total_steps * (1 - (pct ?? 0) / 100)) / s.progress.rate;
    return `${fmt.dur(el)} · ${fmt.dur(left)} left`;
  }
  return pct && pct > 2 ? `${fmt.dur(el)} · ~${fmt.dur((el * (100 - pct)) / pct)} left` : fmt.dur(el);
}

function renderJobs(): void {
  const el = $("jobs");
  const list = jobs.filter((j) => j.project === project?.name || j.project === "_machine").slice(0, 8);
  el.innerHTML = `
    <h2><span class="num">3</span>Jobs</h2>
    <p class="sub">One job runs at a time (they share the GPU). Jobs keep running when this tab is closed.</p>
    ${list.length ? list.map((j) => `
      <div class="job" data-job="${j.id}">
        <div class="jh"><span class="pill ${j.status}">${j.status}</span><span class="jt">${esc(j.title)}</span>
          <span class="muted">${fmt.time(j.created)}</span>
          ${j.status === "queued" || j.status === "running" || j.status === "paused" ? `<button class="small danger" data-act="cancel">Cancel</button>` : ""}
          ${["failed", "interrupted", "cancelled"].includes(j.status) ? `<button class="small" data-act="retry">Retry from the failed step</button>` : ""}
          ${!["running", "paused"].includes(j.status) ? `<button class="small ghost" data-act="delete">Remove</button>` : ""}
          <button class="small ghost" data-act="log">${openLogs.has(j.id) ? "Hide log" : "Log"}</button></div>
        <div class="steps">${j.steps.map((s) => {
          const pct = s.progress?.pct;
          return `<div class="step ${s.status}"><span class="ic">${ICON[s.status] ?? "○"}</span><span>${esc(s.label)}</span>
            <div class="prog ${s.status === "running" && pct == null ? "indet" : ""}"><i style="width:${
              s.status === "done" ? 100 : s.status === "running" ? Math.max(1, pct ?? 0) : 0}%"></i></div>
            <span class="when">${s.status === "running" && s.progress?.text ? `${esc(s.progress.text)} · ` : ""}${stepEta(s)}</span></div>`;
        }).join("")}</div>
        ${j.error ? `<div class="warn" style="color:var(--bad);margin-top:6px">${esc(j.error)}</div>` : ""}
        ${openLogs.has(j.id) ? `<pre class="log" data-log="${j.id}">loading…</pre>` : ""}
      </div>`).join("") : `<div class="empty">No jobs yet.</div>`}`;
  el.querySelectorAll<HTMLElement>("[data-act]").forEach((b) => b.addEventListener("click", async () => {
    const id = (b.closest("[data-job]") as HTMLElement).dataset.job!;
    const act = b.dataset.act!;
    if (act === "log") {
      openLogs.has(id) ? openLogs.delete(id) : openLogs.add(id);
      renderJobs();
      return;
    }
    if (act === "cancel" && !confirm("Cancel this job? A running step is stopped and its output is incomplete.")) return;
    if (act === "delete") await guard(api("DELETE", `/jobs/${id}`));
    else await guard(api("POST", `/jobs/${id}/${act}`));
    await poll();
  }));
  for (const id of openLogs) {
    const pre = el.querySelector(`[data-log="${id}"]`) as HTMLElement | null;
    if (pre) void api<{ text: string }>("GET", `/jobs/${id}/log`).then((r) => {
      pre.textContent = r.text.trim() || "(empty)";
      pre.scrollTop = pre.scrollHeight;
    }).catch(() => {});
  }
}

// ------------------------------------------------------------------ 4. training monitor

function renderTraining(): void {
  const el = $("training");
  if (!train) {
    el.hidden = true;
    return;
  }
  el.hidden = false;
  const d = train.data;
  const step = train.job.steps.find((s) => s.kind === "train")!;
  const running = step.status === "running";
  const total = d?.total || step.total_steps || 1;
  const last = <T,>(a: [number, T][] | undefined) => (a && a.length ? a[a.length - 1][1] : undefined);
  const left = d?.rate ? (total - d.step) / d.rate : null;
  const paused = d?.state === "paused";
  const built = el.dataset.job === train.job.id && el.querySelector("canvas");
  if (!built) {
    el.dataset.job = train.job.id;
    el.innerHTML = `
      <h2><span class="num">4</span>Training <span class="spacer"></span>
        <span id="tbtns"></span></h2>
      <p class="sub" id="tsub"></p>
      <div class="tstats" id="tstats"></div>
      <div class="charts">
        <div class="chart"><div class="ct">Training loss <b id="c-loss"></b></div><canvas id="ch-loss"></canvas></div>
        <div class="chart"><div class="ct">Quality on held-out frames (PSNR, dB) <b id="c-psnr"></b></div><canvas id="ch-psnr"></canvas></div>
        <div class="chart"><div class="ct">Gaussians <b id="c-gs"></b></div><canvas id="ch-gs"></canvas></div>
      </div>
      <div id="livebox"></div>`;
  }
  $("tsub").textContent = `${train.job.title}${running ? "" : ` · ${step.status}`}`;
  $("tbtns").innerHTML = running ? `
    <button class="small" data-t="${paused ? "resume" : "pause"}">${paused ? "Resume" : "Pause"}</button>
    <button class="small" data-t="stop" title="Finish now: save the result and export it">Stop and keep result</button>` : "";
  $("tbtns").querySelectorAll<HTMLElement>("[data-t]").forEach((b) => b.addEventListener("click", async () => {
    if (b.dataset.t === "stop" && !confirm("Stop training now and keep the splat as it is? It is saved, evaluated and exported.")) return;
    await guard(api("POST", `/jobs/${train!.job.id}/${b.dataset.t}`));
    await poll();
  }));
  $("tstats").innerHTML = `
    <div><b>${fmt.num(d?.step ?? 0)} / ${fmt.num(total)}</b><span>steps (${Math.round((100 * (d?.step ?? 0)) / total)} %)</span></div>
    <div><b>${d?.rate ? d.rate.toFixed(1) : "–"}</b><span>steps per second</span></div>
    <div><b>${running ? (paused ? "paused" : left != null ? fmt.dur(left) : "–") : step.status}</b><span>${running ? "left" : "status"}</span></div>
    <div><b>${last(d?.num_gs) != null ? fmt.num(last(d?.num_gs)!) : "–"}</b><span>Gaussians</span></div>
    <div><b>${last(d?.psnr) != null ? `${last(d?.psnr)!.toFixed(2)} dB` : "–"}</b><span>latest PSNR</span></div>`;
  $("c-loss").textContent = last(d?.loss)?.toFixed(3) ?? "";
  $("c-psnr").textContent = last(d?.psnr) != null ? `${last(d?.psnr)!.toFixed(2)}` : "";
  $("c-gs").textContent = last(d?.num_gs) != null ? fmt.num(last(d?.num_gs)!) : "";
  drawChart($("ch-loss") as HTMLCanvasElement, d?.loss ?? [], { color: "#3d9bff", xMax: total, log: true });
  drawChart($("ch-psnr") as HTMLCanvasElement, d?.psnr ?? [], { color: "#3ccf8e", xMax: total, dots: true });
  drawChart($("ch-gs") as HTMLCanvasElement, d?.num_gs ?? [], { color: "#ffb020", xMax: total, format: (v) => fmt.num(v) });
  const live = $("livebox");
  const wantLive = running && d?.viewer;
  if (!wantLive) live.innerHTML = "";
  else if (!live.querySelector(".lvhead")) {
    live.innerHTML = `<div class="row lvhead" style="margin-top:12px"><label class="check"><input type="checkbox" id="showlive" ${showLive ? "checked" : ""}>
      Live 3D view</label><a href="${VIEWER_URL}" target="_blank" rel="noopener" class="small">open in a new tab ↗</a>
      <span class="faint">Drag to orbit. It shows the splat as it trains.</span></div><div id="liveframe"></div>`;
    live.querySelector("#showlive")!.addEventListener("change", (e) => {
      showLive = (e.target as HTMLInputElement).checked;
      live.querySelector("#liveframe")!.innerHTML = showLive ? `<div class="live"><iframe src="${VIEWER_URL}"></iframe></div>` : "";
    });
    if (showLive) live.querySelector("#liveframe")!.innerHTML = `<div class="live"><iframe src="${VIEWER_URL}"></iframe></div>`;
  }
}

// ------------------------------------------------------------------ 5. results

function renderResults(): void {
  const el = $("results");
  const ex = project?.exports ?? [];
  el.innerHTML = `
    <h2><span class="num">5</span>Splats</h2>
    <p class="sub">Finished splats. Clean up removes floaters and noise; open one in the explorer to walk through it.</p>
    ${ex.length ? `<div class="exports">${ex.map((x) => `
      <div class="export"><div class="en">${esc(x.name ?? x.export)}<small>export/${esc(x.export)} · ${fmt.bytes(x.size)} · ${fmt.time(x.mtime)}</small></div>
        ${x.current ? `<span class="tag">in the explorer</span>` : ""}
        ${x.cleaned ? `<span class="tag">cleaned: ${fmt.num(x.cleaned.deleted)} removed</span>` : ""}
        <button class="small" data-clean="${esc(x.export)}" ${x.cleanable ? "" : "disabled title='Re-export to enable cleanup'"}>Clean up…</button>
        <button class="small primary" data-open="${esc(x.export)}">Open in explorer</button></div>`).join("")}</div>`
      : `<div class="empty">No splats yet: build one above.</div>`}`;
  el.querySelectorAll<HTMLElement>("[data-open]").forEach((b) => b.addEventListener("click", async () => {
    const w = window.open("about:blank", "_blank");
    if (await guard(api("POST", `/projects/${encodeURIComponent(project!.name)}/current`, { export: b.dataset.open }))) {
      if (w) w.location.href = "/";
      void loadProject(project!.name);
    } else w?.close();
  }));
  el.querySelectorAll<HTMLElement>("[data-clean]").forEach((b) => b.addEventListener("click", () =>
    window.open(`/clean.html?project=${encodeURIComponent(project!.name)}&export=${encodeURIComponent(b.dataset.clean!)}`, "_blank")));
}

function renderMachine(): void {
  const m = $("machine");
  if (!status) return void (m.textContent = "");
  m.innerHTML = `<b>${esc(status.gpu.name.replace("NVIDIA GeForce ", ""))}</b> · ${Math.round(status.gpu.vram_mb / 1024)} GB ·
    ${esc(status.host)} · speeds: ${status.train_runs_measured ? "measured" : status.bench ? "benchmark" : "defaults"}`;
}

function renderAll(): void {
  renderMachine();
  renderFootage();
  renderSettings();
  renderJobs();
  renderTraining();
  renderResults();
}

// ------------------------------------------------------------------ polling

let lastSig = "";
async function poll(): Promise<void> {
  try {
    status = await api<Status>("GET", "/status");
    $("offline").hidden = true;
  } catch {
    $("offline").hidden = false;
    return;
  }
  const list = await api<Job[]>("GET", "/jobs");
  // Running jobs: fetch them one by one for live step progress.
  jobs = await Promise.all(list.map((j) => (["running", "paused"].includes(j.status) ? api<Job>("GET", `/jobs/${j.id}`) : j)));
  const sig = jobs.map((j) => `${j.id}:${j.status}:${j.steps.map((s) => s.status).join("")}`).join("|");
  const finished = lastSig && sig !== lastSig;
  lastSig = sig;
  // The training monitor follows the running training job, else the newest one of this project.
  const tj = jobs.find((j) => j.project === project?.name && j.steps.some((s) => s.kind === "train" && s.status === "running")) ??
    jobs.find((j) => j.project === project?.name && j.steps.some((s) => s.kind === "train" && s.status !== "pending" && s.status !== "skipped"));
  if (tj) train = { job: tj, data: (await api<TrainProgress>("GET", `/jobs/${tj.id}/train`).catch(() => null)) };
  else train = null;
  renderMachine();
  renderJobs();
  renderTraining();
  if (finished && project) {
    // A step finished: outputs changed (exports, up-to-date stages, measured speeds).
    project = await api<Project>("GET", `/projects/${encodeURIComponent(project.name)}`);
    renderResults();
    refreshEstimate();
  }
}

async function start(): Promise<void> {
  for (;;) {
    try {
      status = await api<Status>("GET", "/status");
      break;
    } catch {
      $("offline").hidden = false;
      await new Promise((r) => setTimeout(r, 3000));
    }
  }
  $("offline").hidden = true;
  await guard(loadProjects());
  await poll();
  const loop = async () => {
    await poll().catch(() => {});
    const active = jobs.some((j) => ["running", "paused", "queued"].includes(j.status));
    setTimeout(loop, active ? 1500 : 5000);
  };
  setTimeout(loop, 1500);
  addEventListener("resize", debounce(() => project && timeline.render(project, caps, selected), 200));
}

void start();
