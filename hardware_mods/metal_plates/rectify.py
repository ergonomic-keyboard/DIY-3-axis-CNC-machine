"""rectify.py — stage 2 of the metal-plate workflow.

Flattens a perspective-distorted photo of the metal plate by computing a
homography from 4 hole positions known via the corresponding *plastic*
STL. The script picks the 4 widest-spaced Y-axis holes automatically, then
shows the user a labelled reference render of the plastic plate side-by-side
with the photo, so the user can click the same 4 holes in order on the photo.

Reads:
  <example>/0_raw_screenshots/  (1 PNG, or --photo to override)
  <stl path>                    (--stl: the plastic prototype STL)

Writes (into <example>/2_flattened_image/):
  plate_reference.png           — annotated plastic-plate render (1..4 marked)
  holes_from_stl.json           — cached extract_holes.py output
  <photo>_rect.png              — perspective-corrected photo
  <photo>_rect.json             — homography + chosen hole IDs + raw clicks

Optional, if the user runs the sanity-check measure loop and presses S:
  <example>/3_measurements/<photo>_manual_measurements.json
  <example>/3_measurements/<photo>_manual_measurements.png

The manual measurements are not required — every dimension of the plate
is recoverable from the rectified PNG plus the polygon trace produced
by trace_polygon.py (stage 5). The measure loop just lets you spot-check
a few distances by hand if you want to verify the rectification.

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

# Disable matplotlib's default keymap (save, home, grid, …) so our explicit
# key bindings don't double-trigger matplotlib's native actions — e.g. `s`
# popping up a save-figure dialog in a random folder while we silently save
# to the stage folder.
for _k in list(matplotlib.rcParams):
    if _k.startswith("keymap.") and _k != "keymap.quit":
        matplotlib.rcParams[_k] = []

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.collections import PolyCollection  # noqa: E402
from stl import mesh  # noqa: E402

from extract_holes import extract_holes  # noqa: E402
import trace_polygon  # noqa: E402


STAGE_DIRS = [
    "0_raw_screenshots",
    "1_original_plastic_images",
    "2_flattened_image",
    "3_measurements",
    "4_outline",
    "5_models_and_renders",
]


# =============================================================================
# STL face-axis normalisation
# =============================================================================
# The downstream pipeline assumes the plate's face is perpendicular to Y
# (so the calibration / mounting holes are "Y-axis" holes). Some parts
# (e.g. Z motor mounts) sit in the STL with the face perpendicular to X or
# Z instead. To keep the pipeline axis-agnostic we just pre-rotate the STL
# once so the original face-axis becomes Y, write the rotated STL to
# stage 2, and run extract_holes on that. Everything downstream then sees
# the standard "Y is the face axis" world.
def _permute_triangles(tris: np.ndarray, face_axis: str) -> np.ndarray:
    """Permute (X, Y, Z) per-vertex so ``face_axis`` becomes new Y.

    Returns a copy with the same shape (N, 3, 3). The non-face axes are
    preserved in their plate-frame roles: the screenshot's horizontal
    becomes new X, the screenshot's vertical becomes new Z.
    """
    if face_axis == "Y":
        return tris.copy()
    out = np.empty_like(tris)
    if face_axis == "Z":
        # screenshot horizontal X, vertical was old Y.
        out[..., 0] = tris[..., 0]
        out[..., 1] = tris[..., 2]
        out[..., 2] = tris[..., 1]
    elif face_axis == "X":
        # screenshot horizontal was old Y, vertical was old Z.
        out[..., 0] = tris[..., 1]
        out[..., 1] = tris[..., 0]
        out[..., 2] = tris[..., 2]
    else:
        raise ValueError(f"face_axis must be X/Y/Z; got {face_axis}")
    return out


def write_rotated_stl(src: Path, face_axis: str, dst: Path) -> Path:
    """Write a copy of ``src`` with the face axis moved to Y. Returns ``dst``.

    No-op (just returns src) when face_axis is already Y.
    """
    if face_axis == "Y":
        return src
    m = mesh.Mesh.from_file(str(src))
    new_tris = _permute_triangles(m.vectors, face_axis)
    out = mesh.Mesh(np.zeros(len(new_tris), dtype=mesh.Mesh.dtype))
    out.vectors[:] = new_tris
    # Permutation can flip winding/normals; recompute and let the writer set
    # them, otherwise OCCT-based loaders may produce inverted faces.
    out.update_normals()
    out.save(str(dst))
    return dst


def detect_face_axis(plate: dict) -> str:
    """Auto-pick the face axis: the one with the most small-radius holes.

    Falls back to the axis with the most holes overall on a tie.
    """
    small = [h for h in plate["holes"] if h["r"] <= 6.0]
    pool = small if small else plate["holes"]
    counts = {"X": 0, "Y": 0, "Z": 0}
    for h in pool:
        counts[h["axis"]] = counts.get(h["axis"], 0) + 1
    return max(counts, key=lambda k: counts[k])


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
def _y_face_projection(stl_path: Path) -> tuple[np.ndarray, bool]:
    """Return XZ-projected triangles for the Y-perpendicular faces of the STL."""
    m = mesh.Mesh.from_file(str(stl_path))
    tris = m.vectors
    norms = m.normals.copy()
    nlen = np.linalg.norm(norms, axis=1, keepdims=True)
    n_unit = np.where(nlen > 1e-12, norms / nlen, 0.0)
    y_face_mask = np.abs(n_unit[:, 1]) > 0.95
    if y_face_mask.any():
        return tris[y_face_mask][:, :, [0, 2]], True
    return tris[:, :, [0, 2]], False


def _draw_plate(
    ax,
    proj: np.ndarray,
    proj_is_y_face: bool,
    y_holes: list[dict],
    chosen: list[int],
    *,
    title: str = "Plastic plate reference\nclick holes 1→2→3→4 on the photo (right)",
) -> None:
    """Draw silhouette + every Y-hole + the numbered chosen holes onto ax."""
    if proj_is_y_face:
        pc = PolyCollection(
            proj, facecolor="lightgray", edgecolor="gray", lw=0.15, alpha=0.65,
        )
    else:
        pc = PolyCollection(
            proj, facecolor="lightgray", edgecolor="gray", lw=0.05, alpha=0.20,
        )
    ax.add_collection(pc)

    # All Y-axis holes as thin circles, with a tiny index label so the user
    # can match clicks to console output if they want.
    for i, h in enumerate(y_holes):
        ax.add_patch(
            plt.Circle(
                (h["cx"], h["cz"]), h["r"],
                fill=False, color="black", lw=0.7, alpha=0.7,
            )
        )
        ax.annotate(
            str(i), (h["cx"], h["cz"]),
            xytext=(h["r"] + 1, h["r"] + 1), textcoords="offset points",
            color="dimgray", fontsize=6,
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
    ax.set_title(title)
    ax.autoscale_view()
    ax.grid(alpha=0.3, lw=0.5)


def render_calibration_reference(
    stl_path: Path,
    y_holes: list[dict],
    chosen: list[int],
    out_path: Path,
) -> None:
    """Render the plate face with the 4 chosen holes marked 1..4 to a PNG."""
    proj, is_y_face = _y_face_projection(stl_path)
    fig, ax = plt.subplots(figsize=(8, 10))
    _draw_plate(ax, proj, is_y_face, y_holes, chosen)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def interactive_hole_selection(
    stl_path: Path,
    y_holes: list[dict],
    initial_chosen: list[int],
) -> list[int]:
    """Open a TUI letting the user toggle which 4 holes are chosen.

    Click on any hole to toggle membership in ``chosen``. Click order
    determines numbering (1..4). Press ``q`` to accept and continue.
    Returns the final list of 4 indices.
    """
    proj, is_y_face = _y_face_projection(stl_path)
    # Plate-frame tolerance for a click counting as a hole hit.
    xs = np.concatenate([proj[:, :, 0].ravel()]) if proj.size else np.array([0.0])
    zs = np.concatenate([proj[:, :, 1].ravel()]) if proj.size else np.array([0.0])
    plate_diag = float(np.hypot(xs.max() - xs.min(), zs.max() - zs.min()))
    tol = max(0.05 * plate_diag, 5.0)

    chosen: list[int] = list(initial_chosen)

    fig, ax = plt.subplots(figsize=(9, 11))
    try:
        fig.canvas.manager.set_window_title(
            "Pick calibration holes — click to toggle (need 4)"
        )
    except Exception:
        pass

    banner = ax.text(
        0.5, 1.02,
        "click a hole to toggle  |  red = chosen, in click order  |  press D when done",
        transform=ax.transAxes, ha="center", va="bottom",
        color="white", fontsize=11,
        bbox=dict(boxstyle="round,pad=0.4", fc="black", ec="white", alpha=0.85),
        zorder=100,
    )
    status = ax.text(
        0.99, 1.02, "",
        transform=ax.transAxes, ha="right", va="bottom",
        color="white", fontsize=11,
        bbox=dict(boxstyle="round,pad=0.3", fc="black", ec="white", alpha=0.85),
        zorder=100,
    )

    def repaint():
        ax.clear()
        _draw_plate(
            ax, proj, is_y_face, y_holes, chosen,
            title="",
        )
        # Re-add the banner/status (cleared by ax.clear above)
        ax.add_artist(banner)
        ax.add_artist(status)
        status.set_text(f"selected: {len(chosen)}/4")
        fig.canvas.draw_idle()

    def on_click(e):
        if e.inaxes is not ax or e.button != 1 or e.xdata is None:
            return
        # Snap to nearest Y-hole within tolerance.
        dists = np.array(
            [np.hypot(h["cx"] - e.xdata, h["cz"] - e.ydata) for h in y_holes]
        )
        nearest = int(np.argmin(dists))
        if dists[nearest] > tol:
            return
        if nearest in chosen:
            chosen.remove(nearest)
        else:
            if len(chosen) < 4:
                chosen.append(nearest)
            else:
                # Already 4; replace the last to keep the count fixed.
                chosen[-1] = nearest
        repaint()

    def on_key(e):
        if e.key not in ("d", "D"):
            return
        if len(chosen) != 4:
            print(f"need 4 holes selected, have {len(chosen)} — keep clicking")
            return
        plt.close(fig)

    fig.canvas.mpl_connect("button_press_event", on_click)
    fig.canvas.mpl_connect("key_press_event", on_key)

    repaint()
    # Maximise — same trick as the photo-click window.
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
    plt.show()

    if len(chosen) != 4:
        raise SystemExit(
            f"calibration aborted with {len(chosen)} hole(s) selected (need 4)"
        )
    return chosen


# =============================================================================
# Side-by-side calibration: reference (left) + photo (right). Collect 4 clicks.
# =============================================================================
def collect_calibration_clicks(
    reference_png: Path,
    photo: np.ndarray,
    n: int = 4,
    initial_clicks: list[tuple[float, float]] | None = None,
) -> np.ndarray:
    ref_img = plt.imread(str(reference_png))
    photo_rgb = cv2.cvtColor(photo, cv2.COLOR_BGR2RGB)

    # Kill any leftover figures so plt.show() below opens only the new window.
    # Without this, Qt/Wayland can re-display the previous (hole-picker)
    # window alongside this one.
    plt.close("all")
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
        f"Click hole 1/{n} on the photo  (u=undo, D=done)"
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

    picked: list[tuple[float, float]] = list(initial_clicks or [])
    artists: list = []

    def update_title():
        if len(picked) < n:
            ax_photo.set_title(
                f"Click hole {len(picked) + 1}/{n} on the photo  (u=undo, D=done)"
            )
        else:
            ax_photo.set_title(
                f"All {n} points clicked — press D to continue"
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
        elif e.key in ("d", "D"):
            if len(picked) != n:
                print(f"need {n} clicks, have {len(picked)} — keep clicking")
                return
            plt.close(fig)

    fig.canvas.mpl_connect("button_press_event", on_click)
    fig.canvas.mpl_connect("key_press_event", on_key)
    # Render any pre-populated clicks before showing the window so the user
    # sees the loaded points and can keep, edit, or replace them.
    if picked:
        redraw()
    plt.show()

    if len(picked) != n:
        raise SystemExit(
            f"got {len(picked)} clicks on the photo, needed {n}. "
            "Re-run rectify.py and click all four holes."
        )
    return np.asarray(picked, dtype=np.float64)


# =============================================================================
# Measure loop — OPTIONAL sanity-check step.
#
# Every dimension you need is already implicit in the rectified PNG plus the
# polygon trace (stage 5): pixel→mm scale lives in the rect.json, so edges
# and angles are computable. This loop just lets you spot-check a few
# distances by hand if you don't trust the rectification yet.
# =============================================================================
def measure_loop(
    img_rect: np.ndarray,
    mm_per_px: float,
    *,
    example: Path,
    photo_stem: str,
) -> None:
    out_dir = example / "3_measurements"
    out_dir.mkdir(exist_ok=True)
    out_json = out_dir / f"{photo_stem}_manual_measurements.json"
    out_png = out_dir / f"{photo_stem}_manual_measurements.png"

    fig, ax = plt.subplots()
    try:
        fig.canvas.manager.set_window_title(
            "Manual measurements (optional sanity check)"
        )
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

    banner_text = (
        "OPTIONAL sanity check — all dimensions are derivable from the polygon trace.\n"
        "left-click two points = measure  |  right-click = undo  |  S = save  |  D = done"
    )
    overlay_text = ax.text(
        0.5, 0.99, banner_text,
        transform=ax.transAxes, ha="center", va="top",
        color="white", fontsize=11,
        bbox=dict(boxstyle="round,pad=0.4", fc="black", ec="white", alpha=0.75),
        zorder=100,
    )
    status_text = ax.text(
        0.01, 0.99, "pairs: 0",
        transform=ax.transAxes, ha="left", va="top",
        color="white", fontsize=10,
        bbox=dict(boxstyle="round,pad=0.3", fc="black", ec="white", alpha=0.7),
        zorder=100,
    )

    # Each entry: ((x1, y1), (x2, y2), d_px, d_mm)
    pairs: list[tuple[tuple[float, float], tuple[float, float], float, float]] = []
    pending: list[tuple[float, float]] = []  # 0 or 1 click between completed pairs

    def render():
        for a in list(ax.lines):
            a.remove()
        for t in list(ax.texts):
            if t is not overlay_text and t is not status_text:
                t.remove()
        # Pending single click
        for x, y in pending:
            ax.plot([x], [y], "o", color="yellow", markersize=8, mec="black", mew=0.8)
        # Completed pairs
        for i, ((x1, y1), (x2, y2), _d_px, d_mm) in enumerate(pairs, start=1):
            ax.plot([x1, x2], [y1, y2], "-", color="lime", lw=2)
            ax.plot([x1, x2], [y1, y2], "o", color="lime", markersize=8,
                    mec="black", mew=0.8)
            mid = ((x1 + x2) / 2, (y1 + y2) / 2)
            ax.annotate(
                f"M{i}: {d_mm:.2f} mm", mid, color="black",
                bbox=dict(boxstyle="round", fc="lime", ec="black"),
                fontsize=10, weight="bold",
            )
        status_text.set_text(f"pairs: {len(pairs)}")
        fig.canvas.draw_idle()

    def save():
        if not pairs:
            print("no measurements to save")
            return
        payload = {
            "source_rectified_png": f"{photo_stem}_rect.png",
            "mm_per_px": mm_per_px,
            "measurements": [
                {
                    "id": i,
                    "p1_px": [p1[0], p1[1]],
                    "p2_px": [p2[0], p2[1]],
                    "distance_px": d_px,
                    "distance_mm": d_mm,
                }
                for i, (p1, p2, d_px, d_mm) in enumerate(pairs, start=1)
            ],
        }
        out_json.write_text(json.dumps(payload, indent=2))
        fig.savefig(out_png, dpi=150, bbox_inches="tight")
        print(f"saved {len(pairs)} measurement(s)")
        print(f"  {out_json}")
        print(f"  {out_png}")

    def on_click(e):
        if e.inaxes is not ax:
            return
        if e.button == 3:
            # Undo: prefer cancelling a pending single click; otherwise drop
            # the last completed pair.
            if pending:
                pending.clear()
            elif pairs:
                pairs.pop()
        elif e.button == 1:
            pending.append((e.xdata, e.ydata))
            if len(pending) == 2:
                (x1, y1), (x2, y2) = pending
                d_px = float(np.hypot(x2 - x1, y2 - y1))
                d_mm = d_px * mm_per_px
                pairs.append(((x1, y1), (x2, y2), d_px, d_mm))
                pending.clear()
                print(f"  M{len(pairs)}: {d_mm:.3f} mm  ({d_px:.1f} px)")
        render()

    def on_key(e):
        if e.key in ("s", "S"):
            save()
        elif e.key in ("d", "D"):
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
    ap.add_argument("--face-axis", choices=["auto", "X", "Y", "Z"], default="auto",
                    help="which original STL axis is perpendicular to the plate "
                         "face (default: auto = the axis with the most small "
                         "holes). The STL is silently rotated so this axis "
                         "becomes Y for the rest of the pipeline.")
    ap.add_argument("--scale", type=float, default=4.0,
                    help="output pixels per mm (default 4 → 0.25 mm/px)")
    ap.add_argument("--pad", type=float, default=10.0,
                    help="mm of padding around the rectified image")
    ap.add_argument("--max-px", type=int, default=200_000_000,
                    help="hard cap on canvas pixel count (default 200 Mpx)")
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
    #    If the plate's face is perpendicular to X or Z rather than Y, rotate
    #    a copy so the rest of the pipeline can keep its "Y is face axis"
    #    assumption.
    holes_cache = stage2 / "holes_from_stl.json"
    print(f"\nExtracting holes from STL → {holes_cache.name}")
    initial_plate = extract_holes(stl_path, verbose=False)
    if args.face_axis == "auto":
        face_axis = detect_face_axis(initial_plate)
        print(f"auto-detected face axis: {face_axis} "
              f"(holes per axis: "
              f"X={sum(1 for h in initial_plate['holes'] if h['axis']=='X')}, "
              f"Y={sum(1 for h in initial_plate['holes'] if h['axis']=='Y')}, "
              f"Z={sum(1 for h in initial_plate['holes'] if h['axis']=='Z')})")
    else:
        face_axis = args.face_axis
        print(f"face axis (user): {face_axis}")

    if face_axis == "Y":
        plate = initial_plate
        effective_stl = stl_path
    else:
        effective_stl = stage2 / "stl_face_y.stl"
        write_rotated_stl(stl_path, face_axis, effective_stl)
        print(f"wrote rotated STL → {effective_stl.name} "
              f"(original face-axis {face_axis} → Y)")
        plate = extract_holes(effective_stl, verbose=False)

    plate["face_axis_original"] = face_axis
    plate["effective_stl"] = str(effective_stl)
    plate["source_stl"] = str(stl_path)
    holes_cache.write_text(json.dumps(plate, indent=2))
    y_holes = [h for h in plate["holes"] if h["axis"] == "Y"]
    if len(y_holes) < 4:
        raise SystemExit(
            f"after axis normalisation, only {len(y_holes)} Y-axis hole(s) "
            f"present; need ≥ 4 for calibration. Try a different --face-axis."
        )

    # 2. Pick 4 widest-spread Y-axis holes (honouring --exclude). If a
    #    previous rectify run for this photo saved a calibration choice, load
    #    it as the initial selection so the user only has to re-confirm
    #    (unless --exclude is passed — that forces a fresh auto-pick).
    exclude = set()
    if args.exclude:
        try:
            exclude = {int(x.strip()) for x in args.exclude.split(",") if x.strip()}
        except ValueError:
            raise SystemExit("--exclude expects comma-separated integers")

    auto_chosen = pick_calibration_holes(y_holes, n=4, exclude=exclude)

    chosen = auto_chosen
    source = "auto-picked"
    cached_clicks: list[tuple[float, float]] | None = None
    if not exclude:
        prev_meta = stage2 / f"{photo_path.stem}_rect.json"
        if prev_meta.exists():
            try:
                prev = json.loads(prev_meta.read_text())
                cached_holes = prev.get("chosen_y_hole_indices")
                if (
                    isinstance(cached_holes, list)
                    and len(cached_holes) == 4
                    and all(
                        isinstance(i, int) and 0 <= i < len(y_holes)
                        for i in cached_holes
                    )
                ):
                    chosen = list(cached_holes)
                    source = f"loaded from {prev_meta.name}"
                # Photo clicks: only reuse if hole choice was also reusable
                # (otherwise the click-order semantics no longer match).
                cached_pts = prev.get("image_points_px")
                if (
                    source.startswith("loaded")
                    and isinstance(cached_pts, list)
                    and len(cached_pts) == 4
                    and all(
                        isinstance(p, list) and len(p) == 2
                        and all(isinstance(v, (int, float)) for v in p)
                        for p in cached_pts
                    )
                ):
                    cached_clicks = [(float(x), float(y)) for x, y in cached_pts]
            except (json.JSONDecodeError, OSError) as e:
                print(f"warning: could not read {prev_meta.name} ({e}); using auto-pick")

    print(f"\nAll Y-axis holes ({len(y_holes)}):")
    for i, h in enumerate(y_holes):
        marks = []
        if i in chosen:
            marks.append("← selected")
        if i in auto_chosen and i not in chosen:
            marks.append("(auto would pick)")
        mark = "  " + "  ".join(marks) if marks else ""
        print(f"  [{i:2d}]  X={h['cx']:7.2f}  Z={h['cz']:7.2f}  r={h['r']:5.2f}{mark}")
    print(f"\nInitial selection ({source}): {chosen}")

    # 3. Let the user adjust the 4 chosen holes interactively before clicking
    #    the photo. Click any hole on the reference to toggle.
    print("Interactive hole picker — toggle any hole, press D when 4/4.")
    initial_chosen = list(chosen)
    chosen = interactive_hole_selection(effective_stl, y_holes, chosen)
    if chosen != initial_chosen and cached_clicks is not None:
        if sorted(chosen) == sorted(initial_chosen):
            # Same 4 holes, just re-ordered — re-permute cached clicks so the
            # user sees the existing click positions and can nudge them.
            old_index = {h: i for i, h in enumerate(initial_chosen)}
            cached_clicks = [cached_clicks[old_index[h]] for h in chosen]
            print("re-permuted cached photo clicks to match new hole order.")
        else:
            # Different set of holes — previous photo clicks no longer
            # correspond, discard them.
            cached_clicks = None
    print(f"\nFinal calibration holes (in click order): {chosen}")
    for k, idx in enumerate(chosen, start=1):
        h = y_holes[idx]
        print(f"  hole {k} → Y-hole #{idx}: (X={h['cx']:.2f}, Z={h['cz']:.2f}, d={2*h['r']:.2f})")

    # 4. Re-render the reference image to disk with the (possibly edited) pick.
    ref_png = stage2 / "plate_reference.png"
    render_calibration_reference(effective_stl, y_holes, chosen, ref_png)
    print(f"\nWrote {ref_png}")

    # 4. Load the photo and collect 4 clicks side-by-side with the reference.
    img = cv2.imread(str(photo_path))
    if img is None:
        raise SystemExit(f"could not load {photo_path}")
    if cached_clicks is not None:
        print("Pre-loaded the 4 photo clicks from the previous run — press D "
              "to accept, or U to undo and re-click.")
    img_pts = collect_calibration_clicks(
        ref_png, img, n=4, initial_clicks=cached_clicks,
    )

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

    # Persist the picks before the canvas check below, so an abort from a
    # too-large warp doesn't force the user to re-click on the next run.
    out_png = stage2 / (photo_path.stem + "_rect.png")
    meta_path = out_png.with_suffix(".json")
    meta_path.write_text(json.dumps(dict(
        source_photo=str(photo_path),
        stl=str(effective_stl),
        source_stl=str(stl_path),
        face_axis_original=face_axis,
        chosen_y_hole_indices=chosen,
        chosen_y_hole_coords_mm=real_pts.tolist(),
        image_points_px=img_pts.tolist(),
        scale_px_per_mm=args.scale,
    ), indent=2))

    # 6. Size the rectified canvas to enclose the plate's known bounding box
    #    (from the STL), not the warped full photo. This decouples the canvas
    #    size from how tightly clustered the user's clicks happen to be — the
    #    output is always plate-sized, never blown up by perspective extremes
    #    in the photo's background.
    plate_x_min_mm = float(plate["plate_x_min"])
    plate_x_max_mm = float(plate["plate_x_max"])
    plate_z_min_mm = float(plate["plate_z_min"])
    plate_z_max_mm = float(plate["plate_z_max"])
    # ideal_dst is built with X*scale on the X axis and -Z*scale on the Y axis,
    # so the canvas footprint in ideal-dst pixels is:
    x0 = plate_x_min_mm * args.scale
    x1 = plate_x_max_mm * args.scale
    y0 = -plate_z_max_mm * args.scale
    y1 = -plate_z_min_mm * args.scale
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
        stl=str(effective_stl),
        source_stl=str(stl_path),
        face_axis_original=face_axis,
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

    # 8. Hand off to the optional manual-measurement loop. This step is a
    #    sanity check only — the polygon trace from stage 5 already encodes
    #    every dimension at the rectified-photo's known mm/px scale.
    mm_per_px = 1.0 / args.scale
    print("\nOptional sanity-check measurements — press D to skip, S to save.")
    measure_loop(
        rectified, mm_per_px,
        example=example, photo_stem=photo_path.stem,
    )

    # 9. Chain straight into stage 5 — polygon trace on the rectified photo.
    print("\nStage 5 — trace the plate outline on the rectified photo.")
    print("Controls: left=add  right/z=undo  c=close loop  s=save  q=quit")
    trace_polygon.run(example, image_override=out_png)


if __name__ == "__main__":
    main()
