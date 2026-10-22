// Tape measure (T): two clicks on surfaces give the distance between them, with its horizontal and vertical parts.
// Only in metric scenes (LiDAR frame); with an approximate scale a number in metres would be misleading.
// A click hits the collision voxels (from the LiDAR in LiDAR scenes, 8 cm) and then snaps to the nearest LiDAR
// point within 12 cm, so the ends sit on real scanned surfaces.

import * as THREE from "three";
import type { CollisionWorld } from "./collision";
import type { LidarLayer } from "./lidar";

export class Measure {
  active = false;
  private a: THREE.Vector3 | null = null;
  private b: THREE.Vector3 | null = null;
  private readonly group = new THREE.Group();
  private readonly line: THREE.Line;
  private readonly dots: THREE.Mesh[];
  private readonly label: HTMLElement;
  private readonly raycaster = new THREE.Raycaster();

  constructor(
    scene: THREE.Scene,
    private camera: THREE.PerspectiveCamera,
    private world: CollisionWorld,
    private lidar: () => LidarLayer | null,
    host: HTMLElement,
  ) {
    const mat = new THREE.LineBasicMaterial({ color: 0xffd400, depthTest: false, transparent: true });
    this.line = new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(), new THREE.Vector3()]), mat);
    this.line.renderOrder = 10;
    const dotMat = new THREE.MeshBasicMaterial({ color: 0xffd400, depthTest: false, transparent: true });
    this.dots = [0, 1].map(() => {
      const m = new THREE.Mesh(new THREE.SphereGeometry(0.025, 12, 8), dotMat);
      m.renderOrder = 10;
      return m;
    });
    this.group.add(this.line, ...this.dots);
    this.group.visible = false;
    scene.add(this.group);
    this.label = document.createElement("div");
    this.label.className = "measure-label";
    this.label.style.display = "none";
    host.appendChild(this.label);
  }

  toggle(): boolean {
    this.active = !this.active;
    if (!this.active) this.clear();
    return this.active;
  }

  clear(): void {
    this.a = this.b = null;
    this.group.visible = false;
    this.label.style.display = "none";
  }

  /** ndc: the clicked point in normalised device coordinates (0, 0 = the crosshair). Returns a status text. */
  click(ndc: THREE.Vector2): string {
    this.raycaster.setFromCamera(ndc, this.camera);
    const { origin: o, direction: d } = this.raycaster.ray;
    const hit = this.world.raycast([o.x, o.y, o.z], [d.x, d.y, d.z], 40);
    if (!hit) return "Nothing there to measure to";
    const p = this.snap(new THREE.Vector3(...hit));
    if (!this.a || this.b) {
      this.a = p;
      this.b = null;
      this.dots[0].position.copy(p);
      this.dots[1].visible = false;
      this.line.visible = false;
      this.group.visible = true;
      this.label.style.display = "none";
      return "Measure: first point set, click the second";
    }
    this.b = p;
    this.dots[1].position.copy(p);
    this.dots[1].visible = true;
    this.line.geometry.setFromPoints([this.a, this.b]);
    this.line.visible = true;
    const d3 = this.a.distanceTo(this.b);
    const dz = Math.abs(this.b.z - this.a.z);
    const dh = Math.hypot(this.b.x - this.a.x, this.b.y - this.a.y);
    this.label.innerHTML = `<b>${d3.toFixed(2)} m</b><span>horizontal ${dh.toFixed(2)} · vertical ${dz.toFixed(2)}</span>`;
    this.label.style.display = "";
    return `Distance ${d3.toFixed(2)} m (horizontal ${dh.toFixed(2)} m, vertical ${dz.toFixed(2)} m)`;
  }

  /** The nearest LiDAR point within 12 cm of a voxel hit (the voxel surface is only 8 cm accurate). */
  private snap(p: THREE.Vector3): THREE.Vector3 {
    const l = this.lidar();
    if (!l) return p;
    const pos = l.points.geometry.getAttribute("position").array as Float32Array;
    let best = 0.12 * 0.12, bi = -1;
    for (let i = 0; i < pos.length; i += 3) {
      const dx = pos[i] - p.x, dy = pos[i + 1] - p.y, dz = pos[i + 2] - p.z;
      const d2 = dx * dx + dy * dy + dz * dz;
      if (d2 < best) { best = d2; bi = i; }
    }
    return bi < 0 ? p : new THREE.Vector3(pos[bi], pos[bi + 1], pos[bi + 2]);
  }

  /** Keep the label at the middle of the line (call every frame). */
  update(w: number, h: number): void {
    if (!this.a || !this.b) return;
    const m = this.a.clone().add(this.b).multiplyScalar(0.5).project(this.camera);
    const front = m.z < 1;
    this.label.style.display = front ? "" : "none";
    this.label.style.transform = `translate(${((m.x + 1) / 2) * w}px, ${((1 - m.y) / 2) * h}px) translate(-50%, -130%)`;
  }
}
