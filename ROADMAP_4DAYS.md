# Autonomous plan, 2026-10-22 (evening) to 2026-10-26: whole office, joined, in the LiDAR frame

The user is away for 4 days and asked Claude to continue alone and make its own decisions. This file is the plan
and the decision rules; the results go into the run log in `HANDOFF.md` (newest first). **Claude: after any
context reset, read this file and the top of HANDOFF.md, check what is running, then continue with the first
open task.** Tick tasks here (`[x]`) when done and add one line on the outcome.

## Rules (decided with the user's go-ahead to judge alone)

- **One GPU job at a time** (8 GB). CPU work may run next to it if it does not starve the trainer's data loading
  (training slowed from 25 to 16 it/s while a CPU-heavy script ran).
- **Never delete or overwrite** the original data: `sfm/068+069/aliked_*` databases and models, `lidar/solve*`,
  `lidar/rigid`, `lidar/merged*`, earlier training runs. New work goes into new folders.
- **Choosing between results:** held-out PSNR from `python -m app.lidar.eval_chunks` (the "all views except the
  two looking down" number, plus the per-chunk table), then a visual check of the same fixed views
  (`web/viewer/tools/shot_views.mjs` + `tools/shot_lidar.mjs`, Chrome via `GSL_BROWSER`). A change must win on
  both or clearly on one without losing on the other. Equal: keep the simpler one.
- The best result is always exported and is `export/current` (what the explorer at :5173 shows).
- A step that fails twice for the same reason is logged in HANDOFF and skipped; move on to the next task.
- Commit + push to origin main after every milestone (outward action already authorised by the user). No other
  outward actions (no publishing, no messages).
- Long jobs run in the background with a log file; a recurring heartbeat (CronCreate, every ~2 h) re-checks
  them. On each wake-up: check jobs, write progress, start the next queued task if the GPU is free.

## Phase 1 (tonight): finish the two joined runs, pick the better one

- [ ] `train/068+069/rigid_lidar_poseopt_150k` (rigid placement, drift fix, pose-opt) -> exports itself.
  Check at 75k that the Gaussians stay inside the office (drift fix).
- [ ] `train/068+069/rigid_lidar_depth_150k` (same + LiDAR depth loss, `GSL_DEPTH_POINTS`), queued after it
  (`scratchpad/queue_depth.ps1`, log `lidar/train_depth.log`).
- [ ] Compare (rules above), export the winner as current, screenshots of fixed views into
  `projects/office-x4/review/` (not in git), log in HANDOFF.

## Phase 2 (days 1-2): one consistent camera solve with LiDAR position priors (the real fix)

Why: the walk falls apart because the original matching never compared the low and high passes or revisits
(sequential matching only), and 48 weak links cut it into 42 models. Now every image has a position in the
LiDAR frame from the joined model, so (a) nearby images from other passes can be found and matched, and (b) the
mapper can use the positions as priors to bridge weak links.

- [ ] 2a. Copy `aliked_cpu` (database with the weak-link and revisit pairs) to `aliked_prior`; write a position
  prior per image (LiDAR frame, from `lidar/merged_rigid`; frames in no model: interpolated in time from their
  neighbours, larger uncertainty).
- [ ] 2b. Spatial pairs: image pairs whose cameras are within ~2.5 m and whose view directions overlap, that are
  not already matched (skip neighbours within 2 frames). Cap at ~250k pairs (GPU matching ~0.15 s/pair ->
  ~10 h). `colmap matches_importer --match_type pairs`.
- [ ] 2c. Mapper: first `global_mapper` on the augmented database (~1 h; check jumps with the path check in
  `app/stages/sfm.py model_quality`), then `pose_prior_mapper` if the global result still jumps. Bring the
  result into the LiDAR frame (Umeyama camera centres -> priors, then ICP onto the LiDAR with the pass-height
  check), compare with `merged_rigid` (camera heights, ICP inliers, number of registered frames).
- [ ] 2d. Merge (LiDAR points as start), depth points, train with the Phase 1 winner's settings; compare;
  export the winner.

## Phase 3 (day 3): quality and the explorer

- [ ] Training budget: if VRAM allows, cap 2.5 M / 300k steps on the winner (one run), compare.
- [ ] LiDAR-based cleanup: drop Gaussians far outside the LiDAR surfaces (outside walls, under the floor, above
  the ceiling), re-export; check visually.
- [ ] Explorer: distance measuring tool (the scale is metric now; PLAN: measurement only with exact scale),
  LiDAR point-size control, a short help text for the LiDAR keys in the tablet view; tablet build.
- [ ] If time: per-pass appearance check (low vs high pass exposure differences).

## Phase 4 (day 4): hand-over

- [ ] Final export as current; review screenshots (splat, splat + LiDAR, LiDAR only) from ~10 fixed spots.
- [ ] HANDOFF: a short "read this first" summary at the top: what is done, numbers, what to look at, what is
  still weak and why, recommended next capture changes (ZV-E1 hybrid, step G).
- [ ] Commit + push.

## Limits (told to the user)

Everything stops if this VS Code / Claude session is closed, the PC restarts (Windows Update), or a tool call
waits for a permission prompt. Recurring heartbeats expire after 7 days.
