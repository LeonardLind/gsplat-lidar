// Timeline: one lane per capture (clips that become one splat). Clips show as filmstrips in recording
// order with the real gap between them; drag a clip's ends to trim it, drag a clip onto another lane to
// merge it into that capture, or onto "new capture" to split it off.

import { esc, fmt, type Capture, type Clip, type Project } from "./api";

const GAP_PX = 96;
const MIN_BAR = 120;
const MIN_KEEP_S = 2;
const THUMBS = 10; // thumbnails made per clip (the server caches them)

export interface TimelineEvents {
  change(caps: Capture[]): void; // trims or grouping changed (save + re-estimate)
  select(id: string): void;
}

/** A capture's id follows its clips, so a different set of clips never reuses an old merged view folder. */
export const captureId = (c: Capture) => c.clips.map((x) => x.id).join("+");

export class Timeline {
  private project!: Project;
  private caps: Capture[] = [];
  private selected = "";
  private scale = 1; // px per second
  private root: HTMLElement | null = null;

  constructor(private ev: TimelineEvents) {}

  /** Draw into `root` (or the last one, on resize). */
  render(project: Project, caps: Capture[], selected: string, root = this.root): void {
    if (!root) return;
    this.root = root;
    this.project = project;
    this.caps = caps;
    this.selected = selected;
    const clips = new Map(project.clips.map((c) => [c.id, c]));
    if (!caps.length) {
      this.root.innerHTML = "";
      return;
    }
    const width = Math.max(300, (root.clientWidth || 900) - 246);
    // px per second so every lane fits; short clips get a minimum width, which the long ones give up.
    this.scale = Math.min(...caps.map((cap) => {
      const durs = cap.clips.map((c) => clips.get(c.id)?.duration ?? 0);
      const room = width - GAP_PX * (durs.length - 1);
      let scale = room / Math.max(durs.reduce((a, b) => a + b, 0), 1);
      for (let k = 0; k < 3; k++) {
        const small = durs.filter((d) => d * scale < MIN_BAR);
        const big = durs.filter((d) => d * scale >= MIN_BAR).reduce((a, b) => a + b, 0);
        scale = Math.max(0.01, (room - small.length * MIN_BAR) / Math.max(big, 1));
      }
      return scale;
    }));
    this.root.innerHTML = `
      <div class="timeline">
        ${caps.map((cap) => this.lane(cap, clips)).join("")}
        <div class="newlane" data-newlane>Drop a clip here to make it a separate capture</div>
      </div>
      <div class="tlhint">Drag a clip's ends to trim the start and end · drag a clip onto another capture to combine them ·
        each capture becomes one splat</div>`;
    this.bind();
  }

  private lane(cap: Capture, clips: Map<string, Clip>): string {
    const recorded = cap.clips.reduce((s, c) => s + (clips.get(c.id)?.duration ?? 0), 0);
    const kept = cap.clips.reduce((s, c) => s + keptOf(c, clips.get(c.id)), 0);
    const parts: string[] = [];
    cap.clips.forEach((c, k) => {
      const clip = clips.get(c.id);
      if (!clip) return;
      if (k > 0) {
        const prev = clips.get(cap.clips[k - 1].id);
        const gap = prev?.end != null && clip.start != null ? clip.start - prev.end : null;
        parts.push(`<div class="gap" style="width:${GAP_PX}px">${gap != null ? `${fmt.dur(Math.max(gap, 0))} gap` : "gap"}<br>
          <span class="faint">${gap != null && gap < 1800 ? "battery swap?" : ""}</span></div>`);
      }
      parts.push(this.bar(cap, c, clip));
    });
    return `
      <div class="lane ${cap.id === this.selected ? "selected" : ""}" data-lane="${esc(cap.id)}">
        <div class="head">
          <label><input type="radio" name="cap" ${cap.id === this.selected ? "checked" : ""} data-select="${esc(cap.id)}">
            <input type="text" value="${esc(cap.name)}" data-rename="${esc(cap.id)}" title="Capture name"></label>
          <div class="info">${cap.clips.length} clip${cap.clips.length > 1 ? "s" : ""} · ${fmt.clock(recorded)} recorded${
            Math.abs(kept - recorded) > 0.5 ? ` · ${fmt.clock(kept)} kept` : ""}</div>
          ${cap.clips.length > 1 ? `<button class="small ghost" data-split="${esc(cap.id)}">Split into separate captures</button>` : ""}
        </div>
        <div class="track">${parts.join("")}</div>
      </div>`;
  }

