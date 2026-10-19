// First-person player in a +Z-up world: walk mode (gravity, collision, step-up) and fly mode.
// Mouse look with pointer lock, WASD to move, Shift to run, Space to jump (walk) or rise (fly), C to sink (fly).

import * as THREE from "three";
import type { CollisionWorld } from "./collision";

export type MoveMode = "walk" | "fly";

export class Player {
  readonly feet = new THREE.Vector3();
  yaw = 0; // radians, 0 = +X, counter-clockwise seen from above
  pitch = 0;
  mode: MoveMode = "walk";
  collide = true;
  walkSpeed = 1.4;
  flySpeed = 2.5;
  /** Analog input from the touch controls (all zero/false when unused). fwd/side/up are -1..1; look* are rad/s. */
  readonly analog = { fwd: 0, side: 0, up: 0, run: false, jump: false, lookYaw: 0, lookPitch: 0 };
  private vz = 0;
  private grounded = false;
  private keys = new Set<string>();

  constructor(
    private camera: THREE.PerspectiveCamera,
    private dom: HTMLElement,
    private world: CollisionWorld,
    public eyeHeight: number,
    public radius: number,
    public stepHeight: number,
  ) {
    camera.up.set(0, 0, 1);
    addEventListener("keydown", (e) => {
      if ((e.target as HTMLElement)?.closest?.("input, textarea")) return;
      this.keys.add(e.code);
    });
    addEventListener("keyup", (e) => this.keys.delete(e.code));
    addEventListener("blur", () => this.keys.clear());
    dom.addEventListener("mousemove", (e) => {
      if (document.pointerLockElement !== dom) return;
      this.yaw -= e.movementX * 0.0022;
      this.pitch = THREE.MathUtils.clamp(this.pitch - e.movementY * 0.0022, -1.5, 1.5);
    });
  }

  get locked(): boolean {
    return document.pointerLockElement === this.dom;
  }

  eye(out = new THREE.Vector3()): THREE.Vector3 {
    return out.copy(this.feet).setZ(this.feet.z + this.eyeHeight);
  }

  forward(out = new THREE.Vector3()): THREE.Vector3 {
    return out.set(Math.cos(this.yaw) * Math.cos(this.pitch), Math.sin(this.yaw) * Math.cos(this.pitch), Math.sin(this.pitch));
  }

  placeAt(x: number, y: number, z: number, yaw: number): void {
    this.feet.set(x, y, z);
    this.yaw = yaw;
    this.pitch = 0;
    this.vz = 0;
    if (this.mode === "walk") this.snapToGround(1.0);
  }

  toggleMode(): MoveMode {
    return this.setMode(this.mode === "walk" ? "fly" : "walk");
  }

  setMode(mode: MoveMode): MoveMode {
    if (mode === this.mode) return mode;
    this.mode = mode;
    this.vz = 0;
    if (mode === "walk") this.snapToGround(3.0);
    return mode;
  }

  private snapToGround(searchUp: number): void {
    const g = this.world.groundZ(this.feet.x, this.feet.y, this.radius, this.feet.z + searchUp);
    if (Number.isFinite(g)) this.feet.z = g;
  }

  private blocked(x: number, y: number, z: number): boolean {
    if (!this.collide) return false;
    return this.world.cylinderBlocked(x, y, this.radius, z + this.stepHeight, z + this.eyeHeight + 0.1);
  }

  update(dt: number): void {
    dt = Math.min(dt, 0.05);
    const k = this.keys, a = this.analog;
    if (a.lookYaw || a.lookPitch) { // touch look stick
      this.yaw -= a.lookYaw * dt;
      this.pitch = THREE.MathUtils.clamp(this.pitch + a.lookPitch * dt, -1.5, 1.5);
    }
    const run = k.has("ShiftLeft") || k.has("ShiftRight") || a.run ? 2.2 : 1;
    const clamp1 = (v: number) => Math.max(-1, Math.min(1, v));
    const fwd = clamp1((k.has("KeyW") || k.has("ArrowUp") ? 1 : 0) - (k.has("KeyS") || k.has("ArrowDown") ? 1 : 0) + a.fwd);
    const side = clamp1((k.has("KeyD") || k.has("ArrowRight") ? 1 : 0) - (k.has("KeyA") || k.has("ArrowLeft") ? 1 : 0) + a.side);
    const cy = Math.cos(this.yaw), sy = Math.sin(this.yaw);

    if (this.mode === "fly") {
      const f = this.forward();
      const right = new THREE.Vector3(sy, -cy, 0);
      const up = clamp1((k.has("Space") ? 1 : 0) - (k.has("KeyC") ? 1 : 0) + a.up);
      const v = f.multiplyScalar(fwd).addScaledVector(right, side).add(new THREE.Vector3(0, 0, up));
      // Full speed for keys (length >= 1); a partly pushed touch stick moves proportionally slower.
      if (v.lengthSq() > 1) v.normalize();
      v.multiplyScalar(this.flySpeed * run * dt);
      this.tryMove(v.x, v.y);
      const nz = this.feet.z + v.z;
      if (!this.blocked(this.feet.x, this.feet.y, nz - this.stepHeight)) this.feet.z = nz;
      return;
    }

    // Walk: horizontal move with sliding, then gravity and step-up.
    let mx = cy * fwd + sy * side, my = sy * fwd - cy * side;
    const len = Math.hypot(mx, my);
    if (len > 0) {
      const sc = (this.walkSpeed * run * dt) / Math.max(len, 1); // keys: full speed; a half-pushed stick: half speed
      this.tryMove(mx * sc, my * sc);
    }
    if (this.grounded && (k.has("Space") || a.jump)) {
      this.vz = 3.2;
      this.grounded = false;
    }
    this.vz -= 9.81 * dt;
    let z = this.feet.z + this.vz * dt;
    const ground = this.world.groundZ(this.feet.x, this.feet.y, this.radius, this.feet.z + this.stepHeight);
    if (z <= ground) {
      z = ground;
      this.vz = 0;
      this.grounded = true;
    } else {
      this.grounded = false;
    }
    this.feet.z = z;
  }

  /** Move horizontally; if blocked, slide along X or Y alone. */
  private tryMove(dx: number, dy: number): void {
    const { x, y, z } = this.feet;
    if (!this.blocked(x + dx, y + dy, z)) {
      this.feet.x += dx;
      this.feet.y += dy;
    } else if (!this.blocked(x + dx, y, z)) {
      this.feet.x += dx;
    } else if (!this.blocked(x, y + dy, z)) {
      this.feet.y += dy;
    }
  }

  applyToCamera(): void {
    const eye = this.eye();
    this.camera.position.copy(eye);
    this.camera.lookAt(eye.add(this.forward()));
    // Now, not at render time: markers and the card are projected with this frame's camera, so they do not lag the splat.
    this.camera.updateMatrixWorld();
  }
}
