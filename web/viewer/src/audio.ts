// Spatial audio: looping positional sound sources plus a one-shot/loop sound per marker card.
// Browsers only allow audio after a user gesture, so everything starts on the first click.

import * as THREE from "three";
import type { Marker, Sound } from "./types";

export class AudioLayer {
  readonly listener = new THREE.AudioListener();
  private loader = new THREE.AudioLoader();
  private buffers = new Map<string, Promise<AudioBuffer>>();
  private ambient = new Map<string, THREE.PositionalAudio>();
  private card: THREE.PositionalAudio | null = null;
  private narration: HTMLAudioElement | null = null;
  private group = new THREE.Group();
  unlocked = false;
  muted = false;

  constructor(camera: THREE.Camera, scene: THREE.Scene, private base: string) {
    camera.add(this.listener);
    scene.add(this.group);
  }

  private buffer(url: string): Promise<AudioBuffer> {
    let b = this.buffers.get(url);
    if (!b) {
      b = this.loader.loadAsync(`${this.base}${url}`);
      this.buffers.set(url, b);
    }
    return b;
  }

  /** Call from a user gesture (click). Starts the ambient sources. */
  async unlock(sounds: Sound[]): Promise<void> {
    if (this.unlocked) return;
    this.unlocked = true;
    await this.listener.context.resume();
    await this.syncSounds(sounds);
  }

  async syncSounds(sounds: Sound[]): Promise<void> {
    if (!this.unlocked) return;
    const ids = new Set(sounds.map((s) => s.id));
    for (const [id, a] of this.ambient) {
      if (!ids.has(id)) {
        a.stop();
        this.group.remove(a);
        this.ambient.delete(id);
      }
    }
    for (const s of sounds) {
      let a = this.ambient.get(s.id);
      if (!a) {
        a = new THREE.PositionalAudio(this.listener);
        this.ambient.set(s.id, a);
        this.group.add(a);
        try {
          a.setBuffer(await this.buffer(s.url));
          a.setLoop(true);
          a.play();
        } catch (e) {
          console.warn(`sound ${s.url} failed`, e);
        }
      }
      a.position.set(...s.position);
      a.setRefDistance(s.refDistance);
      a.setRolloffFactor(1.5);
      a.setVolume(s.volume);
    }
  }

  /** Narration of a marker in the audio bar; positional when the marker says so. */
  playNarration(m: Marker, bar: AudioBar): void {
    this.stopCard();
    if (!m.audio) return;
    const el = new Audio(`${this.base}${encodeURI(m.audio)}`);
    el.crossOrigin = "anonymous";
    if (m.spatial) {
      const a = new THREE.PositionalAudio(this.listener);
      a.position.set(...m.position);
      a.setRefDistance(2);
      a.setMediaElementSource(el);
      this.group.add(a);
      this.card = a;
    } else {
      const src = this.listener.context.createMediaElementSource(el);
      src.connect(this.listener.getInput());
    }
    this.narration = el;
    bar.attach(el, m.title, () => this.stopCard());
    void this.listener.context.resume().then(() => el.play()).catch((e) => console.warn("narration failed", e));
  }

  stopCard(): void {
    if (this.narration) {
      this.narration.pause();
      this.narration = null;
    }
    if (this.card) {
      this.group.remove(this.card);
      this.card = null;
    }
  }

  toggleMute(): boolean {
    this.muted = !this.muted;
    this.listener.setMasterVolume(this.muted ? 0 : 1);
    return this.muted;
  }
}

/** The bottom audio bar: title, progress, time left and a stop button. */
export class AudioBar {
  private el: HTMLAudioElement | null = null;
  private onStop: () => void = () => {};

  constructor(private root: HTMLElement) {
    root.innerHTML = `<div class="wave"><i></i></div><span class="title"></span><span class="time"></span>
      <button class="stop" aria-label="Stop"><svg viewBox="0 0 24 24" width="14" height="14"><rect x="5" y="5" width="14" height="14" rx="2" fill="currentColor"/></svg></button>`;
    root.querySelector("button")!.addEventListener("click", () => this.stop());
  }

  attach(el: HTMLAudioElement, title: string, onStop: () => void): void {
    this.el = el;
    this.onStop = onStop;
    (this.root.querySelector(".title") as HTMLElement).textContent = title;
    this.root.classList.add("open");
    el.addEventListener("ended", () => this.stop());
  }

  stop(): void {
    if (!this.el) return;
    this.el = null;
    this.root.classList.remove("open");
    this.onStop();
  }

  /** Call every frame. */
  update(): void {
    const el = this.el;
    if (!el) return;
    const d = Number.isFinite(el.duration) ? el.duration : 0;
    const left = Math.max(0, d - el.currentTime);
    (this.root.querySelector(".time") as HTMLElement).textContent = d ? `${Math.floor(left / 60)}:${String(Math.floor(left % 60)).padStart(2, "0")}` : "…";
    (this.root.querySelector(".wave i") as HTMLElement).style.width = d ? `${(100 * el.currentTime) / d}%` : "0%";
  }
}
