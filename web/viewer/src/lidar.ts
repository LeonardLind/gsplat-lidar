// LiDAR layer: the scanner's points drawn together with the splat (scenes trained in the LiDAR frame,
// python -m app export writes lidar.bin and scene.lidar). Opaque points write depth, so the splat is hidden
// behind them where they are in front; with lower opacity they blend over it instead.
//
// lidar.bin: little-endian uint32 count, float32 xyz (count x 3), uint8 rgb (count x 3), uint8 intensity (count).

import * as THREE from "three";

export type LidarColour = "rgb" | "intensity" | "height";
const COLOURS: LidarColour[] = ["rgb", "intensity", "height"];

const vertex = /* glsl */ `
  attribute vec3 rgb;
  attribute float intensity;
  uniform float uSize;      // point size in metres
  uniform float uScale;     // viewport height / (2 tan(fov / 2)): metres at distance 1 -> pixels
  uniform int uMode;        // 0 rgb, 1 intensity, 2 height
  uniform vec2 uHeight;     // z range for the height colours
  uniform float uClip;      // points above this z are hidden (cut away the ceiling)
  varying vec3 vColour;
  varying float vHide;
  vec3 ramp(float t) {      // blue -> cyan -> yellow -> red
    t = clamp(t, 0.0, 1.0);
    return clamp(vec3(1.5 * t - 0.25, 1.0 - abs(2.0 * t - 1.0) * 0.6, 1.2 - 1.6 * t), 0.0, 1.0);
  }
  void main() {
    vHide = position.z > uClip ? 1.0 : 0.0;
    vColour = uMode == 0 ? rgb : uMode == 1 ? vec3(intensity) : ramp((position.z - uHeight.x) / (uHeight.y - uHeight.x));
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    gl_Position = projectionMatrix * mv;
    gl_PointSize = clamp(uSize * uScale / max(-mv.z, 0.05), 1.0, 14.0);
  }`;

const fragment = /* glsl */ `
  uniform float uOpacity;
  varying vec3 vColour;
  varying float vHide;
  void main() {
    if (vHide > 0.5) discard;
    vec2 d = gl_PointCoord - 0.5;
    if (dot(d, d) > 0.25) discard;   // round points
    gl_FragColor = vec4(vColour, uOpacity);
  }`;

export class LidarLayer {
  readonly points: THREE.Points;
  private readonly mat: THREE.ShaderMaterial;
  private colourIndex = 0;
  readonly zMin: number;
  readonly zMax: number;

  private constructor(geom: THREE.BufferGeometry, zMin: number, zMax: number) {
    this.zMin = zMin;
    this.zMax = zMax;
    this.mat = new THREE.ShaderMaterial({
      vertexShader: vertex,
      fragmentShader: fragment,
      uniforms: {
        uSize: { value: 0.035 },
        uScale: { value: 500 },
        uMode: { value: 0 },
        uHeight: { value: new THREE.Vector2(zMin, zMax) },
        uClip: { value: zMax + 1 },
        uOpacity: { value: 1 },
      },
    });
    this.points = new THREE.Points(geom, this.mat);
    this.points.frustumCulled = false;
    this.points.visible = false;
    this.points.renderOrder = -1; // before the splat, so the splat is depth-tested against opaque points
  }

  static async load(url: string): Promise<LidarLayer> {
    const r = await fetch(url);
    if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
    const buf = await r.arrayBuffer();
    const n = new DataView(buf).getUint32(0, true);
    const xyz = new Float32Array(buf, 4, n * 3);
    const rgb = new Uint8Array(buf, 4 + 12 * n, n * 3);
    const inten = new Uint8Array(buf, 4 + 15 * n, n);
    const geom = new THREE.BufferGeometry();
    geom.setAttribute("position", new THREE.BufferAttribute(xyz, 3));
    geom.setAttribute("rgb", new THREE.BufferAttribute(rgb, 3, true));
    geom.setAttribute("intensity", new THREE.BufferAttribute(inten, 1, true));
    // height colours over the 1st-99th percentile of z (a sample is enough)
    const zs: number[] = [];
    for (let i = 0; i < n; i += Math.max(1, Math.floor(n / 20000))) zs.push(xyz[3 * i + 2]);
    zs.sort((a, b) => a - b);
    return new LidarLayer(geom, zs[Math.floor(zs.length * 0.01)], zs[Math.floor(zs.length * 0.99)]);
  }

  get visible(): boolean { return this.points.visible; }
  set visible(v: boolean) { this.points.visible = v; }
  get colour(): LidarColour { return COLOURS[this.colourIndex]; }
  get opacity(): number { return this.mat.uniforms.uOpacity.value; }
  get clip(): number { return this.mat.uniforms.uClip.value; }
  get count(): number { return this.points.geometry.getAttribute("position").count; }

  nextColour(): LidarColour {
    this.colourIndex = (this.colourIndex + 1) % COLOURS.length;
    this.mat.uniforms.uMode.value = this.colourIndex;
    return this.colour;
  }

  /** 1 -> 0.6 -> 0.3 -> 1: opaque points hide the splat behind them, lower values blend over it. */
  nextOpacity(): number {
    const steps = [1, 0.6, 0.3];
    const o = steps[(steps.indexOf(this.opacity) + 1) % steps.length];
    this.mat.uniforms.uOpacity.value = o;
    this.mat.transparent = o < 1;
    this.mat.depthWrite = o >= 1;
    this.mat.needsUpdate = true;
    return o;
  }

  /** Move the ceiling cut by dz (points above it are hidden); returns the cut height, or null when off. */
  moveClip(dz: number): number | null {
    const top = this.zMax + 1;
    let c = Math.min(this.clip, this.zMax) + dz;
    if (c >= this.zMax) c = top;
    c = Math.max(c, this.zMin + 0.1);
    this.mat.uniforms.uClip.value = c;
    return c >= top ? null : c;
  }

  setSize(metres: number): void { this.mat.uniforms.uSize.value = metres; }

  /** Call on resize: point sizes are in metres, converted with the camera's projection. */
  updateScale(camera: THREE.PerspectiveCamera, heightPx: number): void {
    this.mat.uniforms.uScale.value = heightPx / (2 * Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2));
  }
}
