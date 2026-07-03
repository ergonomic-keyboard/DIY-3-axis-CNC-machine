"""Metal router clamp — top + bottom halves.

Single-piece aluminium clamp plate that grips the router/spindle body via
a circular bore with a radial saw-slit; tightening one M6 cross-bolt
closes the slit and compresses the bore around the router. Two of these
plates are bolted to the front of engine_holder_vertical_plate_p1of2 —
one near the top, one near the bottom — to constrain the router on its
long axis. Plates are identical (top == bottom for v0); differentiate
later if the assembly demands it.

Coordinate system used here (clamp-local):
  X — along the plate width (left/right)
  Y — perpendicular to the back face (depth, into the plate body)
  Z — along the router axis (vertical in the assembly), == thickness

Default values match a Makita RT0700-class router body (65 mm OD).

Run from inside nix-shell:
  nix-shell hardware_mods/metal_plates/shell.nix --run \\
    "python hardware_mods/metal_plates/examples/mid_vertical_movement/router_clamp_top/5_models_and_renders/router_clamp.py"
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from build123d import (  # noqa: E402
    Box,
    BuildLine,
    BuildPart,
    BuildSketch,
    Circle,
    CenterArc,
    Cylinder,
    GridLocations,
    Line,
    Location,
    Locations,
    Mode,
    Polyline,
    Rectangle,
    export_step,
    export_stl,
    extrude,
    make_face,
)

HERE = Path(__file__).resolve().parent
NAME = "router_clamp"

# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------
PLATE_WIDTH = 110.0     # X — along Z plate face (left/right)
PLATE_DEPTH = 100.0     # Y — sticking out from Z plate
PLATE_THICK = 12.0      # Z — vertical thickness (along router axis)

BORE_DIAM = 65.0        # router OD (Makita RT0700 = 65 mm)
BORE_CENTER_Y = 8.0     # bore centre Y, measured from plate centre toward
                        # the front; positive shifts bore toward +Y front.

SAW_SLIT_WIDTH = 2.5    # slit goes from bore wall to the +Y front edge.

# Cross-bolt that closes the slit (M6 clearance) — passes through the
# plate in the X direction across the slit. Placed between bore wall and
# the front edge.
CROSS_BOLT_DIAM = 6.5
CROSS_BOLT_Y = BORE_CENTER_Y + BORE_DIAM / 2 + 5.0   # 5 mm past bore edge

# Mounting holes — M5 clearance through the plate in Z (vertical) axis;
# the two bolts thread into the engine_holder_vertical_plate behind.
MOUNT_BOLT_DIAM = 5.5
MOUNT_X_PITCH = 80.0
MOUNT_Y_OFFSET = -PLATE_DEPTH / 2 + 8.0  # 8 mm from the back edge


def build():
    body = Box(PLATE_WIDTH, PLATE_DEPTH, PLATE_THICK)

    # Bore (router pocket) — vertical axis along Z, fully through.
    bore = Cylinder(
        radius=BORE_DIAM / 2,
        height=PLATE_THICK * 1.5,
    ).locate(Location((0, BORE_CENTER_Y, 0)))

    # Saw slit — narrow slot from bore wall to +Y front edge.
    slit_y_min = BORE_CENTER_Y
    slit_y_max = PLATE_DEPTH / 2 + 1
    slit_cy = (slit_y_min + slit_y_max) / 2
    slit = Box(
        SAW_SLIT_WIDTH,
        slit_y_max - slit_y_min,
        PLATE_THICK * 1.5,
    ).locate(Location((0, slit_cy, 0)))

    # Cross-bolt — clearance through full X width, sitting between the
    # bore wall and the front edge so tightening pinches the slit shut.
    cross = Cylinder(
        radius=CROSS_BOLT_DIAM / 2,
        height=PLATE_WIDTH * 1.5,
        rotation=(0, 90, 0),
    ).locate(Location((0, CROSS_BOLT_Y, 0)))

    # Mounting holes — M5 clearance through Z near the back edge.
    part = body - bore - slit - cross
    for sx in (-1, 1):
        mh = Cylinder(
            radius=MOUNT_BOLT_DIAM / 2,
            height=PLATE_THICK * 1.5,
        ).locate(Location((sx * MOUNT_X_PITCH / 2, MOUNT_Y_OFFSET, 0)))
        part = part - mh

    return part


def render_plan(out_png: Path) -> None:
    fig, ax = plt.subplots(figsize=(9, 7))

    ax.add_patch(plt.Rectangle(
        (-PLATE_WIDTH / 2, -PLATE_DEPTH / 2),
        PLATE_WIDTH, PLATE_DEPTH,
        fill=False, edgecolor="black", lw=2,
    ))
    ax.add_patch(plt.Circle(
        (0, BORE_CENTER_Y), BORE_DIAM / 2,
        fill=False, edgecolor="tab:blue", lw=2,
    ))
    # Saw slit
    ax.add_patch(plt.Rectangle(
        (-SAW_SLIT_WIDTH / 2, BORE_CENTER_Y),
        SAW_SLIT_WIDTH, PLATE_DEPTH / 2 - BORE_CENTER_Y + 1,
        fill=True, facecolor="lightyellow",
        edgecolor="tab:olive", lw=1.5,
    ))
    # Cross-bolt drawn as a horizontal slot across X
    ax.add_patch(plt.Rectangle(
        (-PLATE_WIDTH / 2, CROSS_BOLT_Y - CROSS_BOLT_DIAM / 2),
        PLATE_WIDTH, CROSS_BOLT_DIAM,
        fill=False, edgecolor="tab:red", lw=1.5, ls="--",
    ))
    for sx in (-1, 1):
        ax.add_patch(plt.Circle(
            (sx * MOUNT_X_PITCH / 2, MOUNT_Y_OFFSET),
            MOUNT_BOLT_DIAM / 2,
            fill=False, edgecolor="tab:green", lw=1.5,
        ))

    ax.set_aspect("equal")
    ax.set_xlim(-PLATE_WIDTH / 2 - 5, PLATE_WIDTH / 2 + 5)
    ax.set_ylim(-PLATE_DEPTH / 2 - 5, PLATE_DEPTH / 2 + 5)
    ax.set_xlabel("X (mm) — left/right")
    ax.set_ylabel("Y (mm) — depth from back")
    ax.set_title(f"{NAME} — bore (blue), saw slit (yellow), "
                 "cross-bolt (red), mount holes (green)")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_png, dpi=150, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    part = build()
    step_path = HERE / f"{NAME}.step"
    stl_path = HERE / f"{NAME}.stl"
    plan_path = HERE / f"{NAME}_plan.png"
    export_step(part, str(step_path))
    export_stl(part, str(stl_path))
    render_plan(plan_path)
    print(f"wrote {step_path.name}")
    print(f"wrote {stl_path.name}")
    print(f"wrote {plan_path.name}")


if __name__ == "__main__":
    main()
