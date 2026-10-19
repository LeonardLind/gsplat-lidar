"""Print a QR code for a URL in the terminal and save it as a PNG, so an iPad can scan it.

    C:\\dev\\envs\\pipe\\Scripts\\python.exe scripts\\tablet_qr.py <url> [out.png]

Needs `segno` (uv pip install --python C:\\dev\\envs\\pipe\\Scripts\\python.exe segno).
"""
import sys

import segno

if len(sys.argv) < 2:
    raise SystemExit(__doc__)
url = sys.argv[1]
out = sys.argv[2] if len(sys.argv) > 2 else "tablet_qr.png"
qr = segno.make(url, error="m")
qr.terminal(compact=True)
qr.save(out, scale=10, border=3)
print(f"\n{url}\nsaved {out}")
