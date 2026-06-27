"""trace_polygon.py — stage 5 of the metal-plate workflow.

Trace the metal plate's outline by clicking points on the rectified
photo from stage 2. The closed polygon is saved into stage 4 on save/quit
so the next stage (build_model.py) can pick it up.

Reads:
  <example>/2_flattened_image/*_rect.png   — the rectified photo from stage 2
                                              (auto-picked if exactly one)

Writes:
  <example>/4_outline/<rect>_polygon.json  — vertex list (pixel coords) +
                                              closed flag + image size
  <example>/4_outline/<rect>_polygon.png   — annotated screenshot of the trace

Controls (also shown as a persistent banner on the image):
  left-click   add vertex
  right-click  undo last vertex
  z            undo last vertex (keyboard)
  c            toggle closed (connect last vertex back to first)
  s            save now (polygon JSON + annotated PNG)
  q            quit (auto-saves if any vertices exist and not yet saved)

Refuses to start if no rectified image exists in stage 2 — run rectify.py
first.

Usage:

  nix-shell hardware_mods/metal_plates/shell.nix --run \\
    "python hardware_mods/metal_plates/trace_polygon.py \\
       --example hardware_mods/metal_plates/examples/.../P20_left_side_plate_p1of3"
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import matplotlib

if not os.environ.get("MPLBACKEND"):
    for backend in ("QtAgg", "TkAgg", "WebAgg"):
        try:
            matplotlib.use(backend, force=True)
            break
        except Exception:
            continue

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.image import imread  # noqa: E402


def find_rectified_image(example: Path, override: Path | None) -> Path:
    """Return the rectified PNG from stage 2, refusing if ambiguous/missing."""
    if override is not None:
        if not override.exists():
            raise SystemExit(f"--image not found: {override}")
        return override
    stage2 = example / "2_flattened_image"
    if not stage2.is_dir():
        raise SystemExit(
            f"missing stage-2 folder: {stage2}\n"
            "Run rectify.py first to produce the flattened photo."
        )
    candidates = sorted(stage2.glob("*_rect.png"))
    if not candidates:
        raise SystemExit(
            f"no *_rect.png in {stage2}\n"
            "Run rectify.py first to produce the flattened photo."
        )
    if len(candidates) > 1:
        listing = "\n  ".join(p.name for p in candidates)
        raise SystemExit(
            f"{len(candidates)} rectified images in {stage2}; pass --image to "
            "disambiguate:\n  " + listing
        )
    return candidates[0]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--example", type=Path, required=True,
                    help="example folder (the one containing the 0_..5_ stage dirs)")
    ap.add_argument("--image", type=Path, default=None,
                    help="rectified image to trace over (default: the single "
                         "*_rect.png in <example>/2_flattened_image/)")
    args = ap.parse_args()

    example: Path = args.example.resolve()
    if not example.is_dir():
        raise SystemExit(f"--example folder does not exist: {example}")
    outline_dir = example / "4_outline"
    outline_dir.mkdir(exist_ok=True)

    img_path = find_rectified_image(example, args.image)
    img = imread(img_path)
    h, w = img.shape[:2]

    json_out = outline_dir / f"{img_path.stem}_polygon.json"
    png_out = outline_dir / f"{img_path.stem}_polygon.png"
    saved_at_least_once = [False]  # boxed so nested fns can mutate

    pts: list[tuple[float, float]] = []
    closed = [False]

    fig, ax = plt.subplots(figsize=(12, 9))
    try:
        fig.canvas.manager.set_window_title(f"Trace polygon — {img_path.name}")
    except Exception:
        pass
    ax.imshow(img)
    ax.set_xlim(0, w)
    ax.set_ylim(h, 0)  # image coords: y grows down
    ax.set_axis_off()
    fig.subplots_adjust(left=0.01, right=0.99, top=0.92, bottom=0.01)

    # Persistent control banner — same idea as rectify.py.
    banner = (
        "left=add  right/z=undo  c=close loop  s=save  q=quit\n"
        f"saves to {json_out.relative_to(example) if json_out.is_relative_to(example) else json_out}"
    )
    ax.text(
        0.5, 0.995, banner,
        transform=ax.transAxes, ha="center", va="top",
        color="white", fontsize=11,
        bbox=dict(boxstyle="round,pad=0.4", fc="black", ec="white", alpha=0.75),
        zorder=100,
    )
    status_text = ax.text(
        0.01, 0.005, "vertices: 0  closed: no",
        transform=ax.transAxes, ha="left", va="bottom",
        color="white", fontsize=10,
        bbox=dict(boxstyle="round,pad=0.3", fc="black", ec="white", alpha=0.7),
        zorder=100,
    )

    (line,) = ax.plot([], [], "-", color="cyan", lw=1.5, zorder=10)
    (close_line,) = ax.plot([], [], "--", color="cyan", lw=1.5, alpha=0.7, zorder=10)
    (dots,) = ax.plot([], [], "o", color="yellow", ms=6, mec="black", mew=0.8, zorder=11)
    labels: list = []

    def redraw() -> None:
        if pts:
            xs, ys = zip(*pts)
            line.set_data(xs, ys)
            dots.set_data(xs, ys)
        else:
            line.set_data([], [])
            dots.set_data([], [])
        if closed[0] and len(pts) >= 2:
            close_line.set_data([pts[-1][0], pts[0][0]], [pts[-1][1], pts[0][1]])
        else:
            close_line.set_data([], [])
        for t in labels:
            t.remove()
        labels.clear()
        for i, (x, y) in enumerate(pts, start=1):
            labels.append(
                ax.annotate(
                    str(i), (x, y),
                    xytext=(6, -6), textcoords="offset points",
                    color="yellow", fontsize=9, fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.15", fc=(0, 0, 0, 0.6), ec="none"),
                    zorder=12,
                )
            )
        status_text.set_text(
            f"vertices: {len(pts)}  closed: {'yes' if closed[0] else 'no'}"
        )
        fig.canvas.draw_idle()

    def save() -> None:
        if not pts:
            print("nothing to save (no points)")
            return
        payload = {
            "source": str(img_path),
            "image_size_px": [w, h],
            "closed": closed[0],
            "vertices_px": [[float(x), float(y)] for x, y in pts],
        }
        json_out.write_text(json.dumps(payload, indent=2))
        fig.savefig(png_out, dpi=150, bbox_inches="tight")
        saved_at_least_once[0] = True
        print(f"wrote {json_out}")
        print(f"wrote {png_out}")

    def on_click(event) -> None:
        if event.inaxes is not ax or event.xdata is None:
            return
        if event.button == 1:
            pts.append((event.xdata, event.ydata))
        elif event.button == 3:
            if pts:
                pts.pop()
        redraw()

    def on_key(event) -> None:
        if event.key == "z":
            if pts:
                pts.pop()
                redraw()
        elif event.key == "c":
            closed[0] = not closed[0]
            redraw()
        elif event.key == "s":
            save()
        elif event.key == "q":
            plt.close(fig)

    fig.canvas.mpl_connect("button_press_event", on_click)
    fig.canvas.mpl_connect("key_press_event", on_key)

    print(f"Tracing {img_path}")
    print(f"On save / quit: writes polygon to {json_out}")
    print("Controls: left=add  right/z=undo  c=close  s=save  q=quit")
    plt.show()

    # Auto-save on close if user didn't press 's' but has points.
    if pts and not saved_at_least_once[0]:
        save()


if __name__ == "__main__":
    main()
