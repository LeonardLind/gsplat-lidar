"""Look at the images inside a BLK2GO .b2g (read-only): table layout, and a few frames written out as JPEG.

    python b2g_images.py <scan.b2g> <out_dir> [--every 150]
"""
import pathlib
import sqlite3
import sys

p = pathlib.Path(sys.argv[1]).resolve()
out = pathlib.Path(sys.argv[2])
every = int(sys.argv[sys.argv.index("--every") + 1]) if "--every" in sys.argv else 150
out.mkdir(parents=True, exist_ok=True)
con = sqlite3.connect(f"file:{p.as_posix()}?mode=ro&immutable=1", uri=True)
cur = con.cursor()
tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")]
print("tables:", tables)
for t in tables:
    if "image" in t.lower() or "calib" in t.lower() or "camera" in t.lower():
        cols = [(r[1], r[2]) for r in cur.execute(f"PRAGMA table_info({t})")]
        n = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"{t}: {n} rows, columns {cols}")

cols = [r[1] for r in cur.execute("PRAGMA table_info(panoimagedata)")]
blob_cols = [c for c in cols if cur.execute(f"SELECT typeof({c}) FROM panoimagedata LIMIT 1").fetchone()[0] == "blob"]
print("blob columns:", blob_cols)
rows = cur.execute(f"SELECT rowid, * FROM panoimagedata").fetchall()
for k, row in enumerate(rows[::every]):
    rec = dict(zip(["rowid", *cols], row))
    meta = {c: v for c, v in rec.items() if not isinstance(v, bytes)}
    for c in blob_cols:
        b = rec[c]
        kind = "jpeg" if b[:2] == b"\xff\xd8" else "png" if b[:4] == b"\x89PNG" else f"raw({b[:4].hex()})"
        if kind in ("jpeg", "png"):
            f = out / f"{p.stem.replace(' ', '_')}_{rec['rowid']}_{c}.{'jpg' if kind == 'jpeg' else 'png'}"
            f.write_bytes(b)
        print(k, meta, c, kind, len(b))
