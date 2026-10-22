// scene.json, written by the pipeline (python -m app export) and edited in the viewer's edit mode.
// All coordinates are in the project frame: +Z up, metres (approximate without LiDAR, see frame.scale).

export type Vec3 = [number, number, number];

export interface Marker {
  id: string;
  /** "info": a card with images and text. "audio": plays a narration in the audio bar. */
  kind?: "info" | "audio";
  position: Vec3;
  title: string;
  text: string;
  /** Image files in the scene folder, shown as a carousel on the card. */
  images?: string[];
  /** Show a hint when the player is closer than this (m). */
  radius?: number;
  /** Sound file in the scene folder: the narration of an audio marker, or a sound for an info card. */
  audio?: string;
  /** Play the audio from the marker's position (true) or as plain narration (false, default for audio markers). */
  spatial?: boolean;
}

/** A looping positional sound source (ambience, machines, voices...). */
export interface Sound {
  id: string;
  position: Vec3;
  url: string;
  volume: number; // 0..1
  refDistance: number; // full volume within this distance (m), then rolls off
}

/** A user-placed collision block: an oriented box, rotated about +Z only. */
export interface Block {
  id: string;
  center: Vec3;
  size: Vec3;
  yawDeg: number;
}

export interface SceneFile {
  schema_version: 1;
  name: string;
  frame: { up: "+Z"; units: "m"; scale: "metric" | "approximate" | "arbitrary"; note?: string };
  /** Optional placement of the splat file in the world: world = position + R(quaternion) * (scale * local). */
  splat: { url: string; transform?: { scale: number; quaternion_xyzw: [number, number, number, number]; position: Vec3 } };
  collision?: { url: string } | null;
  start: { position: Vec3; yawDeg: number };
  player: { eyeHeight: number; radius: number; stepHeight: number };
  markers: Marker[];
  blocks: Block[];
  sounds?: Sound[];
  /** The LiDAR points (scenes trained in the LiDAR frame): lidar.bin, see src/lidar.ts. */
  lidar?: { url: string; count: number; bounds: [Vec3, Vec3] };
}

/** collision.json: occupancy voxels derived from the splat (python -m app export). */
export interface CollisionFile {
  origin: Vec3; // world position of voxel (0,0,0)'s min corner
  voxel: number; // edge length (m)
  dims: [number, number, number];
  floorZ: number; // detected floor height, the fallback ground
  encoding: "bitset-base64"; // x fastest, then y, then z; bit i of byte i>>3 (LSB first)
  data: string;
}
