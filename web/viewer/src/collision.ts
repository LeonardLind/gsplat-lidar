// Collision world: occupancy voxels derived from the splat, plus user-placed blocks.
// The player is a vertical cylinder (radius, from feet + stepHeight up to the head).
// Never collides with the splat itself (PLAN §1.10): it only uses these coarse proxies.

import type { Block, CollisionFile, Vec3 } from "./types";

export class VoxelGrid {
  readonly origin: Vec3;
  readonly voxel: number;
  readonly dims: [number, number, number];
  readonly floorZ: number;
  private bits: Uint8Array;

  constructor(f: CollisionFile) {
    this.origin = f.origin;
    this.voxel = f.voxel;
    this.dims = f.dims;
    this.floorZ = f.floorZ;
    const bin = atob(f.data);
    this.bits = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) this.bits[i] = bin.charCodeAt(i);
  }

  /** Is voxel (i, j, k) occupied? Outside the grid counts as empty. */
  cell(i: number, j: number, k: number): boolean {
    const [nx, ny, nz] = this.dims;
    if (i < 0 || j < 0 || k < 0 || i >= nx || j >= ny || k >= nz) return false;
    const idx = i + nx * (j + ny * k);
    return (this.bits[idx >> 3] & (1 << (idx & 7))) !== 0;
  }

  index(x: number, y: number, z: number): [number, number, number] {
    return [
      Math.floor((x - this.origin[0]) / this.voxel),
      Math.floor((y - this.origin[1]) / this.voxel),
      Math.floor((z - this.origin[2]) / this.voxel),
    ];
  }

  /** All occupied cell centres (for the debug view). */
  *occupied(): Generator<Vec3> {
    const [nx, ny, nz] = this.dims;
    const v = this.voxel;
    for (let k = 0; k < nz; k++)
      for (let j = 0; j < ny; j++)
        for (let i = 0; i < nx; i++)
          if (this.cell(i, j, k))
            yield [this.origin[0] + (i + 0.5) * v, this.origin[1] + (j + 0.5) * v, this.origin[2] + (k + 0.5) * v];
  }
}

/** Point in an oriented (yaw-only) box, in the box's local frame. */
function inBlock(b: Block, x: number, y: number, z: number, pad = 0): boolean {
  const c = Math.cos((-b.yawDeg * Math.PI) / 180), s = Math.sin((-b.yawDeg * Math.PI) / 180);
  const dx = x - b.center[0], dy = y - b.center[1];
  const lx = c * dx - s * dy, ly = s * dx + c * dy, lz = z - b.center[2];
  return Math.abs(lx) <= b.size[0] / 2 + pad && Math.abs(ly) <= b.size[1] / 2 + pad && Math.abs(lz) <= b.size[2] / 2;
}

export class CollisionWorld {
  grid: VoxelGrid | null;
  blocks: Block[];
  voxelsEnabled = true;

  constructor(grid: VoxelGrid | null, blocks: Block[]) {
    this.grid = grid;
    this.blocks = blocks;
  }

  get floorZ(): number {
    return this.grid?.floorZ ?? 0;
  }

  /** Does a vertical cylinder at (x, y) from z0 to z1 hit anything? */
  cylinderBlocked(x: number, y: number, radius: number, z0: number, z1: number): boolean {
    for (const b of this.blocks) {
      for (let z = z0; z <= z1 + 1e-6; z += Math.max((z1 - z0) / 4, 0.05)) if (inBlock(b, x, y, z, radius)) return true;
    }
    const g = this.grid;
    if (!g || !this.voxelsEnabled) return false;
    const [i0, j0, k0] = g.index(x - radius, y - radius, z0);
    const [i1, j1, k1] = g.index(x + radius, y + radius, z1);
    const r2 = (radius + g.voxel * 0.5) ** 2;
    for (let k = k0; k <= k1; k++)
      for (let j = j0; j <= j1; j++)
        for (let i = i0; i <= i1; i++) {
          if (!g.cell(i, j, k)) continue;
          const cx = g.origin[0] + (i + 0.5) * g.voxel, cy = g.origin[1] + (j + 0.5) * g.voxel;
          if ((cx - x) ** 2 + (cy - y) ** 2 <= r2) return true;
        }
    return false;
  }

  /** Highest support under the feet within [zMin, zMax]: voxel tops, block tops or the floor. */
  groundZ(x: number, y: number, radius: number, zMax: number, zMin = -Infinity): number {
    let best = this.floorZ <= zMax ? this.floorZ : -Infinity;
    for (const b of this.blocks) {
      const top = b.center[2] + b.size[2] / 2;
      if (top <= zMax && top > best && inBlock(b, x, y, top - 1e-3, radius * 0.5)) best = top;
    }
    const g = this.grid;
    if (g && this.voxelsEnabled) {
      const r = radius * 0.5;
      const [i0, j0] = g.index(x - r, y - r, 0);
      const [i1, j1] = g.index(x + r, y + r, 0);
      const kTop = g.index(0, 0, zMax)[2];
      const kBottom = Math.max(0, g.index(0, 0, Math.max(zMin, best))[2]);
      for (let i = i0; i <= i1; i++)
        for (let j = j0; j <= j1; j++)
          for (let k = Math.min(kTop, g.dims[2] - 1); k >= kBottom; k--) {
            if (g.cell(i, j, k)) {
              const top = g.origin[2] + (k + 1) * g.voxel;
              if (top <= zMax + 1e-6 && top > best) best = top;
              break;
            }
          }
    }
    return best;
  }

  /** First hit along a ray (voxels via a DDA walk, blocks by sampling). Used to place markers. */
  raycast(o: Vec3, d: Vec3, maxDist = 30): Vec3 | null {
    let hit: Vec3 | null = null;
    let hitT = maxDist;
    for (const b of this.blocks) {
      for (let t = 0; t < hitT; t += 0.02) {
        if (inBlock(b, o[0] + d[0] * t, o[1] + d[1] * t, o[2] + d[2] * t)) {
          hitT = t;
          hit = [o[0] + d[0] * t, o[1] + d[1] * t, o[2] + d[2] * t];
          break;
        }
      }
    }
    const g = this.grid;
    if (g) {
      let [i, j, k] = g.index(o[0], o[1], o[2]);
      const step = d.map((v) => (v > 0 ? 1 : -1));
      const next = (a: number, idx: number) => g.origin[a] + (idx + (step[a] > 0 ? 1 : 0)) * g.voxel;
      const tMax = [0, 1, 2].map((a) => (d[a] !== 0 ? (next(a, [i, j, k][a]) - o[a]) / d[a] : Infinity));
      const tDelta = [0, 1, 2].map((a) => (d[a] !== 0 ? g.voxel / Math.abs(d[a]) : Infinity));
      let t = 0;
      while (t < hitT) {
        if (g.cell(i, j, k)) {
          hitT = t;
          hit = [o[0] + d[0] * t, o[1] + d[1] * t, o[2] + d[2] * t];
          break;
        }
        const a = tMax[0] < tMax[1] ? (tMax[0] < tMax[2] ? 0 : 2) : tMax[1] < tMax[2] ? 1 : 2;
        t = tMax[a];
        tMax[a] += tDelta[a];
        if (a === 0) i += step[0];
        else if (a === 1) j += step[1];
        else k += step[2];
      }
    }
    // The floor plane as a last resort.
    if (!hit && d[2] < 0) {
      const t = (this.floorZ - o[2]) / d[2];
      if (t > 0 && t < maxDist) hit = [o[0] + d[0] * t, o[1] + d[1] * t, this.floorZ];
    }
    return hit;
  }
}
