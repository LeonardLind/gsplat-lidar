import { defineConfig, type Plugin } from "vite";
import fs from "node:fs";
import path from "node:path";
import { sceneDirNow, serveScene } from "./scene-server";

// The scene folder is an export from the pipeline (python -m app export ...):
// scene.json, the splat (.sog/.spz/.ply) and collision.json. Set it with GSL_SCENE_DIR, or pick an
// export in the studio ("Open in explorer"), which records the project in projects/_server/current.json.

/** Serves /scene/* from the scene folder and lets edit mode save scene.json (dev server only). */
function scenePlugin(): Plugin {
  return {
    name: "gsl-scene",
    configureServer(server) {
      server.middlewares.use("/scene", serveScene);
      // Edit mode uploads images/audio for markers: POST /api/upload?name=<file>, raw body -> assets/<file>.
      server.middlewares.use("/api/upload", (req, res) => {
        const url = new URL(req.url ?? "", "http://x");
        const name = (url.searchParams.get("name") ?? "").replace(/[^A-Za-z0-9._-]+/g, "_").slice(0, 120);
        if (req.method !== "POST" || !name || name.startsWith(".")) {
          res.statusCode = 400;
          res.end();
          return;
        }
        const dir = path.join(sceneDirNow(), "assets");
        fs.mkdirSync(dir, { recursive: true });
        const out = fs.createWriteStream(path.join(dir, name));
        req.pipe(out);
        out.on("finish", () => {
          res.setHeader("Content-Type", "application/json");
          res.end(JSON.stringify({ ok: true, path: `assets/${name}` }));
        });
        out.on("error", (e) => {
          res.statusCode = 500;
          res.end(JSON.stringify({ ok: false, error: String(e) }));
        });
      });
      server.middlewares.use("/api/scene", (req, res) => {
        if (req.method !== "POST") {
          res.statusCode = 405;
          res.end();
          return;
        }
        let body = "";
        req.on("data", (c) => (body += c));
        req.on("end", () => {
          try {
            const parsed = JSON.parse(body);
            const sceneDir = sceneDirNow();
            const target = path.join(sceneDir, "scene.json");
            if (fs.existsSync(target)) fs.copyFileSync(target, path.join(sceneDir, "scene.prev.json"));
            fs.writeFileSync(target + ".tmp", JSON.stringify(parsed, null, 2));
            fs.renameSync(target + ".tmp", target);
            res.setHeader("Content-Type", "application/json");
            res.end(JSON.stringify({ ok: true }));
          } catch (e) {
            res.statusCode = 400;
            res.end(JSON.stringify({ ok: false, error: String(e) }));
          }
        });
      });
    },
  };
}

export default defineConfig({
  plugins: [scenePlugin()],
  server: {
    port: 5173,
    host: "127.0.0.1",
    // The studio's job server (python -m app serve).
    proxy: { "/studio-api": { target: "http://127.0.0.1:8765", changeOrigin: true } },
  },
  build: {
    rollupOptions: {
      input: { explorer: path.resolve("index.html"), studio: path.resolve("studio.html"), clean: path.resolve("clean.html") },
    },
  },
});
