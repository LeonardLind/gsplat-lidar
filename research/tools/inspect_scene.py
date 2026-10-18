"""Scene character: height profile above a crude ground estimate, colour, intensity distribution, XY coverage."""
import sys

import laspy
import numpy as np

p = sys.argv[1]
rng = np.random.default_rng(1)
xs, ys, zs, it, r, g, b = [], [], [], [], [], [], []
with laspy.open(p) as f:
    for pts in f.chunk_iterator(5_000_000):
        k = rng.random(len(pts)) < 0.05          # 5% random sample
        xs.append(np.asarray(pts.x)[k]); ys.append(np.asarray(pts.y)[k]); zs.append(np.asarray(pts.z)[k])
        it.append(np.asarray(pts.intensity)[k])
        if "red" in pts.point_format.dimension_names:
            r.append(np.asarray(pts.red)[k]); g.append(np.asarray(pts.green)[k]); b.append(np.asarray(pts.blue)[k])
x, y, z = np.concatenate(xs), np.concatenate(ys), np.concatenate(zs)
I = np.concatenate(it).astype(float)
print("sample points", len(x))

# Crude ground: per 1 m cell, 2nd percentile of z
cell = 1.0
ix = np.floor((x - x.min()) / cell).astype(int); iy = np.floor((y - y.min()) / cell).astype(int)
key = ix * 100000 + iy
order = np.argsort(key); ks = key[order]; zs_ = z[order]
uniq, start = np.unique(ks, return_index=True)
ground = {}
for u, a, bnd in zip(uniq, start, np.r_[start[1:], len(ks)]):
    seg = zs_[a:bnd]
    if len(seg) >= 20:
        ground[u] = np.percentile(seg, 2)
gz = np.array([ground.get(k_, np.nan) for k_ in key])
hag = z - gz
ok = ~np.isnan(hag)
print("occupied 1 m cells (>=20 sampled pts):", len(ground), "of bbox cells", (ix.max() + 1) * (iy.max() + 1))
print("ground z range (2nd pct per cell): %.2f .. %.2f m" % (np.nanmin(list(ground.values())), np.nanmax(list(ground.values()))))
edges = [-1, 0.3, 1, 2, 5, 10, 15, 20, 25, 30, 40]
hist, _ = np.histogram(hag[ok], bins=edges)
print("height-above-ground distribution (m):")
for a_, b_, c in zip(edges[:-1], edges[1:], hist):
    print(f"  {a_:>4}–{b_:<4}: {c / ok.sum():6.1%}")
print("max height above ground (p99.9): %.1f m" % np.percentile(hag[ok], 99.9))

# Intensity
print("intensity percentiles [1,5,25,50,75,95,99]:", np.percentile(I, [1, 5, 25, 50, 75, 95, 99]).round(0))
ground_mask = ok & (hag < 0.3)
print("median intensity ground (<0.3 m): %.0f | 1–5 m: %.0f | >5 m: %.0f" % (
    np.median(I[ground_mask]), np.median(I[ok & (hag > 1) & (hag < 5)]), np.median(I[ok & (hag > 5)])))
print("fraction of points with intensity > p99.5 (bright/reflective):", float((I > np.percentile(I, 99.5)).mean()))

if r:
    R, G, B = (np.concatenate(v).astype(float) / 256 for v in (r, g, b))
    col = R + G + B > 0
    print("coloured fraction", float(col.mean()))
    print("mean RGB (8-bit) all: %.0f %.0f %.0f" % (R[col].mean(), G[col].mean(), B[col].mean()))
    for name, m in (("ground", ground_mask & col), ("1–5 m", ok & (hag > 1) & (hag < 5) & col), (">5 m", ok & (hag > 5) & col)):
        if m.any():
            print(f"  mean RGB {name}: {R[m].mean():.0f} {G[m].mean():.0f} {B[m].mean():.0f}")
    exg = 2 * G - R - B
    print("excess-green > 20 fraction (vegetation-like colour):", float((exg[col] > 20).mean()))
