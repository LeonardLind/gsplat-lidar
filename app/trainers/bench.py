"""GPU benchmark for training-time estimates (runs in the `gs` environment, about a minute).

Times one gsplat training step (render 1600x1600 with SH degree 3, L1 loss, backward, Adam) for
random Gaussians at several counts, the way simple_trainer does it. Real scenes differ (Gaussian
sizes), so the studio replaces these numbers with real runs as soon as there are some.

    python bench.py <out.json> [--size 1600]
"""
from __future__ import annotations

import argparse
import json
import math
import time

import torch
from gsplat import rasterization


def step_time(n: int, size: int, iters: int = 25) -> float:
    dev = "cuda"
    g = torch.Generator(device=dev).manual_seed(0)
    # A room-sized cloud (4 m cube) seen from its centre-ish, Gaussian sizes like a trained indoor scene.
    means = ((torch.rand(n, 3, device=dev, generator=g) - 0.5) * 4).requires_grad_()
    scales = torch.log(torch.rand(n, 3, device=dev, generator=g) * 0.02 + 0.004).requires_grad_()
    quats = torch.randn(n, 4, device=dev, generator=g).requires_grad_()
    opac = torch.logit(torch.rand(n, device=dev, generator=g) * 0.8 + 0.1).requires_grad_()
    sh0 = (torch.rand(n, 1, 3, device=dev, generator=g) - 0.5).requires_grad_()
    shn = (torch.zeros(n, 15, 3, device=dev)).requires_grad_()
    opt = torch.optim.Adam([means, scales, quats, opac, sh0, shn], lr=1e-3)
    f = size / 2 / math.tan(math.radians(45))
    K = torch.tensor([[f, 0, size / 2], [0, f, size / 2], [0, 0, 1]], device=dev)[None]
    target = torch.rand(1, size, size, 3, device=dev, generator=g)

    def one(k: int) -> None:
        a = 0.3 * k
        eye = torch.tensor([0.6 * math.cos(a), 0.6 * math.sin(a), 0.0], device=dev)
        fwd = -eye / eye.norm()
        right = torch.linalg.cross(fwd, torch.tensor([0.0, 0.0, 1.0], device=dev))
        right = right / right.norm()
        down = torch.linalg.cross(fwd, right)
        R = torch.stack([right, down, fwd])  # world -> camera rows (OpenCV: x right, y down, z forward)
        view = torch.eye(4, device=dev)
        view[:3, :3] = R
        view[:3, 3] = -R @ eye
        img, _, _ = rasterization(means, torch.nn.functional.normalize(quats, dim=-1), torch.exp(scales),
                                  torch.sigmoid(opac), torch.cat([sh0, shn], 1), view[None], K, size, size,
                                  sh_degree=3, packed=False)
        loss = (img - target).abs().mean()
        loss.backward()
        opt.step()
        opt.zero_grad(set_to_none=True)

    for k in range(5):
        one(k)
    torch.cuda.synchronize()
    t0 = time.perf_counter()
    for k in range(iters):
        one(k + 5)
    torch.cuda.synchronize()
    return (time.perf_counter() - t0) / iters


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--size", type=int, default=1600)
    a = ap.parse_args()
    vram = torch.cuda.get_device_properties(0).total_memory
    points = []
    for n in (250_000, 500_000, 1_000_000, 2_000_000, 3_000_000):
        if n * 248 * 6 > vram * 0.6:  # params + grads + Adam moments, leave room for the rasterizer
            break
        try:
            s = step_time(n, a.size)
        except torch.OutOfMemoryError:
            break
        finally:
            torch.cuda.empty_cache()
        points.append({"gaussians": n, "s_per_step": round(s, 5)})
        print(f"{n:>9,} Gaussians: {s * 1000:.1f} ms/step", flush=True)
    res = {"gpu": torch.cuda.get_device_name(0), "size": a.size, "points": points, "time": time.time()}
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2)


if __name__ == "__main__":
    main()
