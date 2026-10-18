// Markers in 3D: round glass icons ("+" for an info card, a waveform for audio).
// The title shows on hover or when the player is close. Click (or press E when close) to open.

import * as THREE from "three";
import type { Marker } from "./types";

const ICONS = {
  info: `<svg viewBox="0 0 24 24" width="22" height="22"><path d="M12 5v14M5 12h14" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/></svg>`,
  audio: `<svg viewBox="0 0 24 24" width="22" height="22"><path d="M5 10v4M8.5 7v10M12 4v16M15.5 7v10M19 10v4" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg>`,
};

export const markerKind = (m: Marker): "info" | "audio" => m.kind ?? (m.audio && !m.images?.length && !m.text ? "audio" : "info");

export class MarkerLayer {
  private els = new Map<string, HTMLDivElement>();
  private tmp = new THREE.Vector3();
  nearest: Marker | null = null;
  /** Marker under the screen centre (the crosshair), if any, closer than gazeRange. */
  gazed: Marker | null = null;
  gazeRange = 8;
  activeId: string | null = null;
  onOpen: (m: Marker) => void = () => {};

  constructor(private root: HTMLElement, public markers: Marker[]) {}

  sync(): void {
    const ids = new Set(this.markers.map((m) => m.id));
    for (const [id, el] of this.els) if (!ids.has(id)) (el.remove(), this.els.delete(id));
    for (const m of this.markers) {
      let el = this.els.get(m.id);
      if (!el) {
        el = document.createElement("div");
        el.className = "marker";
        el.addEventListener("click", (e) => {
          e.stopPropagation();
          const mk = this.markers.find((x) => x.id === el!.dataset.id);
          if (mk) this.onOpen(mk);
        });
        this.root.appendChild(el);
        this.els.set(m.id, el);
      }
      el.dataset.id = m.id;
      const kind = markerKind(m);
      el.dataset.kind = kind;
      el.innerHTML = `<button class="icon" aria-label="${kind}">${ICONS[kind]}</button><span class="label"></span>`;
      (el.querySelector(".label") as HTMLElement).textContent = m.title || "(untitled)";
    }
  }

  /** Where a marker's icon is on screen: centre in px, icon radius in px, distance, and whether it is in front of the camera. */
  project(m: Marker, camera: THREE.PerspectiveCamera, w: number, h: number): { x: number; y: number; r: number; dist: number; front: boolean; scale: number } {
    const p = this.tmp.set(...m.position);
    const dist = p.distanceTo(camera.position);
    p.project(camera);
    const scale = THREE.MathUtils.clamp(2.2 / Math.max(dist, 0.3), 0.55, 1.25);
    return { x: ((p.x + 1) / 2) * w, y: ((1 - p.y) / 2) * h, r: 22 * scale, dist, front: p.z > -1 && p.z < 1, scale };
  }

  /** Position icons on screen (scaled by distance); find the nearest marker within its radius. */
  update(camera: THREE.PerspectiveCamera, eye: THREE.Vector3, w: number, h: number, selectedId?: string): void {
    this.nearest = null;
    this.gazed = null;
    let best = Infinity;
    let bestGaze = Infinity;
    for (const m of this.markers) {
      const el = this.els.get(m.id);
      if (!el) continue;
      const dist = this.tmp.set(...m.position).distanceTo(eye);
      if (dist < (m.radius ?? 1.5) && dist < best) {
        best = dist;
        this.nearest = m;
      }
      const { x: sx, y: sy, front, scale } = this.project(m, camera, w, h);
      const visible = front && sx > -0.05 * w && sx < 1.05 * w && sy > -0.05 * h && sy < 1.05 * h && dist < 30;
      el.style.display = visible ? "" : "none";
      if (!visible) continue;
      el.style.transform = `translate(${sx}px, ${sy}px) scale(${scale.toFixed(3)})`;
      // Gaze target: the icon (radius 22 px, scaled) under the screen centre, with a little slack.
      const r = 22 * scale + 6;
      const off = Math.hypot(sx - w / 2, sy - h / 2);
      if (off < r && dist < this.gazeRange && off < bestGaze) {
        bestGaze = off;
        this.gazed = m;
      }
      el.style.zIndex = String(1000 - Math.round(dist * 10));
      el.classList.toggle("near", m === this.nearest);
      el.classList.toggle("active", m.id === this.activeId);
      el.classList.toggle("selected", m.id === selectedId);
    }
    for (const [id, el] of this.els) el.classList.toggle("gazed", id === this.gazed?.id);
  }
}
