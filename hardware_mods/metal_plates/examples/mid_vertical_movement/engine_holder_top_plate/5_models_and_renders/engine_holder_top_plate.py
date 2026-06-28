"""Metal engine_holder_top_plate, derived from Z_MOTOR_MOUNT.stl Z-face.

The outline is the plastic STL's Y-face silhouette (after the rectify
pipeline rotated Z→Y); the M3 motor mount + two big pulley pockets are
kept verbatim, and three M5 mounting features are added per the
hand-drawn schematic in 0_raw_screenshots/example_schematic.jpg.

Run from inside nix-shell:
  nix-shell hardware_mods/metal_plates/shell.nix --run \\
    "python hardware_mods/metal_plates/examples/mid_vertical_movement/engine_holder_top_plate/5_models_and_renders/engine_holder_top_plate.py"
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from build123d import (  # noqa: E402
    BuildLine,
    BuildPart,
    BuildSketch,
    Circle,
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
EX = HERE.parent
NAME = "engine_holder_top_plate"

SILHOUETTE_JSON = EX / "4_outline" / "plastic_silhouette.json"
HOLES_JSON = EX / "2_flattened_image" / "holes_from_stl.json"

# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------
PLATE_THICKNESS = 6.0  # mm

POCKET_DIAM = 22.0  # mm — motor shaft + lead-screw bearing clearance

# M5 mounting features at the back edge, 65 mm pitch to match
# engine_holder_vertical_p1of2's top keyhole-slot spacing, plus a
# central one through the lead-screw axis.
M5_PITCH = 65.0
M5_HOLE_DIAM = 5.5
M5_SLOT_LEN = 12.0  # mm — long axis along Y/Z (length-wise on plate)

# Motor centre (mid-point of the 4 M3 holes from Z_MOTOR_MOUNT.stl
# Z-face: X = (82.289 + 152.289)/2, Z = (348.131 + 379.131)/2).
CENTER_X = 117.289
CENTER_Z = 363.631


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------
def load_silhouette() -> list[tuple[float, float]]:
    pts = json.loads(SILHOUETTE_JSON.read_text())["vertices_xz_mm"]
    return [(float(x), float(z)) for x, z in pts]


def load_y_holes() -> list[dict]:
    return [h for h in json.loads(HOLES_JSON.read_text())["holes"]
            if h["axis"] == "Y"]


def m3_centres(y_holes: list[dict]) -> list[tuple[float, float]]:
    return [(h["cx"], h["cz"]) for h in y_holes if abs(h["r"] - 1.75) < 0.05]


def pocket_centres(y_holes: list[dict]) -> list[tuple[float, float]]:
    seen: set[tuple[float, float]] = set()
    out: list[tuple[float, float]] = []
    for h in y_holes:
        if h["r"] >= 8.0:
            key = (round(h["cx"], 2), round(h["cz"], 2))
            if key in seen:
                continue
            seen.add(key)
            out.append((h["cx"], h["cz"]))
    return out


def m5_slot_centres() -> list[tuple[float, float]]:
    """3 M5 slots at the back edge of the main body, centred on motor X."""
    # Back of main body sits at Z = 391.13 (silhouette top). Place slot
    # centres at Z = 385 so the slot ends sit ~6 mm shy of the top edge
    # and clear the M3 row at Z=379.131.
    z = 385.0
    return [
        (CENTER_X - M5_PITCH / 2, z),
        (CENTER_X,                z),
        (CENTER_X + M5_PITCH / 2, z),
    ]


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------
def build(silhouette: list[tuple[float, float]],
          m3: list[tuple[float, float]],
          pockets: list[tuple[float, float]],
          slots: list[tuple[float, float]]) -> BuildPart:
    with BuildPart() as plate:
        with BuildSketch() as sk:
            with BuildLine():
                Polyline(*silhouette, close=True)
            make_face()
            if m3:
                with Locations(*m3):
                    Circle(3.5 / 2, mode=Mode.SUBTRACT)
            if pockets:
                with Locations(*pockets):
                    Circle(POCKET_DIAM / 2, mode=Mode.SUBTRACT)
            if slots:
                slot_w = M5_HOLE_DIAM
                slot_h = M5_SLOT_LEN
                straight = max(slot_h - slot_w, 0.0)
                with Locations(*slots):
                    Rectangle(slot_w, straight, mode=Mode.SUBTRACT)
                # Round the slot ends (semicircular caps).
                cap_offset = straight / 2
                cap_centres = []
                for cx, cz in slots:
                    cap_centres.append((cx, cz - cap_offset))
                    cap_centres.append((cx, cz + cap_offset))
                with Locations(*cap_centres):
                    Circle(slot_w / 2, mode=Mode.SUBTRACT)
        extrude(amount=PLATE_THICKNESS)
    return plate


# ---------------------------------------------------------------------------
# Plan render
# ---------------------------------------------------------------------------
def render_plan(silhouette, m3, pockets, slots, out_png: Path) -> None:
    fig, ax = plt.subplots(figsize=(9, 6))
    xs = [p[0] for p in silhouette] + [silhouette[0][0]]
    zs = [p[1] for p in silhouette] + [silhouette[0][1]]
    ax.plot(xs, zs, "k-", lw=2)
    ax.fill(xs, zs, color="lightgray", alpha=0.4)

    for cx, cz in m3:
        ax.add_patch(plt.Circle((cx, cz), 3.5 / 2,
                                fill=False, color="tab:blue", lw=1.5))
    for cx, cz in pockets:
        ax.add_patch(plt.Circle((cx, cz), POCKET_DIAM / 2,
                                fill=False, color="tab:green", lw=1.5))

    slot_w = M5_HOLE_DIAM
    slot_h = M5_SLOT_LEN
    for cx, cz in slots:
        rect = plt.Rectangle((cx - slot_w / 2, cz - slot_h / 2 + slot_w / 2),
                              slot_w, max(slot_h - slot_w, 0.0),
                              fill=False, color="tab:red", lw=1.5)
        ax.add_patch(rect)
        ax.add_patch(plt.Circle((cx, cz - (slot_h - slot_w) / 2),
                                slot_w / 2, fill=False, color="tab:red", lw=1.5))
        ax.add_patch(plt.Circle((cx, cz + (slot_h - slot_w) / 2),
                                slot_w / 2, fill=False, color="tab:red", lw=1.5))

    ax.set_aspect("equal")
    ax.grid(True, alpha=0.3, lw=0.5)
    ax.set_xlabel("X (mm)")
    ax.set_ylabel("Z (mm)")
    ax.set_title(
        f"{NAME}  —  plastic silhouette, M3 motor mount (blue), "
        f"pockets (green), M5 slots (red)"
    )
    fig.tight_layout()
    fig.savefig(out_png, dpi=150, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    silhouette = load_silhouette()
    y_holes = load_y_holes()
    m3 = m3_centres(y_holes)
    pockets = pocket_centres(y_holes)
    slots = m5_slot_centres()

    plate = build(silhouette, m3, pockets, slots)

    step_path = HERE / f"{NAME}.step"
    stl_path = HERE / f"{NAME}.stl"
    plan_path = HERE / f"{NAME}_plan.png"
    export_step(plate.part, str(step_path))
    export_stl(plate.part, str(stl_path))
    render_plan(silhouette, m3, pockets, slots, plan_path)
    print(f"wrote {step_path.name}")
    print(f"wrote {stl_path.name}")
    print(f"wrote {plan_path.name}")


if __name__ == "__main__":
    main()
