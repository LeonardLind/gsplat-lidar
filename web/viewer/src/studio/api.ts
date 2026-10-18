// Client for the studio job server (python -m app serve), proxied by Vite under /studio-api.

export interface Clip {
  id: string; path: string; name: string; model: string | null; fps: number | null; duration: number | null;
  width: number | null; height: number | null; codec: string | null; lenses: number; size_bytes: number | null;
  start: number | null; end: number | null; problems: string[]; probed: boolean;
}
export interface CaptureClip { id: string; start: number; end: number | null }
export interface Capture { id: string; name: string; clips: CaptureClip[] }
export interface Reason { clips: string[]; gap_s: number; text: string }
export interface ExportInfo {
  export: string; name: string; current: boolean; size: number; mtime: number; cleanable: boolean;
  cleaned: { count: number; deleted: number; time: number } | null;
}
export interface Project {
  name: string; clips: Clip[]; captures: Capture[]; suggested: boolean; reasons: Reason[];
  settings: Partial<Settings> & { capture_id?: string }; exports: ExportInfo[];
}
export interface Settings {
  fps: number; cap: number; steps: number | null; viewer: boolean; people: boolean; max_features?: number;
}
export interface Stage { stage: string; label: string; seconds: number; source: string; detail?: string; uptodate?: boolean }
export interface Estimate {
  decoded_pairs: number; frames: number; images: number; steps: number; recommended_steps: number;
  looks_per_image: number; disk_bytes: number; stages: Stage[]; total_seconds: number; host: string;
  gpu: { name: string; vram_mb: number }; has_bench: boolean; train_runs_measured: number;
}
export interface JobStep {
  name: string; kind: string; label: string; status: string; started: number | null; ended: number | null;
  code: number | null; progress: { pct: number | null; text: string; rate?: number | null; state?: string } | null;
  run_dir?: string; total_steps?: number;
}
export interface Job {
  id: string; project: string; title: string; status: string; created: number; started: number | null;
  ended: number | null; steps: JobStep[]; error?: string; meta: { run?: string; views_id?: string; export?: string };
}
export interface TrainProgress {
  loss: [number, number][]; num_gs: [number, number][]; psnr: [number, number][]; ssim: [number, number][];
  step: number; total: number; state: string; t0: number | null; t_last: number | null; rate: number | null;
  status: string; viewer: boolean;
}
export interface Status {
  host: string; gpu: { name: string; vram_mb: number }; bench: { points: { gaussians: number; s_per_step: number }[] } | null;
  train_runs_measured: number; running: string | null;
}
export interface DirListing {
  path: string | null; parent: string | null; dirs: { name: string; path: string }[];
  files: { name: string; path: string; size: number; mtime: number }[];
}

const BASE = "/studio-api";

export async function api<T>(method: string, path: string, body?: unknown): Promise<T> {
  const r = await fetch(BASE + path, {
    method,
    headers: body !== undefined && !(body instanceof Uint8Array) ? { "Content-Type": "application/json" } : undefined,
    body: body === undefined ? undefined : body instanceof Uint8Array ? new Blob([body as Uint8Array<ArrayBuffer>]) : JSON.stringify(body),
    cache: "no-store",
  });
  const text = await r.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    if (!r.ok) throw new Error(`${r.status}: server not reachable`);
  }
  if (!r.ok) throw new Error((data as { error?: string } | null)?.error ?? `HTTP ${r.status}`);
  return data as T;
}

export const fmt = {
  dur(s: number): string {
    if (!isFinite(s)) return "–";
    if (s < 60) return `${Math.max(1, Math.round(s))} s`;
    if (s < 3600) return `${Math.round(s / 60)} min`;
    const h = Math.floor(s / 3600), m = Math.round((s % 3600) / 60);
    return m === 60 ? `${h + 1} h` : `${h} h ${String(m).padStart(2, "0")} min`;
  },
  clock(s: number): string {
    const m = Math.floor(s / 60), sec = Math.floor(s % 60);
    return `${m}:${String(sec).padStart(2, "0")}`;
  },
  bytes(b: number): string {
    if (b >= 1e9) return `${(b / 1e9).toFixed(b >= 1e10 ? 0 : 1)} GB`;
    if (b >= 1e6) return `${(b / 1e6).toFixed(0)} MB`;
    return `${Math.round(b / 1e3)} kB`;
  },
  num(n: number): string {
    return n >= 1e6 ? `${(n / 1e6).toFixed(n >= 1e7 ? 0 : 2)} M` : n >= 1e4 ? `${Math.round(n / 1e3)} k` : n.toLocaleString("en");
  },
  time(t: number): string {
    return new Date(t * 1000).toLocaleString(undefined, { hour: "2-digit", minute: "2-digit", day: "numeric", month: "short" });
  },
};

export const esc = (s: unknown): string =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);
