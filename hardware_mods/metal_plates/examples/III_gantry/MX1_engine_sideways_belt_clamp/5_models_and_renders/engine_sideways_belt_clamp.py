"""Metal engine_sideways_belt_clamp — HTD5M belt clamp for the X-axis.

The Y-midplane slice of the plastic X_AXIS_BACK_CLIP.stl shows a flat
block with three semicircular "teeth" on the underside that the belt
threads under in a serpentine pattern (over-under-over) to lock against
slip. The aluminium version keeps the same envelope (27 x 23 x 41 mm),
two M5 mounting bolts on the top face, and three transverse pins on the
underside spaced at the HTD5M pitch.

Coordinate system: X = belt travel direction (long axis 41 mm), Y =
up/down (bolt axis), Z = across belt width.

Origin is at the centre of the block so it can be relocated to either
the front- or back-clip position in the assembly.

Run from inside nix-shell:
  nix-shell hardware_mods/metal_plates/shell.nix --run \\
    "python hardware_mods/metal_plates/examples/mid_horizontal_movement/engine_sideways_belt_clamp/5_models_and_renders/engine_sideways_belt_clamp.py"
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from build123d import (  # noqa: E402
    Box,
    Cylinder,
    Location,
    Part,
    export_step,
    export_stl,
)

HERE = Path(__file__).resolve().parent
NAME = "engine_sideways_belt_clamp"

# Envelope — matches the plastic X_AXIS_BACK_CLIP.stl bbox.
BODY_X = 41.0   # along belt travel
BODY_Y = 23.0   # vertical, bolt axis
BODY_Z = 27.0   # belt width direction (HTD5M belt is 9-15 mm wide; fits)

# Mounting bolts — through-holes along the Y axis (vertical).
BOLT_DIAM = 5.5   # M5 clearance
BOLT_PITCH_X = 26.0   # spacing along the belt-travel axis

# Belt-grip pins on the underside (cylindrical teeth across the belt).
PIN_DIAM = 5.0
PIN_PITCH_X = 8.0   # close to HTD5M 5 mm + tooth ≈ 8 mm interlock
PIN_COUNT = 3
PIN_Y = -BODY_Y / 2  # centre at the bottom face (half-buried tooth)
PIN_LEN = BODY_Z + 2  # span the full belt width


def build() -> Part:
    body = Box(BODY_X, BODY_Y, BODY_Z)

    parts = body
    # Bolt holes
    for k in (-1, 1):
        bolt = Cylinder(
            radius=BOLT_DIAM / 2,
            height=BODY_Y * 2,
            rotation=(90, 0, 0),
        ).locate(Location((k * BOLT_PITCH_X / 2, 0, 0)))
        parts = parts - bolt

    # Grip pins (subtract cylindrical pockets on the underside)
    start_x = -(PIN_COUNT - 1) / 2 * PIN_PITCH_X
    for i in range(PIN_COUNT):
        pin = Cylinder(
            radius=PIN_DIAM / 2,
            height=PIN_LEN,
            rotation=(0, 90, 0),  # axis along Z (across belt width)
        )
        # Cylinder default axis is Z; rotate so axis becomes Z by leaving it.
        # Re-create with axis along Z explicitly:
        pin = Cylinder(radius=PIN_DIAM / 2, height=PIN_LEN).locate(
            Location((start_x + i * PIN_PITCH_X, PIN_Y, 0))
        )
        parts = parts - pin

    return parts


def render_plan(out_png: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12, 6))

    # Side view (Z midplane): X horizontal, Y vertical
    ax = axes[0]
    ax.add_patch(plt.Rectangle(
        (-BODY_X / 2, -BODY_Y / 2), BODY_X, BODY_Y,
        fill=False, edgecolor="black", lw=2,
    ))
    for k in (-1, 1):
        # bolt is a through-hole on Y — draw as a vertical slot
        ax.add_patch(plt.Rectangle(
            (k * BOLT_PITCH_X / 2 - BOLT_DIAM / 2, -BODY_Y / 2),
            BOLT_DIAM, BODY_Y,
            fill=False, edgecolor="tab:red", lw=1.5,
        ))
    start_x = -(PIN_COUNT - 1) / 2 * PIN_PITCH_X
    for i in range(PIN_COUNT):
        ax.add_patch(plt.Circle(
            (start_x + i * PIN_PITCH_X, PIN_Y), PIN_DIAM / 2,
            fill=True, color="lightblue", edgecolor="tab:blue", lw=1,
            alpha=0.6,
        ))
    ax.set_aspect("equal")
    ax.set_xlim(-BODY_X / 2 - 5, BODY_X / 2 + 5)
    ax.set_ylim(-BODY_Y / 2 - 5, BODY_Y / 2 + 5)
    ax.set_xlabel("X (belt travel)")
    ax.set_ylabel("Y (vertical)")
    ax.set_title("Side view — grip pins (blue), bolts (red)")
    ax.grid(True, alpha=0.3)

    # End view (X midplane): Z horizontal, Y vertical
    ax = axes[1]
    ax.add_patch(plt.Rectangle(
        (-BODY_Z / 2, -BODY_Y / 2), BODY_Z, BODY_Y,
        fill=False, edgecolor="black", lw=2,
    ))
    ax.add_patch(plt.Rectangle(
        (-BODY_Z / 2 - 1, PIN_Y - PIN_DIAM / 2),
        BODY_Z + 2, PIN_DIAM,
        facecolor="lightblue", edgecolor="tab:blue", lw=1, alpha=0.4,
    ))
    ax.set_aspect("equal")
    ax.set_xlim(-BODY_Z / 2 - 5, BODY_Z / 2 + 5)
    ax.set_ylim(-BODY_Y / 2 - 5, BODY_Y / 2 + 5)
    ax.set_xlabel("Z (belt width)")
    ax.set_ylabel("Y (vertical)")
    ax.set_title("End view — pin cross-section (blue)")
    ax.grid(True, alpha=0.3)

    fig.suptitle(f"{NAME} — body (black), HTD5M grip pins (blue), M5 bolts (red)")
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
