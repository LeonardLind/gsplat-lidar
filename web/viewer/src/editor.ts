// Edit mode: place and edit pop-up markers and collision blocks, then save scene.json.
//   Tab          toggle edit mode (frees the mouse)
//   1 / 2 / 3 / 4  tool: select / marker / block / sound
//   click        select tool: pick a marker label or block; marker/block tool: place at the clicked surface
//   Delete       remove the selected item
//   Ctrl+S       save (dev server writes scene.json; a copy of the old one is kept as scene.prev.json)

import * as THREE from "three";
import type { CollisionWorld } from "./collision";
import type { MarkerLayer } from "./markers";
import type { Block, Marker, SceneFile, Sound, Vec3 } from "./types";

type Tool = "select" | "marker" | "block" | "sound";
type Selection = { kind: "marker" | "block" | "sound"; id: string } | null;

const uid = (p: string) => `${p}-${Math.random().toString(36).slice(2, 8)}`;

export class Editor {
  active = false;
  tool: Tool = "select";
  selection: Selection = null;
  dirty = false;
  onSoundsChanged: () => void = () => {};
  private blockGroup = new THREE.Group();
  private raycaster = new THREE.Raycaster();

  constructor(
    private scene: SceneFile,
    threeScene: THREE.Scene,
    private camera: THREE.PerspectiveCamera,
    private canvas: HTMLCanvasElement,
    private world: CollisionWorld,
    private markers: MarkerLayer,
    private panel: HTMLElement,
    private status: (msg: string) => void,
  ) {
    threeScene.add(this.blockGroup);
    this.rebuildBlocks();
    canvas.addEventListener("click", (e) => this.active && this.onClick(e));
    addEventListener("keydown", (e) => this.onKey(e));
  }

  setActive(on: boolean): void {
    this.active = on;
    this.blockGroup.visible = on || this.showBlocksInPlay;
    if (!on) this.select(null);
    this.renderPanel();
  }

  showBlocksInPlay = false;

  private onKey(e: KeyboardEvent): void {
    if ((e.target as HTMLElement)?.closest?.("input, textarea")) return;
    if (e.ctrlKey && e.code === "KeyS") {
      e.preventDefault();
      void this.save();
      return;
    }
    if (!this.active) return;
    if (e.code === "Digit1") this.setTool("select");
    if (e.code === "Digit2") this.setTool("marker");
    if (e.code === "Digit3") this.setTool("block");
    if (e.code === "Digit4") this.setTool("sound");
    if (e.code === "Delete" || e.code === "Backspace") this.deleteSelected();
  }

  setTool(t: Tool): void {
    this.tool = t;
    this.renderPanel();
  }

  private rayFromMouse(e: MouseEvent): { o: Vec3; d: Vec3; ray: THREE.Ray } {
    const r = this.canvas.getBoundingClientRect();
    const ndc = new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    this.raycaster.setFromCamera(ndc, this.camera);
    const { origin: o, direction: d } = this.raycaster.ray;
    return { o: [o.x, o.y, o.z], d: [d.x, d.y, d.z], ray: this.raycaster.ray };
  }

