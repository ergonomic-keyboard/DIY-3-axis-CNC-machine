"""build_model.py — stage 6 of the metal-plate workflow.

Reads the polygon trace (stage 5) and the calibration metadata (stage 2),
generates the parametric build123d 3D model of the metal plate including
the Y-axis holes from the plastic STL, and writes STEP/STL + a plan-view
PNG into stage 5.

Reads:
  <example>/4_outline/<...>_polygon.json
  <example>/2_flattened_image/<...>_rect.json
  <example>/2_flattened_image/holes_from_stl.json

Writes (into <example>/5_models_and_renders/):
  <name>_metal.step
  <name>_metal.stl
  <name>_metal_plan.png        — annotated 2D plan view
  <name>_metal_hole_diff.json  — diff between model holes and STL holes
                                 (warns to stdout if any hole moved or resized)

Optional:
  --view        open the STEP in f3d after build
  --thickness   override plate thickness (mm, default 6.0)
  --no-holes    skip punching holes (outline-only quick check)

Refuses to start if any upstream stage file is missing.

Usage:

  nix-shell hardware_mods/metal_plates/shell.nix --run \\
    "python hardware_mods/metal_plates/build_model.py \\
       --example hardware_mods/metal_plates/examples/.../P20_left_side_plate_p1of3"
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

import matplotlib

import os
if not os.environ.get("MPLBACKEND"):
    for backend in ("QtAgg", "TkAgg", "Agg"):
        try:
            matplotlib.use(backend, force=True)
            break
        except Exception:
            continue

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.collections import PolyCollection  # noqa: E402
from matplotlib.path import Path as MplPath  # noqa: E402
from stl import mesh as stl_mesh  # noqa: E402
from build123d import (  # noqa: E402
    BuildLine,
    BuildPart,
    BuildSketch,
    Circle,
    Locations,
    Mode,
    Plane,
    Polyline,
    export_step,
    export_stl,
    extrude,
    make_face,
)


# =============================================================================
# Stage-input loading + validation
# =============================================================================
def _single_file(stage_dir: Path, pattern: str, what: str) -> Path:
    if not stage_dir.is_dir():
        raise SystemExit(f"missing stage folder: {stage_dir}")
    hits = sorted(stage_dir.glob(pattern))
    if not hits:
        raise SystemExit(
            f"no {what} found in {stage_dir} (pattern {pattern}). "
            "Did you run the earlier stages?"
        )
    if len(hits) > 1:
        listing = "\n  ".join(p.name for p in hits)
        raise SystemExit(
            f"{len(hits)} {what} candidates in {stage_dir}; ambiguous:\n  {listing}\n"
            "Remove the ones you don't want, or specify by hand."
        )
    return hits[0]


def load_stage_inputs(example: Path) -> dict:
    stage2 = example / "2_flattened_image"
    stage4 = example / "4_outline"
    rect_json = _single_file(stage2, "*_rect.json", "rectification metadata")
    holes_cache = stage2 / "holes_from_stl.json"
    if not holes_cache.exists():
        raise SystemExit(
            f"missing {holes_cache} — re-run rectify.py to populate the hole cache."
        )

    # Prefer an edited polygon (from align_outline.py) over the raw trace.
    edited = sorted(stage4.glob("*_polygon_edited.json"))
    raw = [p for p in sorted(stage4.glob("*_polygon.json"))
           if not p.name.endswith("_edited.json")]
    if edited:
        if len(edited) > 1:
            raise SystemExit(
                f"multiple edited polygons in {stage4}; remove the stale ones."
            )
        poly_json = edited[0]
        print(f"using edited polygon: {poly_json.name}")
    elif raw:
        if len(raw) > 1:
            raise SystemExit(
                f"multiple polygon traces in {stage4}; remove the stale ones."
            )
        poly_json = raw[0]
    else:
        raise SystemExit(
            f"no polygon trace in {stage4}. Run trace_polygon.py first."
        )

    rect = json.loads(rect_json.read_text())
    holes = json.loads(holes_cache.read_text())
    poly = json.loads(poly_json.read_text())
    if not poly.get("closed", False):
        print("warning: polygon is not marked closed; the build will still "
              "close it by connecting the last vertex back to the first.")
    return dict(rect=rect, holes=holes, poly=poly, poly_json=poly_json)


# =============================================================================
# Coordinate conversion: rectified-image pixels → plate-frame (X, Z) mm
# =============================================================================
def px_to_mm(rect: dict) -> "callable":
    """Return a closure that converts (px, py) on the rectified PNG to (X, Z) mm."""
    scale = float(rect["scale_px_per_mm"])
    x_min = float(rect["canvas_real_bounds_mm"]["x_min"])
    z_max = float(rect["canvas_real_bounds_mm"]["z_max"])

    def to_mm(px: float, py: float) -> tuple[float, float]:
        # Pixel (0, 0) is at (x_min, z_max). +px walks +X, +py walks -Z.
        return (x_min + px / scale, z_max - py / scale)

    return to_mm


# =============================================================================
# 3D model
# =============================================================================
def build_part(
    outline_xz_mm: list[tuple[float, float]],
    y_holes: list[dict],
    *,
    thickness: float,
    punch_holes: bool,
) -> tuple["BuildPart", list[dict], list[dict]]:
    """Build the plate as a sketch on XZ extruded along +Y.

    Returns (part, hole_records, skipped_holes). ``hole_records`` lists each
    hole punched into the metal plate; ``skipped_holes`` lists STL holes that
    fell outside the polygon (plastic has more material there).
    """
    pts_closed = list(outline_xz_mm) + [outline_xz_mm[0]]
    poly_path = MplPath(outline_xz_mm)

    # Filter holes to those whose centre lies inside the polygon. Plastic
    # parts have features the metal plate doesn't (the metal silhouette is
    # smaller), so STL holes outside the polygon should be skipped.
    holes_to_punch: list[dict] = []
    holes_outside: list[dict] = []
    if punch_holes:
        for h in y_holes:
            if poly_path.contains_point((h["cx"], h["cz"])):
                holes_to_punch.append(h)
            else:
                holes_outside.append(h)

    hole_records: list[dict] = []
    with BuildPart() as plate:
        with BuildSketch(Plane.XZ):
            with BuildLine():
                Polyline(*pts_closed)
            make_face()
            for h in holes_to_punch:
                cx = float(h["cx"])
                cz = float(h["cz"])
                r = float(h["r"])
                with Locations((cx, cz)):
                    Circle(radius=r, mode=Mode.SUBTRACT)
                hole_records.append(dict(cx=cx, cz=cz, r=r))
        extrude(amount=thickness)

    if holes_outside:
        print(
            f"note: {len(holes_outside)} STL hole(s) lie outside the metal "
            "plate's traced polygon and were skipped (plastic has more material here):"
        )
        for h in holes_outside:
            print(f"  ({h['cx']:7.2f}, {h['cz']:7.2f})  r={h['r']:.2f}")

    return plate, hole_records, holes_outside


# =============================================================================
# Plan-view PNG render (matplotlib, not build123d — fast and reliable)
# =============================================================================
def _detect_slot_nut_centres(
    outline_xz_mm: list[tuple[float, float]],
    *,
    ac: float = 9.24,            # M5 nut across-corners
    ledge_len_range: tuple[float, float] = (1.0, 3.0),
) -> list[tuple[float, float]]:
    """Find M5 keyhole slots and return the nut centre (cx, cz) for each.

    A slot's two short horizontal ledge edges (one per side) share a Z value;
    the slot centre X is the midpoint between them. Whether the slot opens up
    or down is decided by which plate edge the ledge is closer to.
    """
    zs = [p[1] for p in outline_xz_mm]
    plate_top_z, plate_bottom_z = max(zs), min(zs)
    plate_mid_z = (plate_top_z + plate_bottom_z) / 2
    n = len(outline_xz_mm)
    ledges_by_z: dict[float, list[tuple[float, float]]] = {}
    for i in range(n):
        a = outline_xz_mm[i]
        b = outline_xz_mm[(i + 1) % n]
        if abs(b[1] - a[1]) > 1e-4:
            continue
        L = abs(b[0] - a[0])
        if not (ledge_len_range[0] < L < ledge_len_range[1]):
            continue
        key = round(a[1], 3)
        ledges_by_z.setdefault(key, []).append((a, b))
    centres: list[tuple[float, float]] = []
    for z, pairs in ledges_by_z.items():
        # Multiple slots can share a Z (e.g. TL and TR both at ledge Z=204.79).
        # Sort the ledges along X and pair consecutive ones — each pair forms
        # one slot.
        sorted_pairs = sorted(pairs, key=lambda ab: (ab[0][0] + ab[1][0]) / 2)
        if len(sorted_pairs) % 2 != 0:
            continue
        cz = z - ac / 2 if z > plate_mid_z else z + ac / 2
        for k in range(0, len(sorted_pairs), 2):
            xm1 = (sorted_pairs[k][0][0] + sorted_pairs[k][1][0]) / 2
            xm2 = (sorted_pairs[k + 1][0][0] + sorted_pairs[k + 1][1][0]) / 2
            centres.append(((xm1 + xm2) / 2, cz))
    return centres


def _draw_m5_nuts(ax, centres: list[tuple[float, float]], *,
                  af: float = 8.0, ac: float = 9.24,
                  edgecolor: str = "red", lw: float = 1.4,
                  zorder: int = 10) -> None:
    """Draw an M5 hex nut outline (captive orientation: flats vertical) at
    each (cx, cz). AF horizontal, AC vertical."""
    h, w, q = ac / 2, af / 2, ac / 4
    for cx, cz in centres:
        corners = [
            (cx, cz + h), (cx + w, cz + q), (cx + w, cz - q),
            (cx, cz - h), (cx - w, cz - q), (cx - w, cz + q),
        ]
        xs = [c[0] for c in corners] + [corners[0][0]]
        zs = [c[1] for c in corners] + [corners[0][1]]
        ax.plot(xs, zs, color=edgecolor, lw=lw, zorder=zorder)
        ax.plot([cx], [cz], "+", color=edgecolor, ms=6, zorder=zorder)


def render_overlay(
    outline_xz_mm: list[tuple[float, float]],
    hole_records: list[dict],
    stl_path: Path,
    skipped_holes: list[dict],
    out_path: Path,
    *,
    title: str,
) -> None:
    """Metal plate (filled) on top of the plastic-plate XZ projection (faint).

    Both layers share the same plate-frame (X, Z) mm coordinates — so the
    holes align by construction. Lets the user eyeball whether the metal
    plate covers the plastic part's mounting features.
    """
    fig, ax = plt.subplots(figsize=(8, 10))

    # --- Plastic silhouette (Y-face triangles) ---
    m = stl_mesh.Mesh.from_file(str(stl_path))
    tris = m.vectors
    norms = m.normals.copy()
    nlen = np.linalg.norm(norms, axis=1, keepdims=True)
    n_unit = np.where(nlen > 1e-12, norms / nlen, 0.0)
    y_face_mask = np.abs(n_unit[:, 1]) > 0.95
    if y_face_mask.any():
        proj = tris[y_face_mask][:, :, [0, 2]]
        ax.add_collection(PolyCollection(
            proj, facecolor="tab:red", edgecolor="darkred",
            lw=0.1, alpha=0.18, label="plastic",
        ))

    # --- Metal plate (polygon + holes) ---
    pts = list(outline_xz_mm) + [outline_xz_mm[0]]
    xs = [p[0] for p in pts]; zs = [p[1] for p in pts]
    ax.fill(xs, zs, facecolor="tab:blue", edgecolor="navy",
            lw=1.2, alpha=0.45, zorder=2)
    for h in hole_records:
        ax.add_patch(plt.Circle(
            (h["cx"], h["cz"]), h["r"], fill=True,
            facecolor="white", edgecolor="navy", lw=0.8, zorder=3,
        ))

    # --- Skipped holes (in plastic, not in metal) — for visibility ---
    for h in skipped_holes:
        ax.add_patch(plt.Circle(
            (h["cx"], h["cz"]), h["r"], fill=False,
            edgecolor="red", lw=1.5, linestyle="--", zorder=4,
        ))

    # --- M5 nut outlines inside each keyhole slot, resting on the ledge ---
    _draw_m5_nuts(ax, _detect_slot_nut_centres(outline_xz_mm))

    # --- Limits: enclose both layers ---
    all_x = list(xs) + [tris[:, :, 0].min(), tris[:, :, 0].max()]
    all_z = list(zs) + [tris[:, :, 2].min(), tris[:, :, 2].max()]
    ax.set_xlim(min(all_x) - 10, max(all_x) + 10)
    ax.set_ylim(min(all_z) - 10, max(all_z) + 10)
    ax.set_aspect("equal")
    ax.set_xlabel("X (mm)")
    ax.set_ylabel("Z (mm)")
    ax.grid(alpha=0.3, lw=0.5)
    ax.set_title(
        f"{title} — metal (blue) vs plastic (red)\n"
        f"dashed red = plastic hole skipped (outside metal silhouette)"
    )
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def render_plan(
    outline_xz_mm: list[tuple[float, float]],
    hole_records: list[dict],
    out_path: Path,
    *,
    title: str,
) -> None:
    fig, ax = plt.subplots(figsize=(8, 10))
    pts = list(outline_xz_mm) + [outline_xz_mm[0]]
    xs = [p[0] for p in pts]
    zs = [p[1] for p in pts]
    ax.fill(xs, zs, facecolor="lightgray", edgecolor="black", lw=1.2, alpha=0.7)
    for h in hole_records:
        ax.add_patch(
            plt.Circle((h["cx"], h["cz"]), h["r"], fill=True,
                       facecolor="white", edgecolor="black", lw=0.8)
        )
    # M5 nut outlines inside each keyhole slot, resting on the ledge.
    _draw_m5_nuts(ax, _detect_slot_nut_centres(outline_xz_mm))
    bbx0, bbx1 = min(xs), max(xs)
    bbz0, bbz1 = min(zs), max(zs)
    ax.set_xlim(bbx0 - 10, bbx1 + 10)
    ax.set_ylim(bbz0 - 10, bbz1 + 10)
    ax.set_aspect("equal")
    ax.set_xlabel("X (mm)")
    ax.set_ylabel("Z (mm)")
    ax.grid(alpha=0.3, lw=0.5)
    ax.set_title(
        f"{title}\n"
        f"{bbx1 - bbx0:.1f} mm W  ×  {bbz1 - bbz0:.1f} mm H  "
        f"({len(hole_records)} holes)"
    )
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


# =============================================================================
# Hole-diff vs the plastic STL
# =============================================================================
def compute_hole_diff(
    model_holes: list[dict],
    stl_y_holes: list[dict],
    *,
    tol_pos: float = 0.05,
    tol_r: float = 0.05,
) -> dict:
    """Return a diff between model holes and STL Y-axis holes."""
    matched: list[dict] = []
    unmatched_model: list[dict] = []
    unmatched_stl = list(stl_y_holes)

    for m in model_holes:
        best = None
        best_d = float("inf")
        for i, s in enumerate(unmatched_stl):
            d = float(np.hypot(m["cx"] - s["cx"], m["cz"] - s["cz"]))
            if d < best_d:
                best_d = d
                best = i
        if best is not None and best_d < 1.0:
            s = unmatched_stl.pop(best)
            matched.append(dict(
                cx_stl=s["cx"], cz_stl=s["cz"], r_stl=s["r"],
                cx_model=m["cx"], cz_model=m["cz"], r_model=m["r"],
                dx=m["cx"] - s["cx"], dz=m["cz"] - s["cz"],
                dr=m["r"] - s["r"], dist=best_d,
            ))
        else:
            unmatched_model.append(m)

    moved = [m for m in matched
             if abs(m["dx"]) > tol_pos or abs(m["dz"]) > tol_pos
             or abs(m["dr"]) > tol_r]
    return dict(
        matched=matched,
        moved=moved,
        unmatched_in_model=unmatched_model,
        unmatched_in_stl=unmatched_stl,
    )


def warn_if_holes_differ(diff: dict) -> None:
    moved = diff["moved"]
    miss_m = diff["unmatched_in_model"]
    miss_s = diff["unmatched_in_stl"]
    if not (moved or miss_m or miss_s):
        print("hole check: ✓ model hole positions/sizes match the plastic STL.")
        return
    print("hole check: ⚠ DIFFERENCES from plastic STL:")
    for h in moved:
        print(f"  moved/resized: STL ({h['cx_stl']:.2f}, {h['cz_stl']:.2f}) r={h['r_stl']:.2f} "
              f"→ model ({h['cx_model']:.2f}, {h['cz_model']:.2f}) r={h['r_model']:.2f}  "
              f"Δpos=({h['dx']:+.2f},{h['dz']:+.2f}) Δr={h['dr']:+.2f}")
    for h in miss_m:
        print(f"  in model but NOT in STL: ({h['cx']:.2f}, {h['cz']:.2f}) r={h['r']:.2f}")
    for h in miss_s:
        print(f"  in STL but NOT in model: ({h['cx']:.2f}, {h['cz']:.2f}) r={h['r']:.2f}")


# =============================================================================
# Main
# =============================================================================
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--example", type=Path, required=True,
                    help="example folder (the one containing the 0_..5_ stage dirs)")
    ap.add_argument("--thickness", type=float, default=6.0,
                    help="plate thickness in mm (default 6)")
    ap.add_argument("--no-holes", action="store_true",
                    help="skip punching the Y-axis holes (outline-only quick check)")
    ap.add_argument("--view", action="store_true",
                    help="open the STEP in f3d after build")
    args = ap.parse_args()

    example: Path = args.example.resolve()
    if not example.is_dir():
        raise SystemExit(f"--example folder does not exist: {example}")

    inputs = load_stage_inputs(example)
    rect = inputs["rect"]
    holes_data = inputs["holes"]
    poly = inputs["poly"]

    # 1. Lift polygon pixels → real-world (X, Z) mm (or use the edited mm
    #    coords directly if align_outline.py was run).
    if "vertices_xz_mm" in poly:
        outline_mm = [(float(x), float(z)) for x, z in poly["vertices_xz_mm"]]
    else:
        to_mm = px_to_mm(rect)
        outline_mm = [to_mm(x, y) for x, y in poly["vertices_px"]]
    xs = [p[0] for p in outline_mm]; zs = [p[1] for p in outline_mm]
    bbox_w = max(xs) - min(xs); bbox_h = max(zs) - min(zs)
    print(f"outline   : {len(outline_mm)} vertices  ({bbox_w:.1f} W × {bbox_h:.1f} H mm)")

    # 2. Build the part.
    y_holes = [h for h in holes_data["holes"] if h["axis"] == "Y"]
    part, hole_records, skipped_holes = build_part(
        outline_mm, y_holes,
        thickness=args.thickness, punch_holes=not args.no_holes,
    )
    print(f"thickness : {args.thickness:.2f} mm")
    print(f"holes     : {len(hole_records)} ({'skipped' if args.no_holes else 'punched'})")

    # 3. Export STEP + STL.
    stage5 = example / "5_models_and_renders"
    stage5.mkdir(exist_ok=True)
    # Name derives from the polygon JSON (drop trailing _polygon[_edited]).
    name = inputs["poly_json"].stem
    name = name.removesuffix("_edited").removesuffix("_polygon")
    step_out = stage5 / f"{name}_metal.step"
    stl_out = stage5 / f"{name}_metal.stl"
    export_step(part.part, str(step_out))
    export_stl(part.part, str(stl_out))
    bb = part.part.bounding_box()
    print(
        f"bbox      : X[{bb.min.X:6.1f} .. {bb.max.X:6.1f}]  "
        f"Y[{bb.min.Y:6.1f} .. {bb.max.Y:6.1f}]  "
        f"Z[{bb.min.Z:6.1f} .. {bb.max.Z:6.1f}] mm"
    )
    print(f"volume    : {part.part.volume:.0f} mm³  "
          f"(~{part.part.volume * 2.7e-3:.0f} g in aluminium)")
    print(f"wrote     : {step_out}")
    print(f"wrote     : {stl_out}")

    # 4. Plan-view render + plastic overlay (procedure step 8).
    plan_png = stage5 / f"{name}_metal_plan.png"
    render_plan(outline_mm, hole_records, plan_png, title=name)
    print(f"wrote     : {plan_png}")
    stl_path = Path(rect["stl"])
    if stl_path.exists():
        overlay_png = stage5 / f"{name}_metal_vs_plastic.png"
        render_overlay(
            outline_mm, hole_records, stl_path, skipped_holes, overlay_png,
            title=name,
        )
        print(f"wrote     : {overlay_png}")
    else:
        print(f"skip overlay: STL not found at {stl_path}")

    # 5. Hole-diff vs the plastic STL (skipped if --no-holes).
    if not args.no_holes:
        diff = compute_hole_diff(hole_records, y_holes)
        diff_path = stage5 / f"{name}_metal_hole_diff.json"
        diff_path.write_text(json.dumps(diff, indent=2))
        warn_if_holes_differ(diff)

    # 6. Optional 3D viewer.
    if args.view:
        viewer = shutil.which("f3d") or shutil.which("FreeCAD")
        if not viewer:
            print("\n--view requested, but neither f3d nor FreeCAD found on PATH.")
            print("Try: nix-shell -p f3d --run 'f3d {step_out}'")
        else:
            print(f"\nlaunching {viewer} {step_out}")
            subprocess.Popen([viewer, str(step_out)])


if __name__ == "__main__":
    main()
