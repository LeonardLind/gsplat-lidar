// Small line chart on a canvas (training loss, PSNR, Gaussian count). x = training step.

export interface ChartOpts { color: string; xMax: number; log?: boolean; dots?: boolean; format?: (v: number) => string }

export function drawChart(canvas: HTMLCanvasElement, pts: [number, number][], o: ChartOpts): void {
  const dpr = devicePixelRatio || 1;
  const w = canvas.clientWidth, h = canvas.clientHeight;
  if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
  }
  const g = canvas.getContext("2d")!;
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.clearRect(0, 0, w, h);
  const padL = 44, padR = 8, padT = 8, padB = 18;
  const fmt = o.format ?? ((v: number) => (Math.abs(v) >= 100 ? v.toFixed(0) : v.toPrecision(3)));
  g.font = "11px system-ui, sans-serif";
  g.fillStyle = "rgba(154,161,178,.9)";
  g.strokeStyle = "rgba(255,255,255,.07)";
  g.lineWidth = 1;
  if (!pts.length) {
    g.fillText("waiting for data…", padL, h / 2);
    return;
  }
  const tf = (v: number) => (o.log ? Math.log10(Math.max(v, 1e-6)) : v);
  let lo = Infinity, hi = -Infinity;
  for (const [, v] of pts) (lo = Math.min(lo, tf(v)), hi = Math.max(hi, tf(v)));
  if (hi - lo < 1e-9) (hi += 0.5, lo -= 0.5);
  const span = hi - lo;
  lo -= span * 0.08;
  hi += span * 0.08;
  const X = (s: number) => padL + (s / Math.max(o.xMax, 1)) * (w - padL - padR);
  const Y = (v: number) => padT + (1 - (tf(v) - lo) / (hi - lo)) * (h - padT - padB);
  // Grid: 3 horizontal lines with values.
  for (let k = 0; k <= 2; k++) {
    const yv = lo + ((hi - lo) * k) / 2;
    const y = padT + (1 - k / 2) * (h - padT - padB);
    g.beginPath();
    g.moveTo(padL, y + 0.5);
    g.lineTo(w - padR, y + 0.5);
    g.stroke();
    g.fillText(fmt(o.log ? 10 ** yv : yv), 2, y + 4);
  }
  g.fillText("0", padL, h - 4);
  const xm = `${Math.round(o.xMax / 1000)}k`;
  g.fillText(xm, w - padR - g.measureText(xm).width, h - 4);
  g.strokeStyle = o.color;
  g.lineWidth = 1.6;
  g.beginPath();
  pts.forEach(([s, v], i) => (i ? g.lineTo(X(s), Y(v)) : g.moveTo(X(s), Y(v))));
  g.stroke();
  if (o.dots || pts.length < 3) {
    g.fillStyle = o.color;
    for (const [s, v] of pts) {
      g.beginPath();
      g.arc(X(s), Y(v), 2.6, 0, Math.PI * 2);
      g.fill();
    }
  }
}