  private onClick(e: MouseEvent): void {
    const { o, d, ray } = this.rayFromMouse(e);
    if (this.tool === "select") {
      const hits = this.raycaster.intersectObjects(this.blockGroup.children.filter((c) => c instanceof THREE.Mesh), false);
      const kind = hits.length ? (hits[0].object.userData.kind as "block" | "sound") : null;
      this.select(kind ? { kind, id: hits[0].object.userData.id } : null);
      return;
    }
    const hit = this.world.raycast(o, d, 40);
    if (!hit) {
      this.status("Nothing under the cursor to place on");
      return;
    }
    if (this.tool === "marker") {
      // Pull the marker slightly back towards the camera so it floats in front of the surface.
      const p = new THREE.Vector3(...hit).addScaledVector(ray.direction, -0.15);
      const m: Marker = { id: uid("m"), kind: "info", position: [p.x, p.y, p.z], title: "New marker", text: "", images: [], radius: 1.5 };
      this.scene.markers.push(m);
      this.markers.sync();
      this.select({ kind: "marker", id: m.id });
    } else if (this.tool === "sound") {
      const p = new THREE.Vector3(...hit).addScaledVector(ray.direction, -0.2);
      const snd: Sound = { id: uid("s"), position: [p.x, p.y, p.z], url: "ambient_room.wav", volume: 0.5, refDistance: 2 };
      (this.scene.sounds ??= []).push(snd);
      this.rebuildBlocks();
      this.onSoundsChanged();
      this.select({ kind: "sound", id: snd.id });
    } else {
      const ground = this.world.groundZ(hit[0], hit[1], 0.1, hit[2] + 0.05);
      const base = Number.isFinite(ground) ? ground : this.world.floorZ;
      const yaw = (Math.atan2(ray.direction.y, ray.direction.x) * 180) / Math.PI + 90;
      const b: Block = { id: uid("b"), center: [hit[0], hit[1], base + 1.1], size: [1.0, 0.2, 2.2], yawDeg: Math.round(yaw) };
      this.scene.blocks.push(b);
      this.rebuildBlocks();
      this.select({ kind: "block", id: b.id });
    }
    this.dirty = true;
  }

  select(s: Selection): void {
    this.selection = s;
    this.rebuildBlocks();
    this.renderPanel();
  }

  private deleteSelected(): void {
    const s = this.selection;
    if (!s) return;
    if (s.kind === "marker") this.scene.markers = this.scene.markers.filter((m) => m.id !== s.id);
    else if (s.kind === "sound") {
      this.scene.sounds = (this.scene.sounds ?? []).filter((x) => x.id !== s.id);
      this.onSoundsChanged();
    } else this.scene.blocks = this.scene.blocks.filter((b) => b.id !== s.id);
    this.markers.markers = this.scene.markers;
    this.world.blocks = this.scene.blocks;
    this.markers.sync();
    this.dirty = true;
    this.select(null);
  }

