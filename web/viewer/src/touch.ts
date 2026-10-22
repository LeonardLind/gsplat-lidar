// On-screen controls for tablets (iPad): walking and drone view only, no editing.
//   left stick   move (push it to the edge to run / fly fast)
//   right stick  look (rate based); dragging anywhere else on the picture also looks around
//   Walk | Drone switch (top right); Jump button in walk mode, up / down buttons in drone mode
//   Splat | Both | LiDAR switch below it, for scenes with LiDAR points (addLayerSwitch)
//   a tap on empty picture calls onTap (closes an open info card, unlocks audio)
// The controls write into player.analog, which Player.update reads together with the keyboard.

import type { MoveMode, Player } from "./player";

const STICK = 148; // px, diameter of a stick base
const KNOB = 62;
const DEAD = 0.12;
const RUN_AT = 0.92; // stick deflection from which the player runs
// Right-stick turn speed at full deflection (rad/s). ?look=0.5 halves it, ?look=1.5 raises it by half.
const LOOK_SCALE = Number(new URLSearchParams(location.search).get("look")) || 1;
const LOOK_YAW = 1.3 * LOOK_SCALE;
const LOOK_PITCH = 0.85 * LOOK_SCALE;
const DRAG_LOOK = 0.0048; // rad per px of direct drag
const TAP_MOVE = 9; // px
const TAP_MS = 320;

export function wantsTouchControls(): boolean {
  const q = new URLSearchParams(location.search).get("touch");
  if (q === "1") return true;
  if (q === "0") return false;
  return matchMedia("(hover: none) and (pointer: coarse)").matches;
}

function el<K extends keyof HTMLElementTagNameMap>(tag: K, cls: string, parent?: HTMLElement, text?: string): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  e.className = cls;
  if (text) e.textContent = text;
  parent?.appendChild(e);
  return e;
}

/** A fixed on-screen stick. value() is x right, y down, each -1..1 after the dead zone and a gentle curve. */
class Stick {
  readonly base: HTMLElement;
  private knob: HTMLElement;
  private id: number | null = null;
  x = 0;
  y = 0;
  mag = 0;

  constructor(parent: HTMLElement, side: "left" | "right", label: string, private onChange: () => void) {
    this.base = el("div", `tstick ${side}`, parent);
    el("span", "tlabel", this.base, label);
    this.knob = el("div", "tknob", this.base);
    this.base.addEventListener("pointerdown", (e) => {
      if (this.id !== null) return;
      this.id = e.pointerId;
      this.base.setPointerCapture(e.pointerId);
      this.base.classList.add("on");
      this.move(e);
      e.preventDefault();
    });
    this.base.addEventListener("pointermove", (e) => e.pointerId === this.id && this.move(e));
    const end = (e: PointerEvent) => {
      if (e.pointerId !== this.id) return;
      this.id = null;
      this.x = this.y = this.mag = 0;
      this.knob.style.transform = "translate(0px, 0px)";
      this.base.classList.remove("on", "run");
      this.onChange();
    };
    this.base.addEventListener("pointerup", end);
    this.base.addEventListener("pointercancel", end);
    this.base.addEventListener("lostpointercapture", end);
  }

  private move(e: PointerEvent): void {
    const r = this.base.getBoundingClientRect();
    const R = (STICK - KNOB) / 2 + 8; // how far the knob may travel
    let dx = e.clientX - (r.left + r.width / 2);
    let dy = e.clientY - (r.top + r.height / 2);
    const d = Math.hypot(dx, dy);
    if (d > R) {
      dx = (dx / d) * R;
      dy = (dy / d) * R;
    }
    this.knob.style.transform = `translate(${dx}px, ${dy}px)`;
    const m = Math.min(1, Math.hypot(dx, dy) / R);
    const shaped = m < DEAD ? 0 : Math.pow((m - DEAD) / (1 - DEAD), 1.35); // dead zone, then a gentle curve
    this.mag = m;
    this.x = m > 0 ? (dx / R / m) * shaped : 0;
    this.y = m > 0 ? (dy / R / m) * shaped : 0;
    this.base.classList.toggle("run", m >= RUN_AT);
    this.onChange();
  }
}

export class TouchControls {
  private left: Stick;
  private right: Stick;
  private modeBtns: Record<MoveMode, HTMLButtonElement>;
  private walkBtns: HTMLElement;
  private droneBtns: HTMLElement;

