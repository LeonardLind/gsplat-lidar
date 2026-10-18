"""Read-only schema dump of a Leica BLK2GO .b2g file (SQLite)."""
import pathlib
import sqlite3
import sys

p = pathlib.Path(sys.argv[1]).resolve()
con = sqlite3.connect(f"file:{p.as_posix()}?mode=ro&immutable=1", uri=True)
cur = con.cursor()
rows = cur.execute("SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name").fetchall()
for typ, name, tbl, sql in rows:
    if typ == "table":
        try:
            n = cur.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
        except Exception as e:
            n = f"err {e}"
        print(f"\n=== TABLE {name}  rows={n}")
        print(sql)
    elif typ in ("index", "view", "trigger"):
        print(f"--- {typ} {name} on {tbl}: {sql}")
print("\nuser_version", cur.execute("PRAGMA user_version").fetchone(), "application_id", cur.execute("PRAGMA application_id").fetchone())
