import sys, laspy, numpy as np
p = sys.argv[1]
with laspy.open(p) as f:
    h = f.header
    print("version", h.version, "point_format", h.point_format.id, "count", h.point_count)
    print("system_id", repr(h.system_identifier), "software", repr(h.generating_software))
    print("creation", h.creation_date, "global_encoding", h.global_encoding.value if hasattr(h.global_encoding,'value') else h.global_encoding)
    print("scales", h.scales, "offsets", h.offsets)
    print("mins", h.mins, "maxs", h.maxs, "extent", h.maxs - h.mins)
    print("dims", list(h.point_format.dimension_names))
    print("extra dims", [d.name for d in h.point_format.extra_dimensions])
    for v in h.vlrs:
        print("VLR", v.user_id, v.record_id, v.description)
    try:
        print("CRS", h.parse_crs())
    except Exception as e:
        print("CRS parse err", e)
    try:
        print("evlrs", [(v.user_id, v.record_id) for v in (h.evlrs or [])])
    except Exception as e:
        print("evlr err", e)
    # sample chunks: first, and a few spread chunks via sequential read with stride
    n = h.point_count
    chunk = 2_000_000
    stats = {}
    first = None
    nseen = 0
    gps_min, gps_max = np.inf, -np.inf
    cls_vals = {}
    rn_vals = {}; nr_vals = {}
    psid = {}
    mono_breaks = 0; last_gps = None
    for i, pts in enumerate(f.chunk_iterator(chunk)):
        nseen += len(pts)
        if 'gps_time' in pts.point_format.dimension_names:
            g = np.asarray(pts.gps_time)
            gps_min = min(gps_min, g.min()); gps_max = max(gps_max, g.max())
            d = np.diff(g); mono_breaks += int((d < 0).sum())
            if i == 0:
                print("first gps", g[:10], "unique in chunk", len(np.unique(g)))
        c = np.asarray(pts.classification); u, k = np.unique(c, return_counts=True)
        for a, b in zip(u, k): cls_vals[int(a)] = cls_vals.get(int(a), 0) + int(b)
        r = np.asarray(pts.return_number); u, k = np.unique(r, return_counts=True)
        for a, b in zip(u, k): rn_vals[int(a)] = rn_vals.get(int(a), 0) + int(b)
        r = np.asarray(pts.number_of_returns); u, k = np.unique(r, return_counts=True)
        for a, b in zip(u, k): nr_vals[int(a)] = nr_vals.get(int(a), 0) + int(b)
        s = np.asarray(pts.point_source_id); u, k = np.unique(s, return_counts=True)
        for a, b in zip(u, k): psid[int(a)] = psid.get(int(a), 0) + int(b)
        if i == 0:
            first = pts
            for dn in pts.point_format.dimension_names:
                arr = np.asarray(pts[dn])
                print(f"  {dn:22s} min {arr.min()} max {arr.max()} sample {arr[:5]}")
        if i >= 9:  # cap to ~20M points
            break
    print("points scanned", nseen, "of", n)
    print("gps_time range", gps_min, gps_max, "span s", gps_max - gps_min, "non-monotonic steps", mono_breaks)
    print("classification", cls_vals)
    print("return_number", rn_vals, "number_of_returns", nr_vals)
    print("point_source_id (top)", sorted(psid.items(), key=lambda x: -x[1])[:10], "n unique", len(psid))
    # spacing estimate on first chunk subset
    xyz = np.c_[first.x, first.y, first.z][:200000]
    from scipy.spatial import cKDTree
    t = cKDTree(xyz); d, _ = t.query(xyz[:20000], k=2)
    print("NN spacing (first 20k of first chunk) median m", float(np.median(d[:,1])), "p90", float(np.percentile(d[:,1], 90)))
