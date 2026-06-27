"""Extract circular through-holes from a flat-plate STL.

The plate's main face is typically perpendicular to Y, but some plates
have perpendicular fins whose hole axes run along X or Z. We scan for
hole walls aligned with each of the three principal axes, project each
cylinder back onto the plate (X, Z) plane, and write every candidate to
holes.json so the per-part build123d script can pick which ones it wants.

Usage:
  python extract_holes.py <path/to/plate.stl> [--out path/to/holes.json]

If --out is omitted, holes.json is written next to the input STL.
"""
import argparse
from collections import Counter, defaultdict
from pathlib import Path
import json

import numpy as np
from sklearn.neighbors import KDTree
from stl import mesh


def fit_circle_2d(p, q):
    A = np.column_stack([2 * p, 2 * q, np.ones_like(p)])
    b = p * p + q * q
    sol, *_ = np.linalg.lstsq(A, b, rcond=None)
    cp, cq, c = sol
    r = float(np.sqrt(c + cp * cp + cq * cq))
    radii = np.sqrt((p - cp) ** 2 + (q - cq) ** 2)
    rms = float(np.sqrt(np.mean((radii - r) ** 2)))
    return float(cp), float(cq), r, rms


def peel_circles(points, *, rms_tol=0.05, r_min=0.8, r_max=40.0, min_pts=6):
    used = np.zeros(len(points), dtype=bool)
    out = []
    while True:
        avail = np.where(~used)[0]
        if len(avail) < min_pts:
            break
        active = points[avail]
        tree = KDTree(active)
        best = None
        for i in range(len(avail)):
            for k in (4, 6, 8, 12, 16, 24, 32):
                if k > len(avail):
                    break
                idx = tree.query([active[i]], k=k, return_distance=False)[0]
                cp, cq, r, rms = fit_circle_2d(active[idx, 0], active[idx, 1])
                if not (r_min <= r <= r_max) or rms / r > rms_tol:
                    continue
                d = np.hypot(active[:, 0] - cp, active[:, 1] - cq)
                grow = np.abs(d - r) < max(0.4, 0.05 * r)
                if grow.sum() < min_pts:
                    continue
                cp2, cq2, r2, rms2 = fit_circle_2d(active[grow, 0], active[grow, 1])
                if rms2 / r2 > rms_tol or not (r_min <= r2 <= r_max):
                    continue
                key = (rms2 / r2, -int(grow.sum()))
                if best is None or key < best[0]:
                    best = (key, cp2, cq2, r2, rms2, int(grow.sum()), avail[grow])
        if best is None:
            break
        _, cp, cq, r, rms, n, used_idx = best
        used[used_idx] = True
        out.append(dict(cp=cp, cq=cq, r=r, rms=rms, n=n))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("stl", type=Path, help="input STL")
    ap.add_argument("--out", type=Path, default=None,
                    help="output JSON (default: holes.json next to STL)")
    args = ap.parse_args()

    out_path = args.out or args.stl.with_name("holes.json")

    m = mesh.Mesh.from_file(str(args.stl))
    tris = m.vectors
    grid = 1000
    keys = np.round(tris * grid).astype(np.int64)

    edge_to_tris = defaultdict(list)
    for ti in range(len(tris)):
        for vi in range(3):
            a = tuple(keys[ti, vi])
            b = tuple(keys[ti, (vi + 1) % 3])
            e = (a, b) if a < b else (b, a)
            edge_to_tris[e].append(ti)

    # axis -> seam (other1_val, other2_val, length, midpoint_along_axis)
    seams_by_axis = {0: [], 1: [], 2: []}
    for (a, b), owners in edge_to_tris.items():
        if len(owners) != 2:
            continue
        # Check parallel to each axis
        for axis in (0, 1, 2):
            others = [i for i in range(3) if i != axis]
            if a[others[0]] == b[others[0]] and a[others[1]] == b[others[1]] and a[axis] != b[axis]:
                p = a[others[0]] / grid
                q = a[others[1]] / grid
                length = abs(a[axis] - b[axis]) / grid
                axis_mid = (a[axis] + b[axis]) / 2 / grid
                seams_by_axis[axis].append((p, q, length, axis_mid))
                break

    all_holes = []
    axis_name = {0: "X", 1: "Y", 2: "Z"}
    for axis, seams in seams_by_axis.items():
        if not seams:
            continue
        arr = np.asarray(seams)
        pts = arr[:, :2]
        lens = arr[:, 2]
        axis_mid = arr[:, 3]
        print(f"\n=== axis {axis_name[axis]} : {len(seams)} seams ===")
        lens_round = np.round(lens).astype(int)
        hist = Counter(lens_round.tolist())
        print("  length histogram:", sorted(hist.items()))

        for L, count in sorted(hist.items()):
            if count < 6 or L < 2:
                continue
            mask = lens_round == L
            sub_pts = pts[mask]
            sub_mid = axis_mid[mask]
            holes = peel_circles(sub_pts)
            for h in holes:
                d_to_center = np.hypot(sub_pts[:, 0] - h["cp"], sub_pts[:, 1] - h["cq"])
                close = np.abs(d_to_center - h["r"]) < max(0.4, 0.05 * h["r"])
                # Hole start/end along the cylinder axis
                start = float(sub_mid[close].min() - L / 2)
                end = float(sub_mid[close].max() + L / 2)
                h.update(axis=axis_name[axis], thickness=int(L), start=round(start, 2), end=round(end, 2))
                all_holes.append(h)

    # Dedup
    final = []
    for h in all_holes:
        dup = False
        for k in final:
            if (
                k["axis"] == h["axis"]
                and abs(h["cp"] - k["cp"]) < 0.5
                and abs(h["cq"] - k["cq"]) < 0.5
                and abs(h["r"] - k["r"]) < 0.3
                and h["thickness"] == k["thickness"]
            ):
                dup = True
                break
        if not dup:
            final.append(h)

    # Pretty print
    print(f"\n=== Detected holes: {len(final)} ===")
    print(f"{'axis':>4} {'cp':>9} {'cq':>9} {'d':>7} {'r':>7} {'thk':>5} {'start':>7} {'end':>7} {'rms':>7} {'n':>4}")
    for h in sorted(final, key=lambda x: (x["axis"], round(x["cq"], 1), round(x["cp"], 1))):
        print(
            f"{h['axis']:>4} {h['cp']:>9.3f} {h['cq']:>9.3f} {2*h['r']:>7.3f} {h['r']:>7.3f} "
            f"{h['thickness']:>5d} {h['start']:>7.2f} {h['end']:>7.2f} {h['rms']:>7.4f} {h['n']:>4d}"
        )

    # Serialize. For Y-axis holes (the plate's natural thickness direction),
    # (cp, cq) maps to (cx, cz) directly. For X-axis (the perpendicular fin),
    # (cp, cq) is (cy, cz). For Z-axis it's (cx, cy). The metal plate is flat,
    # so X-axis holes project onto the plate at (cx_of_fin_attachment, cq=cz).
    serial = []
    for h in final:
        if h["axis"] == "Y":
            cx, cz = h["cp"], h["cq"]
            cy_at = (h["start"] + h["end"]) / 2
        elif h["axis"] == "X":
            cy, cz = h["cp"], h["cq"]
            cx = (h["start"] + h["end"]) / 2  # fin midplane in X
            cy_at = cy
        else:  # Z
            cx, cy = h["cp"], h["cq"]
            cz = (h["start"] + h["end"]) / 2
            cy_at = cy

        serial.append(
            dict(
                axis=h["axis"],
                cx=round(float(cx), 3),
                cy=round(float(cy_at), 3),
                cz=round(float(cz), 3),
                r=round(float(h["r"]), 3),
                d=round(2 * float(h["r"]), 3),
                rms=round(float(h["rms"]), 4),
                n=int(h["n"]),
                thickness=int(h["thickness"]),
                start=float(h["start"]),
                end=float(h["end"]),
            )
        )

    plate = dict(
        plate_x_min=float(tris[:, :, 0].min()),
        plate_x_max=float(tris[:, :, 0].max()),
        plate_y_min=float(tris[:, :, 1].min()),
        plate_y_max=float(tris[:, :, 1].max()),
        plate_z_min=float(tris[:, :, 2].min()),
        plate_z_max=float(tris[:, :, 2].max()),
        holes=serial,
    )
    out_path.write_text(json.dumps(plate, indent=2))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
