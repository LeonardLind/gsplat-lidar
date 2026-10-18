import sys, laspy, numpy as np
p = sys.argv[1]
gs = []; inten_max = 0; rgb0 = 0; n = 0; zs = []
with laspy.open(p) as f:
    for pts in f.chunk_iterator(4_000_000):
        gs.append(np.asarray(pts.gps_time).copy())
        inten_max = max(inten_max, int(np.asarray(pts.intensity).max()))
        r, g, b = np.asarray(pts.red), np.asarray(pts.green), np.asarray(pts.blue)
        rgb0 += int(((r == 0) & (g == 0) & (b == 0)).sum()); n += len(pts)
        if len(zs) < 3: zs.append(np.c_[pts.x, pts.y, pts.z, pts.gps_time][::50])
g = np.concatenate(gs); g.sort()
print("n", n, "intensity max (all)", inten_max, "rgb all-zero fraction", rgb0 / n)
d = np.diff(g)
print("sorted-time deltas: zero count", int((d == 0).sum()))
pos = d[d > 0]
print("delta quantiles", np.percentile(pos, [1, 5, 25, 50, 75, 95, 99]))
small = pos[pos < np.percentile(pos, 50)]
vals, cnt = np.unique(np.round(small), return_counts=True)
top = np.argsort(-cnt)[:15]
print("most common small deltas", list(zip(vals[top], cnt[top])))
# gaps -> sessions
big = np.where(d > 1e3 * np.median(pos))[0]
print("big gaps (count)", len(big))
edges = np.r_[0, big + 1, len(g)]
for a, b in zip(edges[:-1], edges[1:]):
    if b - a > 1000:
        print(f"segment n={b-a:>10d} start {g[a]:.6e} end {g[b-1]:.6e} span {g[b-1]-g[a]:.6e}")
# histogram of time
h, e = np.histogram(g, bins=40)
print("time histogram (40 bins):", h.tolist())
# relation of time to position: do nearby times map to nearby positions? (track test)
s = np.concatenate(zs); s = s[np.argsort(s[:, 3])]
dt = np.diff(s[:, 3]); dx = np.linalg.norm(np.diff(s[:, :3], axis=0), axis=1)
print("subsample: median spatial jump between time-adjacent points (m)", float(np.median(dx)))
