"""Compact LAS/LAZ inspection: header, fields, value ranges, timestamp structure, density."""
import sys

import laspy
import numpy as np
from scipy.spatial import cKDTree

p = sys.argv[1]
with laspy.open(p) as f:
    h = f.header
    pf = h.point_format
    print("version", h.version, "| point_format", pf.id, "| points", h.point_count)
    print("system_id", repr(h.system_identifier), "| software", repr(h.generating_software))
    print("creation", h.creation_date, "| global_encoding", int(h.global_encoding.value) if hasattr(h.global_encoding, "value") else h.global_encoding)
    print("scales", h.scales, "| offsets", h.offsets)
    print("mins", np.round(h.mins, 3), "| maxs", np.round(h.maxs, 3), "| extent", np.round(h.maxs - h.mins, 3))
    print("dims", list(pf.dimension_names))
    print("extra dims", [(d.name, str(d.dtype)) for d in pf.extra_dimensions])
    for v in h.vlrs:
        print("VLR", v.user_id, v.record_id, repr(v.description))
    try:
        print("CRS", h.parse_crs())
    except Exception as e:
        print("CRS parse error", e)
    try:
        print("EVLRs", [(v.user_id, v.record_id) for v in (h.evlrs or [])])
    except Exception as e:
        print("EVLR error", e)

    names = list(pf.dimension_names)
    skip = {"X", "Y", "Z"}
    mins = {}; maxs = {}; nonzero = {}
    uniq = {d: {} for d in ("classification", "return_number", "number_of_returns", "point_source_id", "user_data", "scan_angle_rank", "scan_angle")}
    gs = []; sample_xyz = []; n = 0
    for pts in f.chunk_iterator(5_000_000):
        n += len(pts)
        for d in names:
            if d in skip:
                continue
            a = np.asarray(pts[d])
            mins[d] = min(mins.get(d, a.min()), a.min()); maxs[d] = max(maxs.get(d, a.max()), a.max())
            nonzero[d] = nonzero.get(d, 0) + int(np.count_nonzero(a))
            if d in uniq:
                u, c = np.unique(a, return_counts=True)
                for x, y in zip(u[:500], c[:500]):
                    uniq[d][float(x)] = uniq[d].get(float(x), 0) + int(y)
        if "gps_time" in names:
            gs.append(np.asarray(pts.gps_time).copy())
        if len(sample_xyz) < 4:
            sample_xyz.append(np.c_[pts.x, pts.y, pts.z])
    print("points read", n)
    for d in names:
        if d in skip:
            continue
        print(f"  {d:22s} min {mins[d]} max {maxs[d]} nonzero {nonzero[d] / n:.4f}")
    for d, u in uniq.items():
        if u:
            top = sorted(u.items(), key=lambda kv: -kv[1])[:8]
            print(f"  {d} values (top): {top} | distinct {len(u)}")
    if all(c in names for c in ("red", "green", "blue")):
        pass

    if gs:
        g = np.concatenate(gs)
        print("gps_time sorted in file?", bool(np.all(np.diff(g) >= 0)))
        g.sort()
        d = np.diff(g); pos = d[d > 0]
        print("gps_time range", g[0], g[-1], "span", g[-1] - g[0], "| zero steps", int((d == 0).sum()))
        if len(pos):
            print("positive-step quantiles [1,5,25,50,75,95,99]:", np.percentile(pos, [1, 5, 25, 50, 75, 95, 99]))
            small = np.round(pos[pos <= np.percentile(pos, 50)])
            vals, cnt = np.unique(small, return_counts=True)
            top = np.argsort(-cnt)[:8]
            print("most common small steps:", [(float(vals[i]), int(cnt[i])) for i in top])
            med = np.median(pos)
            big = np.where(d > 1000 * med)[0]
            print("gaps > 1000x median step:", len(big))
            if len(big) > 2:
                starts = g[np.r_[0, big + 1]]
                ss = np.diff(starts)
                print("segment start-to-start median", float(np.median(ss)), "min", float(ss.min()), "max", float(ss.max()))
        for unit, label in ((1.0, "s"), (8e-9, "8ns ticks"), (1e-9, "ns"), (1e-6, "us")):
            print(f"  span if unit={label}: {(g[-1] - g[0]) * unit:.3f} s")
        h40, _ = np.histogram(g, bins=40)
        print("time histogram (40 bins):", h40.tolist())

    xyz = np.concatenate(sample_xyz)
    idx = np.random.default_rng(0).choice(len(xyz), size=min(300_000, len(xyz)), replace=False)
    sub = xyz[idx]
    t = cKDTree(sub); dd, _ = t.query(sub[:20000], k=2)
    print("NN spacing in a random 300k subsample of the first chunks: median m", float(np.median(dd[:, 1])))
    area = float((h.maxs[0] - h.mins[0]) * (h.maxs[1] - h.mins[1]))
    print("bbox area m2", round(area, 1), "| points per m2 (bbox)", round(h.point_count / area, 1))
