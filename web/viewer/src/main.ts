// Splat explorer: walk through a Gaussian splat with collision, pop-up markers and an edit mode.
// Scene data comes from /scene/scene.json (served by the dev server from the pipeline's export folder).

import * as THREE from "three";
import { SparkRenderer, SplatMesh } from "@sparkjsdev/spark";
import { AudioBar, AudioLayer } from "./audio";
import { InfoCard } from "./card";
import { CollisionWorld, VoxelGrid } from "./collision";
import { Editor } from "./editor";
import { MarkerLayer, markerKind } from "./markers";
import { Player } from "./player";
import { TouchControls, wantsTouchControls } from "./touch";
import type { CollisionFile, Marker, SceneFile } from "./types";

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const canvas = $<HTMLCanvasElement>("view");
const hud = $("hud");
const statusEl = $("status");
const loading = $("loading");

function status(msg: string): void {
  statusEl.textContent = msg;
  statusEl.classList.add("show");
  clearTimeout((status as unknown as { t?: number }).t);
  (status as unknown as { t?: number }).t = window.setTimeout(() => statusEl.classList.remove("show"), 2500);
}

async function loadJson<T>(url: string): Promise<T> {
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
  return (await r.json()) as T;
}

async function main(): Promise<void> {
  const scene = await loadJson<SceneFile>("/scene/scene.json");
  document.title = `${scene.name} – splat explorer`;

  // Tablet: on-screen controls (walk and drone only; no editing). ?touch=1 forces them on, ?touch=0 off.
  const touchMode = wantsTouchControls();
  const dprCap = Number(new URLSearchParams(location.search).get("dpr")) || (touchMode ? 1.25 : 1.5);
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: false });
  renderer.setPixelRatio(Math.min(devicePixelRatio, dprCap));
  const three = new THREE.Scene();
  three.background = new THREE.Color(0x101114);
  const camera = new THREE.PerspectiveCamera(70, 1, 0.05, 500);

  const spark = new SparkRenderer({ renderer });
  three.add(spark);
  const splat = new SplatMesh({ url: `/scene/${scene.splat.url}` });
  const tf = scene.splat.transform;
  if (tf) {
    splat.quaternion.set(...tf.quaternion_xyzw);
    splat.scale.setScalar(tf.scale);
    splat.position.set(...tf.position);
  }
  three.add(splat);

  let grid: VoxelGrid | null = null;
  if (scene.collision?.url) {
    try {
      grid = new VoxelGrid(await loadJson<CollisionFile>(`/scene/${scene.collision.url}`));
    } catch (e) {
      status(`No collision data (${e}); walking on the floor plane only`);
    }
  }
  const world = new CollisionWorld(grid, scene.blocks);
  const player = new Player(camera, canvas, world, scene.player.eyeHeight, scene.player.radius, scene.player.stepHeight);
  const s = scene.start;
  player.placeAt(s.position[0], s.position[1], s.position[2], (s.yawDeg * Math.PI) / 180);

  // Debug view of the collision voxels (V).
  let voxelView: THREE.InstancedMesh | null = null;
  const toggleVoxels = () => {
    if (!grid) return status("No collision voxels in this scene");
    if (!voxelView) {
      const cells = [...grid.occupied()];
      voxelView = new THREE.InstancedMesh(
        new THREE.BoxGeometry(grid.voxel * 0.92, grid.voxel * 0.92, grid.voxel * 0.92),
        new THREE.MeshBasicMaterial({ color: 0xff3d6e, transparent: true, opacity: 0.25, depthWrite: false }),
        cells.length,
      );
      const m = new THREE.Matrix4();
      cells.forEach((c, i) => voxelView!.setMatrixAt(i, m.makeTranslation(c[0], c[1], c[2])));
      voxelView.visible = false;
      three.add(voxelView);
    }
    voxelView.visible = !voxelView.visible;
    status(voxelView.visible ? `Collision voxels shown (${voxelView.count})` : "Collision voxels hidden");
  };

  scene.sounds ??= [];
  const audio = new AudioLayer(camera, three, "/scene/");
  const markers = new MarkerLayer($("markers"), scene.markers);
  markers.sync();
  const editor = new Editor(scene, three, camera, canvas, world, markers, $("panel"), status);
  editor.onSoundsChanged = () => void audio.syncSounds(scene.sounds ?? []);

  const card = new InfoCard($("card"), "/scene/");
  const bar = new AudioBar($("audiobar"));
  // An info marker opens its card (and plays its sound, if any); an audio marker plays in the audio bar.
  // Cards do not pause anything: the player keeps walking and looking around; the card follows its
  // marker and closes when the marker leaves the view. Wheel = next/previous picture, E = close.
  let cardMarker: Marker | null = null;
  const openPopup = (m: Marker) => {
    if (editor.active) return editor.select({ kind: "marker", id: m.id });
    void audio.unlock(scene.sounds ?? []);
    markers.activeId = m.id;
    if (markerKind(m) === "info") {
      card.open(m);
      cardMarker = m;
    }
    if (m.audio) audio.playNarration(m, bar);
  };
  const closePopup = () => {
    const wasInfo = card.isOpen;
    card.close();
    if (wasInfo && cardMarker?.audio) bar.stop();
    cardMarker = null;
    markers.activeId = null;
  };
  card.onClose = () => {
    if (cardMarker?.audio) bar.stop();
    cardMarker = null;
    markers.activeId = null;
  };
  // Tablets have no pointer lock (iPad Safari has no requestPointerLock at all).
  const lockPointer = () => {
    if (touchMode || typeof canvas.requestPointerLock !== "function") return;
    void Promise.resolve(canvas.requestPointerLock()).catch(() => {});
  };
  // Expanded card: free the mouse (a normal cursor for the panel) and pause walking; shrinking back
  // re-locks the pointer if the player was looking around before.
  let relockAfterExpand = false;
  card.onExpand = (on) => {
    if (on) {
      relockAfterExpand = player.locked;
      if (player.locked) document.exitPointerLock();
      return;
    }
    if (cardMarker) { // back above the marker right away, not one frame later from the top-left corner
      const p = markers.project(cardMarker, camera, innerWidth, innerHeight);
      card.place(p.x, p.y - p.r - 8);
    }
    if (relockAfterExpand && card.isOpen) lockPointer();
    relockAfterExpand = false;
  };
  $("card-backdrop").addEventListener("click", () => card.collapse());

  // Crosshair aiming: while looking around (pointer locked) every click lands on the canvas, so the
  // card button, thumbnail or marker under the crosshair is highlighted and gets the click instead.
  let aimHit: HTMLElement | null = null; // whatever is under the crosshair
  let aimed: HTMLElement | null = null; // the clickable thing under it (pointer locked only)
  const updateAim = () => {
    aimHit = document.elementFromPoint(innerWidth / 2, innerHeight / 2) as HTMLElement | null;
    const target = player.locked && !editor.active
      ? (aimHit?.closest("#card button, #card [data-thumb], .marker") as HTMLElement | null) : null;
    if (target !== aimed) {
      aimed?.classList.remove("aimed");
      target?.classList.add("aimed");
      aimed = target;
    }
    cross.classList.toggle("aim", target !== null);
  };

  addEventListener("wheel", (e) => {
    // Only while looking around (pointer locked); with a free mouse the wheel scrolls the card text.
    // Aiming at the text scrolls it; anywhere else the wheel changes the picture.
    if (!card.isOpen || editor.active || !player.locked) return;
    const text = aimHit?.closest("#card .text");
    if (text) text.scrollBy({ top: e.deltaY });
    else card.step(e.deltaY > 0 ? 1 : -1);
  }, { passive: true });
  markers.onOpen = openPopup;

  // Touch controls: a tap on empty picture closes the card (there is no E key) and unlocks audio.
  const touch = touchMode
    ? new TouchControls($("touch"), player, canvas, {
        onTap: () => {
          void audio.unlock(scene.sounds ?? []);
          if (card.isOpen && !card.isFullscreen) closePopup();
        },
      })
    : null;

  canvas.addEventListener("click", () => {
    void audio.unlock(scene.sounds ?? []);
    if (player.locked && aimed) return aimed.click();
    if (!editor.active) lockPointer();
  });
  $("markers").addEventListener("click", () => void audio.unlock(scene.sounds ?? []), true);
  // In edit mode, look around by dragging with the right mouse button.
  let dragging = false;
  canvas.addEventListener("contextmenu", (e) => e.preventDefault());
  canvas.addEventListener("mousedown", (e) => editor.active && e.button === 2 && (dragging = true));
  addEventListener("mouseup", () => (dragging = false));
  addEventListener("mousemove", (e) => {
    if (!dragging) return;
    player.yaw -= e.movementX * 0.003;
    player.pitch = THREE.MathUtils.clamp(player.pitch - e.movementY * 0.003, -1.5, 1.5);
  });

  addEventListener("keydown", (e) => {
    if ((e.target as HTMLElement)?.closest?.("input, textarea")) return;
    switch (e.code) {
      case "Tab":
        e.preventDefault();
        if (document.pointerLockElement) document.exitPointerLock();
        editor.setActive(!editor.active);
        closePopup();
        break;
      case "KeyF":
        status(`Mode: ${player.toggleMode()}`);
        touch?.showMode();
        break;
      case "KeyG":
        player.collide = !player.collide;
        status(`Collision ${player.collide ? "on" : "off"}`);
        break;
      case "KeyV":
        toggleVoxels();
        break;
      case "KeyE":
        if (card.isOpen) closePopup();
        else if (markers.nearest) openPopup(markers.nearest);
        break;
      case "Escape":
        if (card.isFullscreen) {
          card.collapse();
          break;
        }
        closePopup();
        bar.stop();
        break;
      case "KeyM":
        status(audio.toggleMute() ? "Sound off" : "Sound on");
        break;
      case "KeyH":
        hud.classList.toggle("collapsed");
        break;
      case "KeyR":
        player.placeAt(s.position[0], s.position[1], s.position[2], (s.yawDeg * Math.PI) / 180);
        status("Back to the start");
        break;
    }
  });

  const resize = () => {
    const w = innerWidth, h = innerHeight;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  };
  addEventListener("resize", resize);
  resize();

  splat.initialized.then(() => loading.classList.add("done")).catch((e: unknown) => {
    loading.textContent = `Could not load the splat: ${e}`;
  });

  // Gaze to open: keep the crosshair on a marker for GAZE_SECONDS and it opens (card or audio).
  const GAZE_SECONDS = 1;
  const IDLE_FRACTION = 0.1;
  const cross = $("crosshair");
  const ring = cross.querySelector(".ring") as SVGCircleElement;
  const RING_LEN = 2 * Math.PI * 12;
  let gazeId: string | null = null;
  let gazeTime = 0;
  let gazeBlocked: string | null = null; // the marker just opened: needs a look away before it can fire again
  const updateGaze = (dt: number) => {
    // No gazing through the card (reading it must not open a marker behind it) or while it is expanded.
    const g = !editor.active && !card.isFullscreen && !aimHit?.closest("#card") ? markers.gazed : null;
    const target = g && g.id !== markers.activeId ? g : null; // the open marker cannot re-fire
    if (!target || target.id === gazeBlocked) {
      if (!target) gazeBlocked = null;
      gazeId = null;
      gazeTime = 0;
    } else if (target.id !== gazeId) {
      gazeId = target.id;
      gazeTime = 0;
    } else {
      gazeTime += dt;
      if (gazeTime >= GAZE_SECONDS) {
        gazeBlocked = target.id;
        gazeId = null;
        gazeTime = 0;
        openPopup(target);
      }
    }
    cross.classList.toggle("gazing", gazeId !== null);
    // Idle: just the dot (the ring is hidden by CSS); gazing: the ring fills up from a short arc to a full circle.
    const shown = gazeId !== null ? Math.max(gazeTime / GAZE_SECONDS, IDLE_FRACTION) : 0;
    ring.style.strokeDashoffset = String(RING_LEN * (1 - Math.min(shown, 1)));
  };

  // Debug/test handle (used by tools/shot_ui.mjs to aim at markers).
  (window as unknown as { __gsl: unknown }).__gsl = { player, markers, card, bar };

  const modeEl = $("mode");
  const hintEl = $("near-hint");
  let last = performance.now();
  renderer.setAnimationLoop((now) => {
    const dt = (now - last) / 1000;
    last = now;
    if (!card.isFullscreen) player.update(dt); // the expanded card pauses walking
    player.applyToCamera();
    const sel = editor.selection?.kind === "marker" ? editor.selection.id : undefined;
    markers.update(camera, player.eye(), innerWidth, innerHeight, sel);
    // The card sits just above its marker and follows it; it closes once the marker leaves the view
    // (looking away or walking past it) or the player walks far away. While the crosshair is on the card
    // it stays open, so its top (fullscreen button) can be aimed at even if that pushes the marker off-screen.
    if (cardMarker && card.isOpen && !card.isFullscreen) {
      const p = markers.project(cardMarker, camera, innerWidth, innerHeight);
      const out = 40;
      const offView = !p.front || p.x < -out || p.x > innerWidth + out || p.y < -out || p.y > innerHeight + out;
      const reading = p.front && !!aimHit?.closest("#card"); // crosshair on the card (as of last frame)
      if ((offView && !reading) || p.dist > markers.gazeRange + 2) closePopup();
      else card.place(p.x, p.y - p.r - 8);
    }
    bar.update();
    updateAim();
    updateGaze(dt);
    hintEl.textContent = editor.active || card.isFullscreen ? ""
      : touchMode ? (card.isOpen ? "" : markers.nearest ? `Tap or look at the marker: ${markers.nearest.title}` : "")
      : card.isOpen ?((cardMarker?.images?.length ?? 0) > 1 ? "Scroll: next picture · E: close" : "E: close")
      : markers.nearest ? `Press E: ${markers.nearest.title}` : "";
    modeEl.textContent = `${editor.active ? "EDIT" : player.mode.toUpperCase()} · collision ${player.collide ? "on" : "off"} · scale ${scene.frame.scale}`;
    renderer.render(three, camera);
  });
}

main().catch((e) => {
  loading.textContent = `Could not start: ${e}. Is GSL_SCENE_DIR set to an exported scene folder?`;
  console.error(e);
});