  private bar(cap: Capture, c: { id: string; start: number; end: number | null }, clip: Clip): string {
    const dur = clip.duration ?? 0;
    const w = Math.max(MIN_BAR, dur * this.scale);
    const s = c.start ?? 0, e = c.end ?? dur;
    const n = Math.max(1, Math.min(THUMBS, Math.round(w / 64)));
    const thumbs = Array.from({ length: n }, (_, k) => Math.floor(((k + 0.5) * THUMBS) / n));
    const base = `/studio-api/projects/${encodeURIComponent(this.project.name)}/clips/${encodeURIComponent(clip.id)}/thumb`;
    return `
      <div class="bar" style="width:${w}px" data-bar="${esc(clip.id)}" data-cap="${esc(cap.id)}" data-w="${w}" data-dur="${dur}">
        <div class="strip">${thumbs.map((i) => `<img loading="lazy" src="${base}/${i}?n=${THUMBS}" alt="">`).join("")}</div>
        <div class="cut" style="left:0;width:${(s / dur) * w}px"></div>
        <div class="cut" style="right:0;width:${((dur - e) / dur) * w}px"></div>
        <div class="handle" data-trim="start" style="left:${(s / dur) * w - 5}px"></div>
        <div class="handle" data-trim="end" style="left:${(e / dur) * w - 5}px"></div>
        <div class="label">${esc(clip.id)}</div>
        <div class="dur">${trimText(s, e, dur)}</div>
      </div>`;
  }

  private bind(): void {
    const r = this.root!;
    r.querySelectorAll<HTMLInputElement>("[data-select]").forEach((el) =>
      el.addEventListener("change", () => this.ev.select(el.dataset.select!)));
    r.querySelectorAll<HTMLElement>(".lane").forEach((el) =>
      el.addEventListener("click", (e) => {
        if (!(e.target as HTMLElement).closest("input, button, .bar")) this.ev.select(el.dataset.lane!);
      }));
    r.querySelectorAll<HTMLInputElement>("[data-rename]").forEach((el) =>
      el.addEventListener("change", () => {
        const cap = this.caps.find((c) => c.id === el.dataset.rename);
        if (cap) (cap.name = el.value.trim() || cap.name, this.ev.change(this.caps));
      }));
    r.querySelectorAll<HTMLElement>("[data-split]").forEach((el) =>
      el.addEventListener("click", () => {
        const k = this.caps.findIndex((c) => c.id === el.dataset.split);
        const parts = this.caps[k].clips.map((c) => ({ id: c.id, name: c.id, clips: [c] }));
        this.caps.splice(k, 1, ...parts);
        this.ev.change(this.caps);
      }));
    r.querySelectorAll<HTMLElement>(".bar").forEach((bar) => this.bindBar(bar));
  }

