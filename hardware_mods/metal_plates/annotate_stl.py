"""annotate_stl.py — deterministic technical drawing of a plastic STL.

Renders the plate face (the side perpendicular to the chosen face axis)
with:

  - every silhouette vertex labelled with (X, Z) and an index
  - every edge labelled with its length in mm (and its angle, when not
    horizontal/vertical)
  - every hole on the face drawn at scale, labelled with (cx, cz),
    diameter, and an index
  - bounding-box width × height in the title

Outputs:
  <stem>_drawing.png  — high-DPI technical drawing (compact labels only)
  <stem>_drawing.txt  — human-readable table of vertices, edges, holes
  <stem>_drawing.json — machine-readable copy of every number on the PNG

Reproducible — same STL in, same drawing out.

Usage (inside nix-shell):

  python annotate_stl.py --stl docs/stl_files/router/Z_MOTOR_MOUNT.stl
  python annotate_stl.py --example examples/.../engine_holder_top_plate

If --example is passed, the script uses the rotated STL already produced
by rectify.py (2_flattened_image/stl_face_y.stl). For a bare --stl path,
the face axis is auto-detected (or overridden with --face-axis).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from stl import mesh  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from extract_holes import extract_holes  # noqa: E402
from rectify import detect_face_axis, write_rotated_stl  # noqa: E402


PPMM = 20.0  # rasterisation resolution for cv2 silhouette extraction
APPROX_EPS_MM = 0.25  # polygon-simplification tolerance


# ---------------------------------------------------------------------------
# Silhouette extraction
# ---------------------------------------------------------------------------
def _silhouette_at_y(tris: np.ndarray, mask: np.ndarray,
                     plate_y: float) -> tuple[list[tuple[float, float]], float]:
    tri_y_mean = tris[:, :, 1].mean(axis=1)
    sub = mask & (np.abs(tri_y_mean - plate_y) < 1.0)
    if not sub.any():
        return [], 0.0
    return _contour_from_proj(tris[sub][:, :, [0, 2]])


def _contour_from_proj(proj: np.ndarray) -> tuple[list[tuple[float, float]], float]:
    xs = proj[..., 0].ravel()
    zs = proj[..., 1].ravel()
    pad = 2.0
    x0, x1 = float(xs.min()) - pad, float(xs.max()) + pad
    z0, z1 = float(zs.min()) - pad, float(zs.max()) + pad
    W = int((x1 - x0) * PPMM)
    H = int((z1 - z0) * PPMM)
    img = np.zeros((H, W), dtype=np.uint8)
    for tri in proj:
        px = np.array(
            [[(p[0] - x0) * PPMM, (z1 - p[1]) * PPMM] for p in tri],
            dtype=np.int32,
        )
        cv2.fillPoly(img, [px], 255)
    contours, _ = cv2.findContours(img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours:
        return [], 0.0
    c = max(contours, key=cv2.contourArea)
    area = float(cv2.contourArea(c)) / (PPMM * PPMM)
    approx = cv2.approxPolyDP(c, APPROX_EPS_MM * PPMM, True)
    verts: list[tuple[float, float]] = []
    for p in approx[:, 0, :]:
        x = float(p[0]) / PPMM + x0
        z = z1 - float(p[1]) / PPMM
        verts.append((x, z))
    return verts, area


def silhouette(stl_path: Path,
               plate_y_min: float | None = None,
               plate_y_max: float | None = None) -> list[tuple[float, float]]:
    """Extract the plate-face silhouette in the XZ plane.

    If plate_y_min/max are provided (i.e. the STL has the plate bounded
    in Y, as after rectify's rotation), tries both outer faces and
    returns whichever silhouette encloses more area — that's almost
    always the flat plate side, opposite the one with bosses/ribs.
    """
    m = mesh.Mesh.from_file(str(stl_path))
    tris = m.vectors
    nl = np.linalg.norm(m.normals, axis=1, keepdims=True)
    n = np.where(nl > 1e-12, m.normals / nl, 0.0)
    mask = np.abs(n[:, 1]) > 0.95
    if not mask.any():
        raise SystemExit("STL has no faces perpendicular to Y.")

    if plate_y_min is None or plate_y_max is None:
        return _contour_from_proj(tris[mask][:, :, [0, 2]])[0]

    best: tuple[list[tuple[float, float]], float] = ([], 0.0)
    for plate_y in (plate_y_min, plate_y_max):
        candidate = _silhouette_at_y(tris, mask, plate_y)
        if candidate[1] > best[1]:
            best = candidate
    if not best[0]:
        raise SystemExit(
            f"no Y-perpendicular faces near Y={plate_y_min} or Y={plate_y_max}"
        )
    return best[0]


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------
def _is_axis_aligned(x1: float, z1: float, x2: float, z2: float) -> bool:
    deg = abs(float(np.degrees(np.arctan2(z2 - z1, x2 - x1))))
    return deg < 0.5 or abs(deg - 90.0) < 0.5 or abs(deg - 180.0) < 0.5


def _outward_unit(x: float, z: float, cx: float, cz: float) -> tuple[float, float]:
    dx, dz = x - cx, z - cz
    n = (dx * dx + dz * dz) ** 0.5
    if n < 1e-9:
        return 1.0, 0.0
    return dx / n, dz / n


def annotate(
    silhouette_pts: list[tuple[float, float]],
    y_holes: list[dict],
    title: str,
    out_png: Path,
) -> None:
    """Drawing with compact V#/H# labels only. Numbers live in the .txt."""
    xs = [p[0] for p in silhouette_pts]
    zs = [p[1] for p in silhouette_pts]
    x_min, x_max = min(xs), max(xs)
    z_min, z_max = min(zs), max(zs)
    span = max(x_max - x_min, z_max - z_min)
    margin = span * 0.10
    cx = sum(xs) / len(xs)
    cz = sum(zs) / len(zs)

    fig, ax = plt.subplots(figsize=(12, 10))
    ax.set_aspect("equal")

    loop_x = xs + [xs[0]]
    loop_z = zs + [zs[0]]
    ax.plot(loop_x, loop_z, "k-", lw=1.5)
    ax.fill(loop_x, loop_z, color="lightgray", alpha=0.2)

    # Vertices — small black dot + V# leader-line label.
    for i, (x, z) in enumerate(silhouette_pts):
        ax.plot(x, z, "ko", markersize=3)
        ux, uz = _outward_unit(x, z, cx, cz)
        off = margin * 0.55
        ax.annotate(
            f"V{i}",
            (x, z),
            xytext=(x + ux * off, z + uz * off),
            fontsize=7, ha="center", va="center",
            bbox=dict(boxstyle="round,pad=0.15", fc="white",
                      ec="black", alpha=0.9),
            arrowprops=dict(arrowstyle="-", color="black", lw=0.4),
        )

    # Holes — outline + H# leader-line label.
    for i, h in enumerate(y_holes):
        hx, hz, r = h["cx"], h["cz"], h["r"]
        ax.add_patch(plt.Circle((hx, hz), r,
                                fill=False, color="tab:red", lw=1.0))
        ax.plot(hx, hz, "+", color="tab:red", markersize=5)
        ux, uz = _outward_unit(hx, hz, cx, cz)
        off = r + margin * 0.35
        ax.annotate(
            f"H{i}",
            (hx, hz),
            xytext=(hx + ux * off, hz + uz * off),
            fontsize=7, ha="center", va="center", color="tab:red",
            bbox=dict(boxstyle="round,pad=0.15", fc="white",
                      ec="tab:red", alpha=0.9),
            arrowprops=dict(arrowstyle="-", color="tab:red", lw=0.4),
        )

    ax.set_xlim(x_min - margin, x_max + margin)
    ax.set_ylim(z_min - margin, z_max + margin)
    ax.grid(True, alpha=0.4, lw=0.4)
    ax.set_xlabel("X (mm)")
    ax.set_ylabel("Z (mm)")
    ax.set_title(
        f"{title}\nbbox  {x_max - x_min:.2f} × {z_max - z_min:.2f} mm  "
        f"(X[{x_min:.2f}, {x_max:.2f}]  Z[{z_min:.2f}, {z_max:.2f}])  "
        f"— see {out_png.stem}.txt for V/E/H tables"
    )
    fig.tight_layout()
    fig.savefig(out_png, dpi=200, bbox_inches="tight")
    plt.close(fig)


def _make_table(
    silhouette_pts: list[tuple[float, float]],
    y_holes: list[dict],
    title: str,
) -> str:
    n = len(silhouette_pts)
    xs = [p[0] for p in silhouette_pts]
    zs = [p[1] for p in silhouette_pts]
    out: list[str] = []
    out.append(f"# {title}")
    out.append("")
    out.append(
        f"bbox  {max(xs) - min(xs):.3f} × {max(zs) - min(zs):.3f} mm   "
        f"X[{min(xs):.3f}, {max(xs):.3f}]   Z[{min(zs):.3f}, {max(zs):.3f}]"
    )
    out.append("")
    out.append("VERTICES")
    out.append(f"  {'id':>3}  {'X (mm)':>10}  {'Z (mm)':>10}")
    for i, (x, z) in enumerate(silhouette_pts):
        out.append(f"  V{i:<2}  {x:10.3f}  {z:10.3f}")
    out.append("")
    out.append("EDGES")
    out.append(
        f"  {'id':>9}  {'length (mm)':>11}  {'angle (deg)':>11}"
    )
    for i in range(n):
        x1, z1 = silhouette_pts[i]
        x2, z2 = silhouette_pts[(i + 1) % n]
        length = ((x2 - x1) ** 2 + (z2 - z1) ** 2) ** 0.5
        deg = float(np.degrees(np.arctan2(z2 - z1, x2 - x1)))
        ang = "  axis-aligned" if _is_axis_aligned(x1, z1, x2, z2) else f"{deg:+11.3f}"
        out.append(f"  V{i:<2}→V{(i + 1) % n:<2}  {length:11.3f}  {ang}")
    out.append("")
    out.append("HOLES")
    out.append(
        f"  {'id':>3}  {'X (mm)':>10}  {'Z (mm)':>10}  {'Ø (mm)':>8}"
    )
    for i, h in enumerate(y_holes):
        out.append(
            f"  H{i:<2}  {h['cx']:10.3f}  {h['cz']:10.3f}  {h['d']:8.3f}"
        )
    out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def _drawing_payload(
    silhouette_pts: list[tuple[float, float]],
    y_holes: list[dict],
    stl_path: Path,
) -> dict:
    edges = []
    n = len(silhouette_pts)
    for i in range(n):
        x1, z1 = silhouette_pts[i]
        x2, z2 = silhouette_pts[(i + 1) % n]
        edges.append({
            "i": i,
            "from": [x1, z1],
            "to": [x2, z2],
            "length_mm": ((x2 - x1) ** 2 + (z2 - z1) ** 2) ** 0.5,
            "angle_deg": float(np.degrees(np.arctan2(z2 - z1, x2 - x1))),
        })
    holes = []
    for i, h in enumerate(y_holes):
        holes.append({
            "i": i,
            "cx": h["cx"],
            "cz": h["cz"],
            "d": h["d"],
            "r": h["r"],
        })
    xs = [p[0] for p in silhouette_pts]
    zs = [p[1] for p in silhouette_pts]
    return {
        "source_stl": str(stl_path),
        "vertices_xz_mm": [[x, z] for x, z in silhouette_pts],
        "edges": edges,
        "holes": holes,
        "bbox": {
            "x_min": min(xs), "x_max": max(xs),
            "z_min": min(zs), "z_max": max(zs),
            "width": max(xs) - min(xs),
            "height": max(zs) - min(zs),
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--stl", type=Path)
    g.add_argument("--example", type=Path)
    ap.add_argument("--face-axis", choices=["auto", "X", "Y", "Z"],
                    default="auto")
    ap.add_argument("--out", type=Path, default=None,
                    help="output PNG path (default: alongside STL)")
    args = ap.parse_args()

    tmpdir: Path | None = None
    try:
        if args.example:
            rotated = args.example / "2_flattened_image" / "stl_face_y.stl"
            if not rotated.exists():
                raise SystemExit(
                    f"{rotated} not found. Run rectify.py first, or pass --stl."
                )
            work_stl = rotated
            display_name = f"{args.example.name} — {rotated.stem}"
            out_png = args.out or (args.example / "3_measurements"
                                    / f"{rotated.stem}_drawing.png")
        else:
            src = args.stl
            if not src.exists():
                raise SystemExit(f"{src} does not exist")
            face_axis = args.face_axis
            if face_axis == "auto":
                face_axis = detect_face_axis(
                    extract_holes(src, verbose=False)
                )
            if face_axis == "Y":
                work_stl = src
            else:
                tmpdir = Path(tempfile.mkdtemp(prefix="annotate_stl_"))
                work_stl = tmpdir / (src.stem + ".rotated.stl")
                write_rotated_stl(src, face_axis, work_stl)
            display_name = src.name
            out_png = args.out or src.with_name(src.stem + "_drawing.png")

        plate = extract_holes(work_stl, verbose=False)
        y_holes = [h for h in plate["holes"] if h["axis"] == "Y"]
        pts = silhouette(
            work_stl,
            plate_y_min=float(plate["plate_y_min"]),
            plate_y_max=float(plate["plate_y_max"]),
        )

        out_png.parent.mkdir(parents=True, exist_ok=True)
        annotate(pts, y_holes, display_name, out_png)
        json_path = out_png.with_suffix(".json")
        json_path.write_text(json.dumps(
            _drawing_payload(pts, y_holes, work_stl), indent=2
        ))
        txt_path = out_png.with_suffix(".txt")
        txt_path.write_text(_make_table(pts, y_holes, display_name))
        print(f"wrote {out_png}")
        print(f"wrote {txt_path}")
        print(f"wrote {json_path}")
    finally:
        if tmpdir is not None:
            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    main()
