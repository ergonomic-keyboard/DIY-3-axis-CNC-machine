"""build123d model of the LEFT SIDE PLATE, aluminium version.

Geometry:
  * Flat plate, 10 mm aluminium (one of the two thicknesses the video uses).
  * Hole positions and diameters come from ./holes.json — produced by
    `../../../extract_holes.py docs/stl_files/side_plates/left/LEFT_PLATE.stl
    --out ./holes.json`.
  * Silhouette is an approximation of the metal plate visible in
    `../../../examples/side_movement/P20_left_side_plate_p1of3/`
    (a flat panel rather than the plastic version's perpendicular fin).

Coordinates match the STL's plate frame: X is the long axis (rail length),
Z is plate height, Y is plate thickness. The metal plate sits with its face
on the XZ plane and is extruded along +Y.
"""
from __future__ import annotations

import json
from pathlib import Path

from build123d import (
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

HERE = Path(__file__).resolve().parent
HOLES_JSON = HERE / "holes.json"
PLATE_THICKNESS = 10.0  # mm — aluminium side plate

# Outline of the metal side plate in the X-Z plane (mm), clockwise from
# bottom-left. The shape is a flat panel that mirrors the silhouette of the
# left side plate in the build-video screenshots: a wide rail-mount block at
# the bottom, a narrower neck with the clip mount holes, and a motor-mount
# tab at the top. It encloses all holes recovered from the plastic STL.
OUTLINE = [
    (85.0,   -9.0),   # bottom-left
    (190.0,  -9.0),   # bottom-right
    (190.0,  90.0),   # right side keeps the right-edge hole inside
    (170.0, 105.0),   # step in above the right-edge hole
    (170.0, 115.0),   # right side of upper neck
    (165.0, 175.0),   # right side of motor tab
    (150.0, 190.0),   # top-right peak
    (125.0, 190.0),   # top-left peak
    (105.0, 175.0),   # angled shoulder (left)
    (100.0, 115.0),   # left side of motor tab
    (95.0,  100.0),   # step out for clip area
    (95.0,   35.0),   # left side of rail-mount block
    (85.0,   35.0),   # step out at rail-mount block
]


def load_holes() -> list[dict]:
    return json.loads(HOLES_JSON.read_text())["holes"]


def metal_holes(holes: list[dict]) -> list[dict]:
    """Pick the through-holes that belong on the flat metal plate.

    The plastic STL contains stepped pockets (counterbores/recesses) and the
    perpendicular-fin holes; on a flat metal plate we keep one through-hole
    per (cx, cz) position, plus the motor mount hole mapped onto the plate
    face from the perpendicular-fin (axis=X) detection.
    """
    kept: list[dict] = []

    # Y-axis through-holes: smallest diameter per (cx, cz) is the screw bore.
    y_holes = [h for h in holes if h["axis"] == "Y"]
    best_at: dict[tuple[float, float], dict] = {}
    for h in y_holes:
        key = (round(h["cx"], 2), round(h["cz"], 2))
        if key not in best_at or h["d"] < best_at[key]["d"]:
            best_at[key] = h
    for h in best_at.values():
        kept.append(dict(cx=h["cx"], cz=h["cz"], d=h["d"], note="Y-through"))

    # Motor mount hole on the perpendicular fin (axis=X) sits in the upper
    # tab area (cz>100). On the flat metal plate, place it at the fin's X
    # midplane, projected to the plate face.
    for h in holes:
        if h["axis"] != "X" or h["thickness"] < 6 or h["d"] > 30:
            continue
        if h["cz"] < 100:                       # ignore artifacts from steps
            continue
        if not (-30 <= h["cy"] <= 30):
            continue
        kept.append(dict(cx=h["cx"], cz=h["cz"], d=h["d"], note="motor-mount"))

    return kept


def build_plate(holes: list[dict]):
    pts = list(OUTLINE) + [OUTLINE[0]]
    with BuildPart() as plate:
        with BuildSketch(Plane.XZ):
            with BuildLine():
                Polyline(*pts)
            make_face()
            # Subtract each hole. Per-hole Locations keeps radii independent.
            for h in holes:
                with Locations((h["cx"], h["cz"])):
                    Circle(radius=h["d"] / 2, mode=Mode.SUBTRACT)
        extrude(amount=PLATE_THICKNESS)
    return plate.part


def main():
    holes = metal_holes(load_holes())
    print(f"Holes placed on metal plate: {len(holes)}")
    for h in sorted(holes, key=lambda h: (round(h["cz"], 1), round(h["cx"], 1))):
        print(f"  ({h['cx']:7.2f}, {h['cz']:7.2f})  d = {h['d']:.2f}  [{h['note']}]")

    part = build_plate(holes)

    step_out = HERE / "side_plate_left_metal.step"
    stl_out = HERE / "side_plate_left_metal.stl"
    export_step(part, str(step_out))
    export_stl(part, str(stl_out))
    print(f"\nWrote {step_out}")
    print(f"Wrote {stl_out}")

    bb = part.bounding_box()
    print(f"\nFinal bbox: X[{bb.min.X:.1f}..{bb.max.X:.1f}] "
          f"Y[{bb.min.Y:.1f}..{bb.max.Y:.1f}] "
          f"Z[{bb.min.Z:.1f}..{bb.max.Z:.1f}]")
    print(f"Volume: {part.volume:.0f} mm^3 "
          f"(mass at Al 2.7 g/cm^3 ≈ {part.volume * 2.7e-3:.1f} g)")


if __name__ == "__main__":
    main()