  constructor(
    private host: HTMLElement,
    private player: Player,
    canvas: HTMLElement,
    private opts: { onTap: () => void; onMode?: (m: MoveMode) => void },
  ) {
    document.body.classList.add("touch");
    // iOS Safari: no pinch zoom on top of the picture (touch-action: none in the CSS covers the rest, and
    // leaves the info card's text scrollable).
    for (const t of ["gesturestart", "gesturechange", "gestureend"]) document.addEventListener(t, (e) => e.preventDefault());

    this.left = new Stick(host, "left", "MOVE", () => this.sync());
    this.right = new Stick(host, "right", "LOOK", () => this.sync());

    // Walk | Drone switch.
    const sw = el("div", "tswitch", host);
    this.modeBtns = {
      walk: el("button", "", sw, "Walk"),
      fly: el("button", "", sw, "Drone"),
    };
    this.modeBtns.walk.addEventListener("click", () => this.setMode("walk"));
    this.modeBtns.fly.addEventListener("click", () => this.setMode("fly"));

    // Walk: jump. Drone: up and down.
    this.walkBtns = el("div", "tbtns walk", host);
    this.hold(el("button", "tbtn", this.walkBtns, "Jump"), (on) => (this.player.analog.jump = on));
    this.droneBtns = el("div", "tbtns drone", host);
    const down = el("button", "tbtn", this.droneBtns, "▼");
    const up = el("button", "tbtn", this.droneBtns, "▲");
    this.hold(down, () => this.updateUpDown());
    this.hold(up, () => this.updateUpDown());
    this.upBtn = up;
    this.downBtn = down;

    this.dragLook(canvas);
    this.showMode();
  }

  /** Splat | Both | LiDAR, under the Walk | Drone switch. */
  addLayerSwitch(onPick: (k: "splat" | "both" | "lidar") => void, initial: "splat" | "both" | "lidar" = "splat"): void {
    const sw = el("div", "tswitch tlayers", this.host);
    const btns = { splat: el("button", "", sw, "Splat"), both: el("button", "", sw, "Both"), lidar: el("button", "", sw, "LiDAR") };
    const pick = (k: "splat" | "both" | "lidar") => {
      for (const [n, b] of Object.entries(btns)) b.classList.toggle("on", n === k);
      onPick(k);
    };
    for (const [n, b] of Object.entries(btns)) b.addEventListener("click", () => pick(n as "splat" | "both" | "lidar"));
    pick(initial);
  }

  private upBtn!: HTMLButtonElement;
  private downBtn!: HTMLButtonElement;

  setMode(m: MoveMode): void {
    this.player.setMode(m);
    // A drone flies freely: in dense scenes (forest understory) collision would pin it under the branches.
    this.player.collide = m === "walk";
    this.player.analog.up = 0;
    this.player.analog.jump = false;
    this.showMode();
    this.opts.onMode?.(m);
  }

  /** Refresh the buttons after the mode changed from elsewhere (e.g. the F key). */
  showMode(): void {
    const fly = this.player.mode === "fly";
    this.modeBtns.walk.classList.toggle("on", !fly);
    this.modeBtns.fly.classList.toggle("on", fly);
    this.walkBtns.style.display = fly ? "none" : "flex";
    this.droneBtns.style.display = fly ? "flex" : "none";
  }

  private sync(): void {
    const a = this.player.analog;
    a.fwd = -this.left.y;
    a.side = this.left.x;
    a.run = this.left.mag >= RUN_AT;
    a.lookYaw = this.right.x * LOOK_YAW;
    a.lookPitch = -this.right.y * LOOK_PITCH;
  }

  /** A button that is "on" while a finger is on it. */
  private hold(b: HTMLButtonElement, on: (v: boolean) => void): void {
    let id: number | null = null;
    b.addEventListener("pointerdown", (e) => {
      if (id !== null) return;
      id = e.pointerId;
      b.setPointerCapture(e.pointerId);
      b.classList.add("on");
      on(true);
      e.preventDefault();
    });
    const end = (e: PointerEvent) => {
      if (e.pointerId !== id) return;
      id = null;
      b.classList.remove("on");
      on(false);
    };
    b.addEventListener("pointerup", end);
    b.addEventListener("pointercancel", end);
    b.addEventListener("lostpointercapture", end);
  }

  private updateUpDown(): void {
    this.player.analog.up = (this.upBtn.classList.contains("on") ? 1 : 0) - (this.downBtn.classList.contains("on") ? 1 : 0);
  }

  /** Drag on the picture to look around; a short still touch is a tap. */
  private dragLook(canvas: HTMLElement): void {
    let id: number | null = null;
    let lx = 0, ly = 0, sx = 0, sy = 0, t0 = 0, moved = 0;
    canvas.addEventListener("pointerdown", (e) => {
      if (e.pointerType === "mouse" || id !== null) return;
      id = e.pointerId;
      canvas.setPointerCapture(e.pointerId);
      lx = sx = e.clientX;
      ly = sy = e.clientY;
      t0 = performance.now();
      moved = 0;
    });
    canvas.addEventListener("pointermove", (e) => {
      if (e.pointerId !== id) return;
      const dx = e.clientX - lx, dy = e.clientY - ly;
      lx = e.clientX;
      ly = e.clientY;
      moved = Math.max(moved, Math.hypot(e.clientX - sx, e.clientY - sy));
      this.player.yaw -= dx * DRAG_LOOK;
      this.player.pitch = Math.max(-1.5, Math.min(1.5, this.player.pitch - dy * DRAG_LOOK));
    });
    const end = (e: PointerEvent) => {
      if (e.pointerId !== id) return;
      id = null;
      if (e.type === "pointerup" && moved < TAP_MOVE && performance.now() - t0 < TAP_MS) this.opts.onTap();
    };
    canvas.addEventListener("pointerup", end);
    canvas.addEventListener("pointercancel", end);
  }
}
