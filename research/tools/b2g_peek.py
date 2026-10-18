"""Read-only peek into small tables and blob layouts of a .b2g file."""
import pathlib
import sqlite3
import sys

p = pathlib.Path(sys.argv[1]).resolve()
con = sqlite3.connect(f"file:{p.as_posix()}?mode=ro&immutable=1", uri=True)
cur = con.cursor()

print("=== config")
for k, v in cur.execute("SELECT key, value FROM config ORDER BY key"):
    print(f"  {k} = {v[:160] if v else v}")

print("\n=== configfiles")
for tag, fn, sha, content in cur.execute("SELECT tag, filename, sha256, content FROM configfiles"):
    print(f"  [{tag}] {fn} sha={sha[:12] if sha else None} len={len(content) if content else 0}")
    if content:
        print("    " + content[:1200].replace("\n", "\n    "))

print("\n=== calibration")
for sensor, schema, data in cur.execute("SELECT sensor, schema, data FROM calibration"):
    print(f"  sensor={sensor} schema={schema!r} datalen={len(data) if data else 0} head={data[:64]!r}")

print("\n=== slamevents")
for row in cur.execute("SELECT ts, eventType, eventDescription FROM slamevents"):
    print("  ", row)

print("\n=== timestampedevents")
for ts, et, md, data in cur.execute("SELECT ts, eventType, metadata, data FROM timestampedevents"):
    print(f"  ts={ts} type={et} md={md[:200] if md else None!r} datalen={len(data) if data else 0}")

def blobstats(table, cols="streamId, minTs, maxTs, maxIndex, points", has_stream=True):
    q = f"SELECT {cols} FROM {table} ORDER BY minTs LIMIT 3"
    rows = cur.execute(q).fetchall()
    agg = cur.execute(f"SELECT COUNT(*), MIN(minTs), MAX(maxTs), SUM(LENGTH(points)), SUM(maxIndex) FROM {table}").fetchone()
    print(f"\n=== {table}: rows={agg[0]} minTs={agg[1]} maxTs={agg[2]} span={None if agg[1] is None else agg[2]-agg[1]} total_blob={agg[3]} sum_maxIndex={agg[4]}")
    if has_stream:
        for sid, n in cur.execute(f"SELECT streamId, COUNT(*) FROM {table} GROUP BY streamId"):
            print(f"   stream {sid!r}: {n} rows")
    for r in rows:
        blob = r[-1]
        print(f"   row: {r[:-1]} bloblen={len(blob)} head={blob[:48].hex()}")

for t in ("bodytrajectories", "posestreams", "slammetricdata"):
    blobstats(t)
for t in ("imudata", "edmdata", "fastaxisangledata", "slowaxisangledata"):
    blobstats(t, cols="minTs, maxTs, maxIndex, points", has_stream=False)

for t in ("panoimagedata", "userimagedata", "imagefeaturesdata", "maskdata"):
    agg = cur.execute(f"SELECT COUNT(*), MIN(ts), MAX(ts), SUM(LENGTH(data)), AVG(LENGTH(metadata)) FROM {t}").fetchone()
    print(f"\n=== {t}: rows={agg[0]} ts {agg[1]}..{agg[2]} total_data={agg[3]} avg_meta={agg[4]}")
    r = cur.execute(f"SELECT ts, metadata, data FROM {t} ORDER BY ts LIMIT 1").fetchone()
    if r:
        print(f"   first ts={r[0]} meta head={r[1][:300]!r}")
        print(f"   data head={r[2][:16].hex() if r[2] else None} len={len(r[2]) if r[2] else 0}")
