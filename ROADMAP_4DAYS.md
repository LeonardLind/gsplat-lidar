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

- [x] `train/068+069/rigid_lidar_poseopt_150k`: DIVERGED (pose-opt lr 1e-4, loss 0.1 -> 17 at ~62k). Stopped.
- [x] Queue done 00:28: base 17.69, depth_v2 17.77 (current), depth+pose1e5 17.79 (tie -> simpler kept).
- [x] (was) Training queue (`scripts/train_queue.py lidar/queue.json`, watchdog): `rigid_base_150k`,
  `rigid_depth_v2_150k` (depth loss, NaN fix), `rigid_depth_pose1e5_150k`. Drift fix:
  `--strategy.noise-injection-stop-iter 25000`. Restart the queue with the same command after a reboot.
- [x] Compared: `rigid_depth_v2_150k` (17.77 dB, no fog near the camera) beats `rigid_base_150k` (17.69 dB). It is current.
- [ ] (old) Compare (rules above), export the winner as current, screenshots of fixed views into
  `projects/office-x4/review/` (not in git), log in HANDOFF.

## Phase 2 (days 1-2): one consistent camera solve with LiDAR position priors (the real fix)

Why: the walk falls apart because the original matching never compared the low and high passes or revisits
(sequential matching only), and 48 weak links cut it into 42 models. Now every image has a position in the
LiDAR frame from the joined model, so (a) nearby images from other passes can be found and matched, and (b) the
mapper can use the positions as priors to bridge weak links.

- [x] 2a+2b done 2026-10-22 18:xx: `aliked_prior/database.db` has priors for 1271 + 23 interpolated frames
  (237 without); `aliked_prior/pairs_spatial.txt` 245 657 pairs (227k cross-pass/revisit, max 40 per image,
  ~400 per frame). `scripts/phase2_prior_solve.py` (started, waits for the training queue) does 2b matching
  + 2c global_mapper + pose_prior_mapper, report `aliked_prior/phase2_report.json`, log `aliked_prior/phase2.log`.
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

- [ ] 2e. **Allowed by the user (2026-10-22): a full SfM re-run with the LiDAR as the skeleton**, if Phase 2
  still fails or looks bad. E.g. fresh matching with pairs chosen from the LiDAR-frame positions (spatial +
  view overlap, cross-pass), mapping with position priors from the start (`pose_prior_mapper`), or poses
  fixed from the LiDAR-frame solve and only triangulation + bundle adjustment with the priors. Feature
  extraction can be reused (the databases hold the ALIKED features; re-extracting costs ~6 h CPU and is only
  worth it if the features themselves are the problem).
  **The current plan and every result so far must stay reviewable:** the re-run writes only to new folders
  (`sfm/068+069/lidar_rerun*`, `lidar/rerun*`, `train/068+069/rerun_*`, `export/068+069/rerun_*`); the best
  pre-re-run export is kept and listed in HANDOFF next to the re-run's, so the user can compare both.

## Phase 3 (day 3): quality and the explorer

- [ ] Training budget: if VRAM allows, cap 2.5 M / 300k steps on the winner (one run), compare.
- [x] LiDAR cleanup (`app/lidar/clean_splat.py`): current scene 1.6 M -> 285k Gaussians, 6.8 MB, looks the same.
  Run it on every new winner after export. Queue job `rigid_depth_reloc_150k` waits for the GPU (start
  `scripts/train_queue.py lidar/queue.json` again when `aliked_prior/match.done` exists).
- [x] (was) LiDAR-based cleanup: drop Gaussians far outside the LiDAR surfaces (outside walls, under the floor, above
  the ceiling), re-export; check visually.
- [x] Measure tool (T, metric scenes only, snaps to LiDAR points): floor-to-ceiling 2.71 m vs LiDAR 2.70
  (`web/viewer/tools/test_measure.mjs`).
- [ ] Explorer (rest): distance measuring tool (the scale is metric now; PLAN: measurement only with exact scale),
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

Windows Update on this PC is managed by company IT (Intune): pausing is disabled by policy
(`SetDisablePauseUXAccess`), updates install automatically at 03:00 with a 5-day deadline + 2-day grace and
may restart outside the active hours (10-19). Claude did not and must not override that policy. Checked
2026-10-22 18:2x: no restart pending, only Dell driver updates waiting; the October security update (9-day
deferral) can arrive any day. **If the PC restarted:** log in, open VS Code in this repo, tell Claude "continue
the 4-day roadmap". Everything up to the last milestone is committed and pushed; a training run that was cut
off is simply restarted (its folder is replaced by a new one with a suffix).
