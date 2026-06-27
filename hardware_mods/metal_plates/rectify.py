"""Photo rectifier + measurer for the metal-plate screenshots.

Workflow:

  1. Calibrate
       Click 4 points in the photo that you know the real (X, Z)
       coordinates of (e.g. the 4 corner M3 holes of the rail-mount block:
       (103, 1), (178, 1), (178, 21), (103, 21)). The script computes the
       homography that maps photo pixels to plate-frame millimetres and
       saves a rectified PNG plus the homography matrix.

  2. Measure
       In the rectified window, left-click two points to read the distance
       between them (in mm). Right-click to reset.
       Press 'q' to quit.

Run:

  nix-shell hardware_mods/metal_plates/shell.nix --run \
    "python hardware_mods/metal_plates/rectify.py \
       <image.png> \
       --pts 103,1 178,1 178,21 103,21 \
       --out side_movement_rectified.png"

The 4 calibration points can be in any order — just click them in the
same order on the photo. They must be (close to) coplanar with the
plate's flat face for the rectification to be accurate.
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


def parse_points(strs: list[str]) -> np.ndarray:
    pts = []
    for s in strs:
        x, z = s.split(",")
        pts.append((float(x), float(z)))
    if len(pts) != 4:
        raise SystemExit(f"--pts needs exactly 4 entries, got {len(pts)}")
    return np.asarray(pts, dtype=np.float64)


def _full_screen_figure(img: np.ndarray, window_title: str, overlay: str):
    """Create a maximised, chromeless figure showing img.

    Axes fill the entire window; the image keeps its aspect ratio
    (so any unused screen area is letterboxed). Click → data coords
    are still in source-image pixels, so measurements are unaffected.
    """
    fig, ax = plt.subplots()
    try:
        fig.canvas.manager.set_window_title(window_title)
    except Exception:
        pass
    ax.imshow(cv2.cvtColor(img, cv2.COLOR_BGR2RGB), interpolation="bilinear")
    ax.set_axis_off()
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
    fig.patch.set_facecolor("black")  # letterbox bands are black
    # Maximise on whichever GUI backend matplotlib picked
    mgr = fig.canvas.manager
    for fn in (
        lambda: mgr.window.showMaximized(),         # Qt
        lambda: mgr.window.state("zoomed"),         # TkAgg (Windows-style)
        lambda: mgr.full_screen_toggle(),           # generic
    ):
        try:
            fn()
            break
        except Exception:
            continue
    # Lightweight on-image instruction overlay (top-centre)
    ax.text(
        0.5, 0.99, overlay,
        transform=ax.transAxes, ha="center", va="top",
        color="white", fontsize=11,
        bbox=dict(boxstyle="round,pad=0.4", fc="black", ec="white", alpha=0.7),
    )
    return fig, ax


def pick_points(img: np.ndarray, n: int, label: str) -> np.ndarray:
    """Show img full-screen and collect n left-clicks. 'u' undoes."""
    fig, ax = _full_screen_figure(
        img,
        window_title=f"{label} — click {n} points",
        overlay=f"{label}: click {n} points  (u=undo, q=quit)",
    )
    picked: list[tuple[float, float]] = []
    artists: list = []

    def redraw():
        for a in artists:
            a.remove()
        artists.clear()
        for i, (x, y) in enumerate(picked):
            (dot,) = ax.plot([x], [y], "o", color="red", markersize=8)
            txt = ax.annotate(str(i + 1), (x, y), color="white",
                              xytext=(6, -6), textcoords="offset points",
                              fontsize=10, weight="bold")
            artists.extend([dot, txt])
        fig.canvas.draw_idle()

    def on_click(e):
        if e.inaxes is not ax or e.button != 1:
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
        raise SystemExit(f"only got {len(picked)} clicks, needed {n}")
    return np.asarray(picked, dtype=np.float64)


def measure_loop(img_rect: np.ndarray, mm_per_px: float) -> None:
    fig, ax = _full_screen_figure(
        img_rect,
        window_title="Measure",
        overlay="Left-click two points to measure  (right-click=reset, q=quit)",
    )
    state = {"pts": []}
    overlay_text = None  # remember the instruction text artist so we never delete it

    # The first text on ax is our overlay; everything after is measurement text.
    overlay_text = ax.texts[0]

    def render():
        # Wipe measurement artists (keep the overlay text)
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
            ax.annotate(f"{d_mm:.2f} mm",
                        mid, color="black",
                        bbox=dict(boxstyle="round", fc="lime", ec="black"),
                        fontsize=11, weight="bold")
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


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("image", type=Path, help="input photo")
    ap.add_argument("--pts", nargs=4, required=True,
                    metavar="X,Z",
                    help="real-world (X,Z) mm coords of 4 click points")
    ap.add_argument("--scale", type=float, default=4.0,
                    help="output pixels per mm (default 4 → 0.25 mm/px)")
    ap.add_argument("--pad", type=float, default=10.0,
                    help="mm of padding around the rectified image")
    ap.add_argument("--bounds", type=float, nargs=4, default=None,
                    metavar=("X_MIN", "X_MAX", "Z_MIN", "Z_MAX"),
                    help="explicit canvas bounds in real mm (default: bbox of "
                         "the warped source image — keeps the whole photo visible)")
    ap.add_argument("--max-px", type=int, default=40_000_000,
                    help="hard cap on canvas pixel count (default 40 Mpx) so "
                         "a wild perspective doesn't allocate a giant image")
    ap.add_argument("--out", type=Path, default=None,
                    help="output rectified PNG (default: <image>_rect.png)")
    args = ap.parse_args()

    img = cv2.imread(str(args.image))
    if img is None:
        raise SystemExit(f"could not load {args.image}")

    real_pts = parse_points(args.pts)
    img_pts = pick_points(img, 4, "Calibrate")

    # Build the homography in an "ideal" frame where:
    #   ideal_x = real_X * scale,  ideal_y = -real_Z * scale  (Z grows up,
    #   so flip for image coords where Y grows down).
    ideal_dst = np.column_stack([
         real_pts[:, 0] * args.scale,
        -real_pts[:, 1] * args.scale,
    ]).astype(np.float64)

    H_ideal, _ = cv2.findHomography(img_pts, ideal_dst, method=0)
    if H_ideal is None:
        raise SystemExit("homography failed — points may be collinear")

    # Warp the source-image corners to find where the whole photo lands
    # in the ideal frame, then size the canvas to enclose all of it.
    if args.bounds is not None:
        bx0, bx1, bz0, bz1 = args.bounds
        x0 = bx0 * args.scale
        x1 = bx1 * args.scale
        # ideal_y = -real_Z * scale, so smallest ideal_y = -bz1 * scale
        y0 = -bz1 * args.scale
        y1 = -bz0 * args.scale
    else:
        src_h_img, src_w_img = img.shape[:2]
        src_corners = np.array([[0, 0], [src_w_img, 0],
                                [src_w_img, src_h_img], [0, src_h_img]],
                               dtype=np.float64).reshape(-1, 1, 2)
        warped = cv2.perspectiveTransform(src_corners, H_ideal).reshape(-1, 2)
        x0, y0 = warped.min(axis=0)
        x1, y1 = warped.max(axis=0)

    pad_px = args.pad * args.scale
    W = int(round((x1 - x0) + 2 * pad_px))
    H = int(round((y1 - y0) + 2 * pad_px))

    if W * H > args.max_px:
        raise SystemExit(
            f"output canvas would be {W}x{H} px ({W*H/1e6:.1f} Mpx) — bigger than "
            f"--max-px ({args.max_px/1e6:.1f} Mpx). Pass --bounds X_MIN X_MAX Z_MIN Z_MAX "
            f"to restrict, or raise --max-px."
        )

    # Translation that shifts the warped bbox to (pad_px, pad_px)
    T = np.array([[1.0, 0.0, -x0 + pad_px],
                  [0.0, 1.0, -y0 + pad_px],
                  [0.0, 0.0, 1.0]])
    H_mat = T @ H_ideal

    rectified = cv2.warpPerspective(img, H_mat, (W, H))

    # Real-world bounds the canvas covers (for the JSON metadata)
    x_min = (x0 - pad_px) / args.scale
    x_max = (x1 + pad_px) / args.scale
    z_max = -(y0 - pad_px) / args.scale
    z_min = -(y1 + pad_px) / args.scale

    out_png = args.out or args.image.with_name(args.image.stem + "_rect.png")
    cv2.imwrite(str(out_png), rectified)
    meta = dict(
        source=str(args.image),
        real_points_mm=real_pts.tolist(),
        image_points_px=img_pts.tolist(),
        homography=H_mat.tolist(),
        scale_px_per_mm=args.scale,
        canvas_real_bounds_mm=dict(
            x_min=x_min, x_max=x_max, z_min=z_min, z_max=z_max
        ),
        output_size_px=[W, H],
    )
    meta_path = out_png.with_suffix(".json")
    meta_path.write_text(json.dumps(meta, indent=2))
    print(f"Wrote {out_png}  ({W}x{H} px, {args.scale} px/mm)")
    print(f"Wrote {meta_path}")

    mm_per_px = 1.0 / args.scale
    print("\nMeasure mode — close window to exit.")
    measure_loop(rectified, mm_per_px)


if __name__ == "__main__":
    main()
