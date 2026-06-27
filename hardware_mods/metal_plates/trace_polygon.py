"""Interactive polygon tracer for plate photos.

Open an image, click points to define the closed outline, then save the
vertex list and an annotated preview alongside the source.

Controls
  left-click     add vertex
  right-click    undo last vertex
  z              undo last vertex (keyboard)
  c              toggle closed (connect last vertex back to first)
  s              save <image>_polygon.json + <image>_polygon.png
  q              quit (also saves on close if any points exist)

Run

  nix-shell hardware_mods/metal_plates/shell.nix --run \
    "python hardware_mods/metal_plates/trace_polygon.py <image.png>"

Coordinates are stored as pixels of the source image (origin = top-left,
matching PIL / typical image conventions).
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


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("image", type=Path)
    args = ap.parse_args()

    img_path: Path = args.image
    if not img_path.exists():
        raise SystemExit(f"no such file: {img_path}")

    img = imread(img_path)
    h, w = img.shape[:2]

    json_out = img_path.with_name(f"{img_path.stem}_polygon.json")
    png_out = img_path.with_name(f"{img_path.stem}_polygon.png")

    pts: list[tuple[float, float]] = []
    closed = [False]  # boxed so nested fns can mutate

    fig, ax = plt.subplots(figsize=(12, 9))
    ax.imshow(img)
    ax.set_xlim(0, w)
    ax.set_ylim(h, 0)  # image coords: y grows down
    ax.set_title(
        f"{img_path.name}  —  left:add  right:undo  c:close  s:save  q:quit"
    )

    (line,) = ax.plot([], [], "-", color="cyan", lw=1.5)
    (close_line,) = ax.plot([], [], "--", color="cyan", lw=1.5, alpha=0.7)
    (dots,) = ax.plot([], [], "o", color="yellow", ms=6, mec="black", mew=0.8)
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
                    str(i),
                    (x, y),
                    xytext=(6, -6),
                    textcoords="offset points",
                    color="yellow",
                    fontsize=9,
                    fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.15", fc=(0, 0, 0, 0.6), ec="none"),
                )
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

    print("Polygon tracer — left:add  right:undo  z:undo  c:close  s:save  q:quit")
    plt.tight_layout()
    plt.show()

    # auto-save on close if user didn't press 's' but has points
    if pts and not json_out.exists():
        save()


if __name__ == "__main__":
    main()
