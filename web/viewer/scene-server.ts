// Serves /scene/* (the exported scene folder) for the dev server and the read-only tablet server.
// The folder is GSL_SCENE_DIR when set (pins a scene), otherwise the project the studio last opened
// (projects/_server/current.json -> projects/<name>/export/current).

import fs from "node:fs";
import path from "node:path";
import type { IncomingMessage, ServerResponse } from "node:http";

const projectsDir = path.resolve("../../projects");

export function sceneDirNow(): string {
  if (process.env.GSL_SCENE_DIR) return path.resolve(process.env.GSL_SCENE_DIR);
  let project = "office";
  try {
    project = JSON.parse(fs.readFileSync(path.join(projectsDir, "_server", "current.json"), "utf8")).project ?? project;
  } catch { /* no studio choice yet */ }
  return path.join(projectsDir, project, "export", "current");
}

const MIME: Record<string, string> = {
  ".json": "application/json",
  ".sog": "application/octet-stream",
  ".spz": "application/octet-stream",
  ".ply": "application/octet-stream",
  ".bin": "application/octet-stream",
  ".wav": "audio/wav",
  ".mp3": "audio/mpeg",
  ".ogg": "audio/ogg",
  ".m4a": "audio/mp4",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".png": "image/png",
  ".webp": "image/webp",
};

/** Connect middleware for /scene: GET/HEAD of files below the scene folder, with byte ranges. */
export function serveScene(req: IncomingMessage, res: ServerResponse, next: () => void): void {
  const sceneDir = sceneDirNow();
  const rel = decodeURIComponent((req.url ?? "/").split("?")[0]).replace(/^\/+/, "");
  const file = path.resolve(sceneDir, rel);
  if (!file.startsWith(sceneDir) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) return next();
  const size = fs.statSync(file).size;
  res.setHeader("Content-Type", MIME[path.extname(file).toLowerCase()] ?? "application/octet-stream");
  res.setHeader("Cache-Control", "no-store");
  res.setHeader("Accept-Ranges", "bytes");
  // Media elements and streaming loaders ask for byte ranges; answer them properly.
  const m = /^bytes=(\d*)-(\d*)$/.exec(req.headers.range ?? "");
  if (m) {
    const start = m[1] ? +m[1] : Math.max(0, size - +m[2]);
    const end = m[1] && m[2] ? Math.min(+m[2], size - 1) : size - 1;
    if (start >= size || start > end) {
      res.statusCode = 416;
      res.setHeader("Content-Range", `bytes */${size}`);
      res.end();
      return;
    }
    res.statusCode = 206;
    res.setHeader("Content-Range", `bytes ${start}-${end}/${size}`);
    res.setHeader("Content-Length", String(end - start + 1));
    fs.createReadStream(file, { start, end }).pipe(res);
    return;
  }
  res.setHeader("Content-Length", String(size));
  fs.createReadStream(file).pipe(res);
}
