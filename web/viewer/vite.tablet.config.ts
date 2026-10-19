// Read-only server for tablets (and anything reached through a tunnel): the explorer page and /scene/* only.
// Unlike the dev server it has no /studio-api proxy (job control), no studio or cleanup pages and no
// save/upload endpoints, so exposing it through a tunnel cannot start jobs or change a scene.
//
//   npm run tablet                      serve the scene the studio last opened, on 127.0.0.1:5180 (for a tunnel)
//   GSL_SCENE_DIR=<export folder> ...   pin one scene (e.g. the forest demo)
//   TABLET_LAN=1 npm run tablet         listen on the local network too (same Wi-Fi, http://<PC address>:5180)
import path from "node:path";
import { defineConfig, type Plugin } from "vite";
import { serveScene } from "./scene-server";

function readOnlyScene(): Plugin {
  const guard = (req: { method?: string }, res: { statusCode: number; end: () => void }, next: () => void) => {
    if (req.method !== "GET" && req.method !== "HEAD") {
      res.statusCode = 405;
      res.end();
      return;
    }
    next();
  };
  return {
    name: "gsl-scene-readonly",
    configurePreviewServer(server) {
      server.middlewares.use("/scene", guard);
      server.middlewares.use("/scene", serveScene);
    },
  };
}

export default defineConfig({
  plugins: [readOnlyScene()],
  build: {
    outDir: "dist-tablet",
    emptyOutDir: true,
    rollupOptions: { input: { explorer: path.resolve("index.html") } },
  },
  preview: {
    port: Number(process.env.TABLET_PORT) || 5180,
    host: process.env.TABLET_LAN === "1" ? "0.0.0.0" : "127.0.0.1",
    strictPort: true,
    allowedHosts: true, // reached through a tunnel host name; the server is read-only
  },
});