  private bindBar(bar: HTMLElement): void {
    const clipId = bar.dataset.bar!, capId = bar.dataset.cap!;
    const w = +bar.dataset.w!, dur = +bar.dataset.dur!;
    const cap = () => this.caps.find((c) => c.id === capId)!;
    const entry = () => cap().clips.find((c) => c.id === clipId)!;

    // Trim handles.
    bar.querySelectorAll<HTMLElement>(".handle").forEach((h) => {
      h.addEventListener("pointerdown", (e) => {
        e.stopPropagation();
        h.setPointerCapture(e.pointerId);
        const which = h.dataset.trim as "start" | "end";
        const left = bar.getBoundingClientRect().left;
        const move = (ev: PointerEvent) => {
          const c = entry();
          const t = Math.min(dur, Math.max(0, ((ev.clientX - left) / w) * dur));
          if (which === "start") c.start = Math.min(t, (c.end ?? dur) - MIN_KEEP_S);
          else c.end = Math.max(t, c.start + MIN_KEEP_S) >= dur - 0.05 ? null : Math.max(t, c.start + MIN_KEEP_S);
          c.start = Math.max(0, Math.round(c.start * 10) / 10);
          if (c.end != null) c.end = Math.round(c.end * 10) / 10;
          const s = c.start, en = c.end ?? dur;
          const [cutL, cutR] = bar.querySelectorAll<HTMLElement>(".cut");
          cutL.style.width = `${(s / dur) * w}px`;
          cutR.style.width = `${((dur - en) / dur) * w}px`;
          const [hs, he] = bar.querySelectorAll<HTMLElement>(".handle");
          hs.style.left = `${(s / dur) * w - 5}px`;
          he.style.left = `${(en / dur) * w - 5}px`;
          (bar.querySelector(".dur") as HTMLElement).textContent = trimText(s, en, dur);
        };
        const up = () => {
          h.removeEventListener("pointermove", move);
          h.removeEventListener("pointerup", up);
          this.ev.change(this.caps);
        };
        h.addEventListener("pointermove", move);
        h.addEventListener("pointerup", up);
      });
    });

    // Drag the clip to another capture.
    bar.addEventListener("pointerdown", (e) => {
      if ((e.target as HTMLElement).closest(".handle")) return;
      const x0 = e.clientX, y0 = e.clientY;
      let dragging = false;
      let target: HTMLElement | null = null;
      bar.setPointerCapture(e.pointerId);
      const move = (ev: PointerEvent) => {
        if (!dragging && Math.hypot(ev.clientX - x0, ev.clientY - y0) < 6) return;
        dragging = true;
        bar.classList.add("dragging");
        const over = document.elementFromPoint(ev.clientX, ev.clientY) as HTMLElement | null;
        const t = (over?.closest(".lane, [data-newlane]") as HTMLElement | null) ?? null;
        if (t !== target) {
          target?.classList.remove("drop");
          target = t && (t.dataset.lane !== capId || t.dataset.newlane !== undefined) ? t : null;
          target?.classList.add("drop");
        }
      };
      const up = () => {
        bar.removeEventListener("pointermove", move);
        bar.removeEventListener("pointerup", up);
        bar.classList.remove("dragging");
        target?.classList.remove("drop");
        if (!dragging || !target) return;
        const from = cap();
        const item = entry();
        from.clips = from.clips.filter((c) => c.id !== clipId);
        if (target.dataset.newlane !== undefined) {
          this.caps.push({ id: clipId, name: clipId, clips: [item] });
        } else {
          const to = this.caps.find((c) => c.id === target!.dataset.lane)!;
          to.clips.push(item);
          const starts = new Map(this.project.clips.map((c) => [c.id, c.start ?? 0]));
          to.clips.sort((a, b) => (starts.get(a.id) ?? 0) - (starts.get(b.id) ?? 0));
        }
        this.caps = this.caps.filter((c) => c.clips.length);
        this.ev.change(this.caps);
      };
      bar.addEventListener("pointermove", move);
      bar.addEventListener("pointerup", up);
    });
  }
}

function keptOf(c: { start: number; end: number | null }, clip?: Clip): number {
  const dur = clip?.duration ?? 0;
  return Math.max(0, (c.end ?? dur) - (c.start ?? 0));
}

function trimText(s: number, e: number, dur: number): string {
  return s < 0.05 && e > dur - 0.05 ? fmt.clock(dur) : `${fmt.clock(s)}–${fmt.clock(e)} · ${fmt.clock(e - s)} kept`;
}
