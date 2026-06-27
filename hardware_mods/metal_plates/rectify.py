"""rectify.py — stage 2 of the metal-plate workflow.

Flattens a perspective-distorted photo of the metal plate by computing a
homography from 4 hole positions known via the corresponding *plastic*
STL. The script picks the 4 widest-spaced Y-axis holes automatically, then
shows the user a labelled reference render of the plastic plate side-by-side
with the photo, so the user can click the same 4 holes in order on the photo.

Reads:
  <example>/0_raw_screenshots/  (1 PNG, or --photo to override)
  <stl path>                    (--stl: the plastic prototype STL)

Writes (all into <example>/2_flattened_image/):
  plate_reference.png           — annotated plastic-plate render (1..4 marked)
  holes_from_stl.json           — cached extract_holes.py output
  <photo>_rect.png              — perspective-corrected photo
  <photo>_rect.json             — homography + chosen hole IDs + raw clicks

Refuses to start (with a clear, actionable message) if any required
upstream-stage file is missing — this enforces the README ## Procedure.

Usage:

  nix-shell hardware_mods/metal_plates/shell.nix --run \\
    "python hardware_mods/metal_plates/rectify.py \\
       --example hardware_mods/metal_plates/examples/.../P20_left_side_plate_p1of3 \\
       --stl docs/stl_files/side_plates/left/LEFT_PLATE.stl"

  Pass --exclude N,N,... to skip Y-axis hole indices (use this if the
  script's chosen holes don't exist on the metal plate you're rectifying).
  Indices match the "all Y-holes" numbering printed when the script starts.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import cv2
import matplotlib

# Force an interactive backend. PyQt6 (in the venv) brings its own Qt, so
# QtAgg is the most reliable choice on NixOS. Fall back to WebAgg (browser)
# if QtAgg can't load — set MPLBACKEND=webagg to opt in explicitly.
if not os.environ.get("MPLBACKEND"):
    for backend in ("QtAgg", "TkAgg", "WebAgg"):
        try:
            matplotlib.use(backend, force=True)
            break
        except Exception:
            continue

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.collections import PolyCollection  # noqa: E402
from stl import mesh  # noqa: E402

from extract_holes import extract_holes  # noqa: E402


STAGE_DIRS = [
    "0_raw_screenshots",
    "1_original_plastic_images",
    "2_flattened_image",
    "3_measurements",
    "4_outline",
    "5_models_and_renders",
]


# =============================================================================
# Stage-folder enforcement
# =============================================================================
def ensure_stage_layout(example: Path) -> None:
    """Create the 6 numbered stage folders inside example if missing."""
    if not example.exists():
        raise SystemExit(f"--example folder does not exist: {example}")
    if not example.is_dir():
        raise SystemExit(f"--example is not a directory: {example}")
    for s in STAGE_DIRS:
        (example / s).mkdir(exist_ok=True)


def require_raw_screenshot(example: Path, photo_override: Path | None) -> Path:
    """Return the raw screenshot to rectify, refusing if ambiguous."""
    if photo_override is not None:
        if not photo_override.exists():
            raise SystemExit(f"--photo not found: {photo_override}")
        return photo_override
    raw_dir = example / "0_raw_screenshots"
    candidates = sorted(
        p for p in raw_dir.iterdir()
        if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg"}
    )
    if not candidates:
        raise SystemExit(
            f"no images in {raw_dir} — drop the raw video screenshot there "
            f"(stage 0) before running rectify."
        )
    if len(candidates) > 1:
        listing = "\n  ".join(p.name for p in candidates)
        raise SystemExit(
            f"{len(candidates)} images in {raw_dir}; pass --photo to disambiguate:\n  "
            + listing
        )
    return candidates[0]


# =============================================================================
# Hole picking: widest mutual spread among small Y-axis holes
# =============================================================================
def pick_calibration_holes(
    y_holes: list[dict],
    *,
    n: int = 4,
    max_radius: float = 6.0,
    exclude: set[int] = frozenset(),
) -> list[int]:
    """Pick n Y-axis holes with maximum mutual spread (greedy max-min)."""
    candidates = [
        i for i, h in enumerate(y_holes)
        if h["r"] <= max_radius and i not in exclude
    ]
    if len(candidates) < n:
        # Relax the radius filter, keep the exclude filter.
        candidates = [i for i in range(len(y_holes)) if i not in exclude]
    if len(candidates) < n:
        raise SystemExit(
            f"only {len(candidates)} Y-axis hole(s) remain after --exclude; "
            f"need {n}. Re-run without (or with fewer) --exclude indices."
        )

    pts = np.array(
        [(y_holes[i]["cx"], y_holes[i]["cz"]) for i in candidates]
    )
    # Pairwise distances
    diff = pts[:, None, :] - pts[None, :, :]
    D = np.linalg.norm(diff, axis=-1)

    # Start with the pair furthest apart
    i0, i1 = np.unravel_index(np.argmax(D), D.shape)
    selected = [int(i0), int(i1)]
    while len(selected) < n:
        min_to_selected = D[selected].min(axis=0)
        # Forbid re-picking
        for k in selected:
            min_to_selected[k] = -np.inf
        nxt = int(np.argmax(min_to_selected))
        selected.append(nxt)

    return [candidates[i] for i in selected]


# =============================================================================
# Reference image: plate face silhouette + numbered chosen-hole markers
# =============================================================================
def render_calibration_reference(
    stl_path: Path,
    y_holes: list[dict],
    chosen: list[int],
    out_path: Path,
) -> None:
    """Render the plate face with the 4 chosen holes marked 1..4."""
    m = mesh.Mesh.from_file(str(stl_path))
    tris = m.vectors
    norms = m.normals.copy()
    nlen = np.linalg.norm(norms, axis=1, keepdims=True)
    n_unit = np.where(nlen > 1e-12, norms / nlen, 0.0)
    y_face_mask = np.abs(n_unit[:, 1]) > 0.95

    fig, ax = plt.subplots(figsize=(8, 10))
    if y_face_mask.any():
        proj = tris[y_face_mask][:, :, [0, 2]]
        pc = PolyCollection(
            proj, facecolor="lightgray", edgecolor="gray", lw=0.15, alpha=0.65,
        )
        ax.add_collection(pc)
    else:
        # Fall back to all-triangle projection if no clear Y-face.
        proj = tris[:, :, [0, 2]]
        pc = PolyCollection(
            proj, facecolor="lightgray", edgecolor="gray", lw=0.05, alpha=0.20,
        )
        ax.add_collection(pc)

    # All Y-axis holes as thin circles (so the user sees the layout)
    for i, h in enumerate(y_holes):
        ax.add_patch(
            plt.Circle(
                (h["cx"], h["cz"]), h["r"],
                fill=False, color="black", lw=0.7, alpha=0.7,
            )
        )

    # Chosen holes: numbered, in click order
    for k, idx in enumerate(chosen, start=1):
        h = y_holes[idx]
        ring = plt.Circle(
            (h["cx"], h["cz"]), max(h["r"] * 1.6, 3.0),
            fill=False, color="red", lw=2.5,
        )
        ax.add_patch(ring)
        ax.annotate(
            str(k), (h["cx"], h["cz"]),
            color="white", fontsize=18, fontweight="bold",
            ha="center", va="center",
            bbox=dict(boxstyle="circle,pad=0.35", fc="red", ec="white", lw=1.5),
        )

    ax.set_aspect("equal")
    ax.set_xlabel("X (mm)")
    ax.set_ylabel("Z (mm)")
    ax.set_title(
        "Plastic plate reference\nclick holes 1→2→3→4 on the photo (right)"
    )
    ax.autoscale_view()
    ax.grid(alpha=0.3, lw=0.5)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


# =============================================================================
# Side-by-side calibration: reference (left) + photo (right). Collect 4 clicks.
# =============================================================================
def collect_calibration_clicks(
    reference_png: Path,
    photo: np.ndarray,
    n: int = 4,
) -> np.ndarray:
    ref_img = plt.imread(str(reference_png))
    photo_rgb = cv2.cvtColor(photo, cv2.COLOR_BGR2RGB)

    fig, (ax_ref, ax_photo) = plt.subplots(1, 2, figsize=(16, 9))
    try:
        fig.canvas.manager.set_window_title(
            "Calibrate — click the 4 red-numbered holes on the photo (right)"
        )
    except Exception:
        pass

    ax_ref.imshow(ref_img)
    ax_ref.set_axis_off()
    ax_ref.set_title("Reference (plastic plate)")

    ax_photo.imshow(photo_rgb, interpolation="bilinear")
    ax_photo.set_axis_off()
    ax_photo.set_title(
        f"Click hole 1/{n} on the photo  (u=undo, q=quit)"
    )

    fig.patch.set_facecolor("black")
    fig.subplots_adjust(left=0.01, right=0.99, top=0.95, bottom=0.01, wspace=0.02)

    mgr = fig.canvas.manager
    for fn in (
        lambda: mgr.window.showMaximized(),
        lambda: mgr.window.state("zoomed"),
        lambda: mgr.full_screen_toggle(),
    ):
        try:
            fn()
            break
        except Exception:
            continue

    picked: list[tuple[float, float]] = []
    artists: list = []

    def update_title():
        if len(picked) < n:
            ax_photo.set_title(
                f"Click hole {len(picked) + 1}/{n} on the photo  (u=undo, q=quit)"
            )
        else:
            ax_photo.set_title(
                f"All {n} points clicked — press q to continue"
            )

    def redraw():
        for a in artists:
            a.remove()
        artists.clear()
        for i, (x, y) in enumerate(picked):
            (dot,) = ax_photo.plot([x], [y], "o", color="red", markersize=10,
                                    mec="white", mew=1.2)
            txt = ax_photo.annotate(
                str(i + 1), (x, y),
                color="white", fontsize=12, fontweight="bold",
                ha="center", va="center",
                bbox=dict(boxstyle="circle,pad=0.25", fc="red", ec="white", lw=1),
            )
            artists.extend([dot, txt])
        update_title()
        fig.canvas.draw_idle()

    def on_click(e):
        if e.inaxes is not ax_photo or e.button != 1:
            return
        if len(picked) >= n:
            return
        picked.append((e.xdata, e.ydata))
        redraw()

    def on_key(e):
        if e.key == "u" and picked:
            picked.pop()
            redraw()
        elif e.key == "q":
            plt.close(fig)

    fig.canvas.mpl_connect("button_press_event", on_click)
    fig.canvas.mpl_connect("key_press_event", on_key)
    plt.show()

    if len(picked) != n:
        raise SystemExit(
            f"got {len(picked)} clicks on the photo, needed {n}. "
            "Re-run rectify.py and click all four holes."
        )
    return np.asarray(picked, dtype=np.float64)


# =============================================================================
# Measure loop (unchanged from the previous rectify.py)
# =============================================================================
def measure_loop(img_rect: np.ndarray, mm_per_px: float) -> None:
    fig, ax = plt.subplots()
    try:
        fig.canvas.manager.set_window_title("Measure")
    except Exception:
        pass
    ax.imshow(cv2.cvtColor(img_rect, cv2.COLOR_BGR2RGB), interpolation="bilinear")
    ax.set_axis_off()
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
    fig.patch.set_facecolor("black")
    mgr = fig.canvas.manager
    for fn in (
        lambda: mgr.window.showMaximized(),
        lambda: mgr.window.state("zoomed"),
        lambda: mgr.full_screen_toggle(),
    ):
        try:
            fn()
            break
        except Exception:
            continue
    overlay_text = ax.text(
        0.5, 0.99,
        "Left-click two points to measure  (right-click=reset, q=quit)",
        transform=ax.transAxes, ha="center", va="top",
        color="white", fontsize=11,
        bbox=dict(boxstyle="round,pad=0.4", fc="black", ec="white", alpha=0.7),
    )

    state = {"pts": []}

    def render():
        for a in list(ax.lines):
            a.remove()
        for t in list(ax.texts):
            if t is not overlay_text:
                t.remove()
        for x, y in state["pts"]:
            ax.plot([x], [y], "o", color="lime", markersize=8)
        if len(state["pts"]) == 2:
            (x1, y1), (x2, y2) = state["pts"]
            ax.plot([x1, x2], [y1, y2], "-", color="lime", lw=2)
            d_px = np.hypot(x2 - x1, y2 - y1)
            d_mm = d_px * mm_per_px
            mid = ((x1 + x2) / 2, (y1 + y2) / 2)
            ax.annotate(
                f"{d_mm:.2f} mm",
                mid, color="black",
                bbox=dict(boxstyle="round", fc="lime", ec="black"),
                fontsize=11, weight="bold",
            )
            print(f"  distance: {d_mm:.3f} mm  ({d_px:.1f} px)")
        fig.canvas.draw_idle()

    def on_click(e):
        if e.inaxes is not ax:
            return
        if e.button == 3:
            state["pts"].clear()
        elif e.button == 1:
            if len(state["pts"]) == 2:
                state["pts"] = []
            state["pts"].append((e.xdata, e.ydata))
        render()

    def on_key(e):
        if e.key == "q":
            plt.close(fig)

    fig.canvas.mpl_connect("button_press_event", on_click)
    fig.canvas.mpl_connect("key_press_event", on_key)
    plt.show()


# =============================================================================
# Main
# =============================================================================
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--example", type=Path, required=True,
                    help="example folder (the one containing the 0_..5_ stage dirs)")
    ap.add_argument("--stl", type=Path, required=True,
                    help="path to the plastic prototype STL (calibration source)")
    ap.add_argument("--photo", type=Path, default=None,
                    help="raw photo to rectify (default: the single image in "
                         "<example>/0_raw_screenshots/)")
    ap.add_argument("--exclude", type=str, default="",
                    help="comma-separated Y-hole indices to skip when picking "
                         "the 4 calibration holes (use if the script's pick "
                         "includes holes that don't exist on the metal plate)")
    ap.add_argument("--scale", type=float, default=4.0,
                    help="output pixels per mm (default 4 → 0.25 mm/px)")
    ap.add_argument("--pad", type=float, default=10.0,
                    help="mm of padding around the rectified image")
    ap.add_argument("--max-px", type=int, default=40_000_000,
                    help="hard cap on canvas pixel count (default 40 Mpx)")
    args = ap.parse_args()

    example: Path = args.example.resolve()
    stl_path: Path = args.stl.resolve()
    if not stl_path.exists():
        raise SystemExit(f"--stl not found: {stl_path}")

    ensure_stage_layout(example)
    photo_path = require_raw_screenshot(example, args.photo)
    print(f"example       : {example}")
    print(f"photo         : {photo_path.relative_to(example) if photo_path.is_relative_to(example) else photo_path}")
    print(f"stl           : {stl_path}")

    stage2 = example / "2_flattened_image"

    # 1. Extract holes from the plastic STL (cache the JSON in stage 2).
    holes_cache = stage2 / "holes_from_stl.json"
    print(f"\nExtracting holes from STL → {holes_cache.name}")
    plate = extract_holes(stl_path, verbose=False)
    holes_cache.write_text(json.dumps(plate, indent=2))
    y_holes = [h for h in plate["holes"] if h["axis"] == "Y"]
    if len(y_holes) < 4:
        raise SystemExit(
            f"plastic STL only has {len(y_holes)} Y-axis hole(s); need ≥ 4 "
            "for calibration."
        )

    # 2. Pick 4 widest-spread Y-axis holes (honouring --exclude).
    exclude = set()
    if args.exclude:
        try:
            exclude = {int(x.strip()) for x in args.exclude.split(",") if x.strip()}
        except ValueError:
            raise SystemExit("--exclude expects comma-separated integers")
    chosen = pick_calibration_holes(y_holes, n=4, exclude=exclude)

    print(f"\nAll Y-axis holes ({len(y_holes)}):")
    for i, h in enumerate(y_holes):
        mark = " ← chosen" if i in chosen else ""
        print(f"  [{i:2d}]  X={h['cx']:7.2f}  Z={h['cz']:7.2f}  r={h['r']:5.2f}{mark}")
    print(f"\nChosen calibration holes (in click order): {chosen}")
    for k, idx in enumerate(chosen, start=1):
        h = y_holes[idx]
        print(f"  hole {k} → Y-hole #{idx}: (X={h['cx']:.2f}, Z={h['cz']:.2f}, d={2*h['r']:.2f})")

    # 3. Render the reference image.
    ref_png = stage2 / "plate_reference.png"
    render_calibration_reference(stl_path, y_holes, chosen, ref_png)
    print(f"\nWrote {ref_png}")

    # 4. Load the photo and collect 4 clicks side-by-side with the reference.
    img = cv2.imread(str(photo_path))
    if img is None:
        raise SystemExit(f"could not load {photo_path}")
    img_pts = collect_calibration_clicks(ref_png, img, n=4)

    # 5. Build homography from the 4 (X, Z) real-world coords of the chosen
    #    holes onto the photo clicks.
    real_pts = np.array(
        [(y_holes[idx]["cx"], y_holes[idx]["cz"]) for idx in chosen],
        dtype=np.float64,
    )
    ideal_dst = np.column_stack([
         real_pts[:, 0] * args.scale,
        -real_pts[:, 1] * args.scale,
    ]).astype(np.float64)
    H_ideal, _ = cv2.findHomography(img_pts, ideal_dst, method=0)
    if H_ideal is None:
        raise SystemExit("homography failed — chosen holes may be collinear")

    # 6. Size the rectified canvas to enclose the warped source image.
    src_h_img, src_w_img = img.shape[:2]
    src_corners = np.array(
        [[0, 0], [src_w_img, 0], [src_w_img, src_h_img], [0, src_h_img]],
        dtype=np.float64,
    ).reshape(-1, 1, 2)
    warped = cv2.perspectiveTransform(src_corners, H_ideal).reshape(-1, 2)
    x0, y0 = warped.min(axis=0)
    x1, y1 = warped.max(axis=0)
    pad_px = args.pad * args.scale
    W = int(round((x1 - x0) + 2 * pad_px))
    H = int(round((y1 - y0) + 2 * pad_px))
    if W * H > args.max_px:
        raise SystemExit(
            f"output canvas would be {W}x{H} px ({W*H/1e6:.1f} Mpx); bigger than "
            f"--max-px ({args.max_px/1e6:.1f} Mpx). Tighten --pad or raise --max-px."
        )

    T = np.array(
        [[1.0, 0.0, -x0 + pad_px],
         [0.0, 1.0, -y0 + pad_px],
         [0.0, 0.0, 1.0]]
    )
    H_mat = T @ H_ideal
    rectified = cv2.warpPerspective(img, H_mat, (W, H))

    x_min = (x0 - pad_px) / args.scale
    x_max = (x1 + pad_px) / args.scale
    z_max = -(y0 - pad_px) / args.scale
    z_min = -(y1 + pad_px) / args.scale

    # 7. Write outputs into stage 2.
    out_png = stage2 / (photo_path.stem + "_rect.png")
    cv2.imwrite(str(out_png), rectified)
    meta = dict(
        source_photo=str(photo_path),
        stl=str(stl_path),
        chosen_y_hole_indices=chosen,
        chosen_y_hole_coords_mm=real_pts.tolist(),
        image_points_px=img_pts.tolist(),
        homography=H_mat.tolist(),
        scale_px_per_mm=args.scale,
        canvas_real_bounds_mm=dict(
            x_min=x_min, x_max=x_max, z_min=z_min, z_max=z_max,
        ),
        output_size_px=[W, H],
    )
    meta_path = out_png.with_suffix(".json")
    meta_path.write_text(json.dumps(meta, indent=2))
    print(f"\nWrote {out_png}  ({W}x{H} px, {args.scale} px/mm)")
    print(f"Wrote {meta_path}")

    # 8. Hand off to the measure loop.
    mm_per_px = 1.0 / args.scale
    print("\nMeasure mode — close the window or press q to exit.")
    measure_loop(rectified, mm_per_px)


if __name__ == "__main__":
    main()
