# Inspiration 01: three Instagram posts (2026-10-18)

Downloaded with yt-dlp (no login), audio transcribed with faster-whisper `small`.

| Post | Author | What it is | Audio |
|---|---|---|---|
| reel/DdHLaBfDJnG (2026-09-10, 23 s) | CG Channel | SuperSplat Editor 3.0 (PlayCanvas, open source): rewritten on WebGPU | Narration (below) |
| p/DcRAvxIonV8 (2026-08-20, 79 s) | Jörg Kahlhöfer | Splat of a person in a graveyard, "large format emulator" in Octane: grain, halation, 4×5 film frame, live in the AOV compositor | Music only |
| p/DbLTWlKorL6 (2026-07-24, 72 s) | Jörg Kahlhöfer | VW Beetle splat in Octane with simulated DOF, framed as the 1959 "Think small" ad; the car is a second splat composited in front of the frame | Music only |

SuperSplat 3.0 narration: "The editor has been rebuilt on WebGPU. Projection, sorting and selection all run on the GPU, so every splat in your scene is sorted together and far larger scenes load without running out of memory. On heavy scenes, with tens of millions of Gaussians, the editor skips sorting while you move. A new stochastic alpha mode keeps it responsive, and the sorted image returns the moment you stop."

Kahlhöfer capture: rig of **5 × DJI Osmo Action 6**, 3 min capture → frames → RealityCapture alignment → Postshot training → Octane (Cinema 4D) render. Quote: "I don't take the photo on location. I bring the location home and take the photo there."

## Ideas worth taking (see the session reply for the ranked list)
1. SuperSplat 3.0 as an external heavy-cleanup editor for big masters (round trip: our master PLY → SuperSplat → import cleaned PLY → rebuild SOG + collision).
2. "Moving = stochastic/unsorted, still = sorted" as a performance mode for clean.html and low-end presets.
3. GPU-side selection when cleanup must handle 10 M+ splats.
4. A photo/viewfinder mode in the explorer: focal length, DOF, framing, and saving the shot as a hotspot card image (high-res re-render offline with gsplat).
5. An optional "presentation look" (grain, vignette, light DOF) that hides softness and floaters. Presentation only, never in measurement or LiDAR modes.
6. Layered splats: hero objects scanned separately at high detail and composited into the scene (also the model for the LiDAR/splat layer order).
7. Capture: a multi-camera action-cam rig (larger sensor, better low light than the X4) as an extra modular source, e.g. for forest hero objects.