  rebuildBlocks(): void {
    this.world.blocks = this.scene.blocks;
    for (const c of [...this.blockGroup.children]) {
      this.blockGroup.remove(c);
      if (c instanceof THREE.Mesh || c instanceof THREE.LineSegments) {
        c.geometry.dispose();
        (c.material as THREE.Material).dispose();
      }
    }
    for (const b of this.scene.blocks) {
      const sel = this.selection?.kind === "block" && this.selection.id === b.id;
      const geo = new THREE.BoxGeometry(...b.size);
      const mesh = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({
        color: sel ? 0xffb020 : 0x2f9bff, transparent: true, opacity: sel ? 0.35 : 0.2, depthWrite: false,
      }));
      const edges = new THREE.LineSegments(new THREE.EdgesGeometry(geo), new THREE.LineBasicMaterial({ color: sel ? 0xffb020 : 0x2f9bff }));
      for (const o of [mesh, edges]) {
        o.position.set(...b.center);
        o.rotation.z = (b.yawDeg * Math.PI) / 180;
        o.userData.id = b.id;
        o.userData.kind = "block";
        this.blockGroup.add(o);
      }
    }
    // Sound sources: small spheres (shown with the blocks).
    for (const snd of this.scene.sounds ?? []) {
      const sel = this.selection?.kind === "sound" && this.selection.id === snd.id;
      const ball = new THREE.Mesh(new THREE.SphereGeometry(0.12, 16, 12),
        new THREE.MeshBasicMaterial({ color: sel ? 0xffb020 : 0x3ddc84, transparent: true, opacity: 0.8 }));
      ball.position.set(...snd.position);
      ball.userData.id = snd.id;
      ball.userData.kind = "sound";
      this.blockGroup.add(ball);
    }
    this.blockGroup.visible = this.active || this.showBlocksInPlay;
  }

  /** Side panel: tool buttons and fields for the selected item. */
  renderPanel(): void {
    const p = this.panel;
    p.style.display = this.active ? "" : "none";
    if (!this.active) return;
    const s = this.selection;
    const m = s?.kind === "marker" ? this.scene.markers.find((x) => x.id === s.id) : undefined;
    const b = s?.kind === "block" ? this.scene.blocks.find((x) => x.id === s.id) : undefined;
    const snd = s?.kind === "sound" ? (this.scene.sounds ?? []).find((x) => x.id === s.id) : undefined;
    const toolBtn = (t: Tool, label: string, key: string) =>
      `<button data-tool="${t}" class="${this.tool === t ? "on" : ""}">${label} <kbd>${key}</kbd></button>`;
    const num = (name: string, v: number, step = 0.05) =>
      `<label>${name}<input type="number" step="${step}" data-field="${name}" value="${+v.toFixed(3)}"></label>`;
    let html = `<h2>Edit mode</h2><div class="tools">${toolBtn("select", "Select", "1")}${toolBtn("marker", "Marker", "2")}${toolBtn("block", "Block", "3")}${toolBtn("sound", "Sound", "4")}</div>`;
    html += `<p class="hint">${this.tool === "select" ? "Click a block or a marker label to edit it." : this.tool === "marker" ? "Click a surface to place a pop-up marker." : this.tool === "sound" ? "Click to place a looping sound source." : "Click a surface to place a collision block."}</p>`;
    if (m) {
      const kind = m.kind ?? "info";
      html += `<h3>Marker</h3>
        <label>Type<select data-field="kind"><option value="info" ${kind === "info" ? "selected" : ""}>Info card (images + text)</option>
          <option value="audio" ${kind === "audio" ? "selected" : ""}>Audio (narration in the audio bar)</option></select></label>
        <label>Title<input data-field="title" value="${escapeAttr(m.title)}"></label>
        <label>Text<textarea data-field="text" rows="5">${escapeHtml(m.text)}</textarea></label>
        <div class="row">${num("x", m.position[0])}${num("y", m.position[1])}${num("z", m.position[2])}</div>
        ${num("radius", m.radius ?? 1.5, 0.1)}
        <label>Images (one file per line)<textarea data-field="images" rows="3">${escapeHtml((m.images ?? []).join("\n"))}</textarea></label>
        <label>Audio file<input data-field="audio" value="${escapeAttr(m.audio ?? "")}" placeholder="assets/voice.mp3"></label>
        <label class="check"><input type="checkbox" data-field="spatial" ${m.spatial ? "checked" : ""}> Play from the marker's position</label>
        <label>Upload images / audio from this PC<input type="file" data-upload multiple accept="image/*,audio/*"></label>`;
    } else if (b) {
      html += `<h3>Collision block</h3>
        <div class="row">${num("x", b.center[0])}${num("y", b.center[1])}${num("z", b.center[2])}</div>
        <div class="row">${num("width", b.size[0])}${num("depth", b.size[1])}${num("height", b.size[2])}</div>
        ${num("yaw", b.yawDeg, 5)}`;
    } else if (snd) {
      html += `<h3>Sound source</h3>
        <label>Audio file<input data-field="url" value="${escapeAttr(snd.url)}"></label>
        <div class="row">${num("x", snd.position[0])}${num("y", snd.position[1])}${num("z", snd.position[2])}</div>
        <div class="row">${num("volume", snd.volume, 0.05)}${num("distance", snd.refDistance, 0.5)}</div>`;
    }
    if (s) html += `<button data-action="delete" class="danger">Delete <kbd>Del</kbd></button>`;
    html += `<hr><button data-action="save">${this.dirty ? "Save changes" : "Saved"} <kbd>Ctrl+S</kbd></button>
      <label class="check"><input type="checkbox" data-action="blocks-in-play" ${this.showBlocksInPlay ? "checked" : ""}> Show blocks outside edit mode</label>`;
    p.innerHTML = html;

    p.querySelectorAll<HTMLButtonElement>("[data-tool]").forEach((el) => (el.onclick = () => this.setTool(el.dataset.tool as Tool)));
    p.querySelector<HTMLButtonElement>("[data-action=delete]")?.addEventListener("click", () => this.deleteSelected());
    p.querySelector<HTMLButtonElement>("[data-action=save]")?.addEventListener("click", () => void this.save());
    p.querySelector<HTMLInputElement>("[data-action=blocks-in-play]")?.addEventListener("change", (e) => {
      this.showBlocksInPlay = (e.target as HTMLInputElement).checked;
    });
    p.querySelector<HTMLInputElement>("[data-upload]")?.addEventListener("change", (e) => void this.upload((e.target as HTMLInputElement).files, m));
    p.querySelectorAll<HTMLInputElement | HTMLTextAreaElement>("[data-field]").forEach((el) => {
      el.addEventListener(el instanceof HTMLSelectElement || (el as HTMLInputElement).type === "checkbox" ? "change" : "input", () => {
        const f = el.dataset.field!;
        const v = parseFloat(el.value);
        if (m) {
          if (f === "title") m.title = el.value;
          else if (f === "text") m.text = el.value;
          else if (f === "audio") m.audio = el.value || undefined;
          else if (f === "images") m.images = el.value.split("\n").map((x) => x.trim()).filter(Boolean);
          else if (f === "kind") m.kind = el.value as "info" | "audio";
          else if (f === "spatial") m.spatial = (el as HTMLInputElement).checked;
          else if (f === "radius" && Number.isFinite(v)) m.radius = v;
          else if (Number.isFinite(v)) m.position["xyz".indexOf(f)] = v;
          this.markers.sync();
        } else if (snd) {
          if (f === "url") snd.url = el.value;
          else if (f === "volume" && Number.isFinite(v)) snd.volume = Math.max(0, v);
          else if (f === "distance" && Number.isFinite(v)) snd.refDistance = Math.max(0.1, v);
          else if (Number.isFinite(v)) snd.position["xyz".indexOf(f)] = v;
          this.rebuildBlocks();
          this.onSoundsChanged();
        } else if (b && Number.isFinite(v)) {
          if ("xyz".includes(f)) b.center["xyz".indexOf(f)] = v;
          else if (f === "yaw") b.yawDeg = v;
          else b.size[["width", "depth", "height"].indexOf(f)] = Math.max(0.02, v);
          this.rebuildBlocks();
        }
        this.dirty = true;
        const save = p.querySelector<HTMLButtonElement>("[data-action=save]");
        if (save) save.firstChild!.textContent = "Save changes ";
      });
    });
  }

  /** Copy files into the scene's assets/ folder (dev server) and attach them to the marker. */
  private async upload(files: FileList | null, m: Marker | undefined): Promise<void> {
    if (!files || !m) return;
    for (const f of Array.from(files)) {
      try {
        const r = await fetch(`/api/upload?name=${encodeURIComponent(f.name)}`, { method: "POST", body: f });
        const j = await r.json();
        if (!j.ok) throw new Error(j.error);
        if (f.type.startsWith("audio/")) m.audio = j.path;
        else (m.images ??= []).push(j.path);
        this.dirty = true;
        this.status(`Uploaded ${f.name}`);
      } catch (err) {
        this.status(`Upload failed: ${err}`);
      }
    }
    this.markers.sync();
    this.renderPanel();
  }

  async save(): Promise<void> {
    try {
      const r = await fetch("/api/scene", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(this.scene) });
      if (!r.ok) throw new Error(await r.text());
      this.dirty = false;
      this.status("Saved scene.json");
    } catch (err) {
      // Static hosting has no save endpoint: offer the file as a download instead.
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([JSON.stringify(this.scene, null, 2)], { type: "application/json" }));
      a.download = "scene.json";
      a.click();
      this.status(`Save endpoint unavailable (${err}); downloaded scene.json instead`);
    }
    this.renderPanel();
  }
}

function escapeHtml(s: string): string {
  return s.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[c]!);
}
function escapeAttr(s: string): string {
  return escapeHtml(s).replace(/"/g, "&quot;");
}
