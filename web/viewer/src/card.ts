// Info card, anchored above its marker: sliding image gallery (arrows, dots, thumbnails, fullscreen),
// a title and scrollable text. main.ts places it every frame and closes it when the marker leaves the view.
// "Fullscreen" expands it into a large centred panel over the blurred scene; × (or Esc) brings the card back.

import type { Marker } from "./types";

export class InfoCard {
  private index = 0;
  private marker: Marker | null = null;
  onClose: () => void = () => {};
  /** Called with true when the card expands to the large panel, false when it shrinks back or closes. */
  onExpand: (expanded: boolean) => void = () => {};

  constructor(private root: HTMLElement, private base: string) {
    root.addEventListener("click", (e) => {
      const t = e.target as HTMLElement;
      if (t.closest("[data-prev]")) this.show(this.index - 1);
      else if (t.closest("[data-next]")) this.show(this.index + 1);
      else if (t.closest("[data-full]")) this.expand();
      else if (t.closest("[data-collapse]")) this.collapse();
      else if (t.closest("[data-thumb]")) this.show(+(t.closest("[data-thumb]") as HTMLElement).dataset.thumb!);
    });
    // No arrow-key shortcuts here: the arrow keys move the player, and the card never pauses walking.
  }

  get isOpen(): boolean {
    return this.root.classList.contains("open");
  }

  get isFullscreen(): boolean {
    return this.root.classList.contains("fullscreen");
  }

  open(m: Marker): void {
    this.marker = m;
    this.index = 0;
    const imgs = m.images ?? [];
    const src = (u: string) => `${this.base}${encodeURI(u)}`;
    this.root.classList.toggle("no-images", imgs.length === 0);
    this.root.innerHTML = `
      ${imgs.length ? `
      <div class="gallery">
        <div class="track">${imgs.map((u) => `<div class="slide"><img class="blur" src="${src(u)}" alt=""><img class="pic" src="${src(u)}" alt=""></div>`).join("")}</div>
        <button class="full" data-full aria-label="Fullscreen"><svg viewBox="0 0 24 24" width="16" height="16"><path d="M4 9V4h5M15 4h5v5M20 15v5h-5M9 20H4v-5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></button>
        <button class="x" data-collapse aria-label="Close"><svg viewBox="0 0 24 24" width="16" height="16"><path d="M6 6l12 12M18 6L6 18" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg></button>
        ${imgs.length > 1 ? `<button class="nav prev" data-prev aria-label="Previous">‹</button>
        <button class="nav next" data-next aria-label="Next">›</button>
        <div class="dots">${imgs.map(() => "<i></i>").join("")}</div>` : ""}
      </div>` : ""}
      <div class="body">
        <div class="content"><h2></h2><div class="text"></div></div>
        ${imgs.length > 1 ? `<div class="thumbs">${imgs.map((u, i) => `<img data-thumb="${i}" src="${src(u)}" alt="">`).join("")}</div>` : ""}
      </div>`;
    (this.root.querySelector("h2") as HTMLElement).textContent = m.title;
    const text = this.root.querySelector(".text") as HTMLElement;
    text.textContent = m.text;
    // Fade the bottom edge while there is more text to scroll to.
    const more = () => text.classList.toggle("more", text.scrollTop + text.clientHeight < text.scrollHeight - 2);
    text.addEventListener("scroll", more, { passive: true });
    requestAnimationFrame(more);
    // Portrait and square pictures are shown whole over a blurred copy of themselves; wide ones fill the frame.
    this.root.querySelectorAll<HTMLImageElement>("img.pic").forEach((img) => {
      const fit = () => img.parentElement!.classList.toggle("contain", img.naturalWidth / img.naturalHeight < 1.4);
      img.complete && img.naturalWidth ? fit() : img.addEventListener("load", fit, { once: true });
    });
    this.setExpanded(false);
    this.root.classList.remove("open");
    void this.root.offsetWidth; // restart the fade-in when one card replaces another
    this.root.classList.add("open");
    this.show(0, false);
  }

  expand(): void {
    if (this.isOpen && !this.isFullscreen) this.setExpanded(true);
  }

  collapse(): void {
    if (this.isFullscreen) this.setExpanded(false);
  }

  private setExpanded(on: boolean): void {
    if (on === this.isFullscreen) return;
    this.root.classList.toggle("fullscreen", on);
    document.body.classList.toggle("card-expanded", on);
    if (on) this.root.style.transform = ""; // centred by CSS; place() is not called while expanded
    const text = this.root.querySelector(".text") as HTMLElement | null;
    text?.dispatchEvent(new Event("scroll")); // refresh the "more text" fade for the new size
    this.onExpand(on);
  }

  /** Put the card's bottom centre at (x, y) in screen px. */
  place(x: number, y: number): void {
    this.root.style.transform = `translate(${x.toFixed(1)}px, ${y.toFixed(1)}px) translate(-50%, -100%)`;
  }

  /** Next (+1) or previous (-1) picture. */
  step(delta: number): void {
    this.show(this.index + delta);
  }

  private show(i: number, animate = true): void {
    const imgs = this.marker?.images ?? [];
    if (!imgs.length) return;
    this.index = (i + imgs.length) % imgs.length;
    const track = this.root.querySelector(".track") as HTMLElement;
    track.style.transition = animate ? "" : "none";
    track.style.transform = `translateX(${-100 * this.index}%)`;
    this.root.querySelectorAll(".dots i").forEach((d, k) => d.classList.toggle("on", k === this.index));
    this.root.querySelectorAll(".thumbs img").forEach((d, k) => d.classList.toggle("on", k === this.index));
  }

  close(): void {
    if (!this.isOpen) return;
    this.setExpanded(false);
    this.root.classList.remove("open");
    this.marker = null;
    this.onClose();
  }
}
