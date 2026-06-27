"""Parametric build123d outline of the P20 left side plate.

Stage ``4_outline`` of the P20_left_side_plate_p1of3 example: turns the
traced polygon into a parametric 3D outline. STEP/STL exports land in
``../5_models_and_renders/``.

Outline only — holes are not included. Geometry is derived from the polygon
trace in
``../2_flattened_image/Screenshot From 2026-06-27 15-29-35_polygon.json``,
with nearly-horizontal / nearly-vertical edges snapped to perfectly H/V.
The four intentional chamfers (bottom-left, big upper-left, tab-side,
bottom-right) are preserved as true diagonals.

The two U-shaped notches accept the horizontal steel cross-bars; both
notch heights are driven by ``BAR_PROFILE``.

Every numeric value below is independent — change any one and the outline
rebuilds. Defaults assume ``BAR_PROFILE = 30 mm`` (the traced notches each
measure ~30 mm at the implied 4.43 px/mm scale). Replace any number with a
real measurement from ``../2_flattened_image/measurements``.

Coordinate system: sketch is in the X-Y plane; origin at the plate's
bottom-left corner (after the bottom-left chamfer); +Y is up; the plate
extrudes in +Z by ``PLATE_THICKNESS``.

Run::

    nix-shell hardware_mods/metal_plates/shell.nix --run \\
      "python hardware_mods/metal_plates/examples/side_movement/\\
P20_left_side_plate_p1of3/4_outline/plate_outline.py"
"""
from __future__ import annotations

from pathlib import Path

from build123d import (
    BuildLine,
    BuildPart,
    BuildSketch,
    Plane,
    Polyline,
    export_step,
    export_stl,
    extrude,
    make_face,
)

# =============================================================================
# parameters (mm) — adjust any value and re-run
# =============================================================================
PLATE_THICKNESS = 6.0    # placeholder — set to your aluminium stock thickness
BAR_PROFILE     = 30.0   # height of the horizontal steel bars; sets both U-notch heights

# --- X breakpoints (left → right) -------------------------------------------
BL_CHAMFER_X        = 12.3   # bottom-left chamfer meets bottom edge      (V1)
LEFT_NOTCH_DEPTH    = 12.1   # depth of the left U-notch                  (V4, V5)
BIG_DIAG_X_END      = 36.4   # big upper-left diagonal ends here          (V8)
TAB_BASE_KINK_X     = 45.1   # small vertical step before tab diagonal    (V9, V10)
TAB_TOPLEFT_X       = 59.6   # top-left corner of tab (end of tab diag)   (V11)
RIGHT_MAIN_X        = 82.0   # right edge of main body          (V12, V13, V16, V17, V20, V21)
BR_CHAMFER_X        = 101.7  # bottom-right chamfer meets bottom edge     (V24)
RIGHT_BOTTOM_X      = 109.4  # right edge of bottom-right protrusion      (V22, V23)
RIGHT_NOTCH_DEPTH   = 12.6   # depth of the two right-side U-notches      (V14, V15, V18, V19)

# --- Y breakpoints (bottom → top) -------------------------------------------
BR_CHAMFER_TOP_Y       = 5.0    # top of bottom-right chamfer             (V23)
BL_CHAMFER_Y           = 13.3   # top of bottom-left chamfer              (V2)
RIGHT_PROTR_TOP_Y      = 34.4   # top of bottom-right protrusion          (V21, V22)
LOWER_NOTCH_BOTTOM_Y   = 43.5   # bottom of lower U-notch                 (V3, V4, V19, V20)
BIG_DIAG_Y_START       = 114.1  # left edge meets big upper-left diagonal (V7)
UPPER_NOTCH_BOTTOM_Y   = 157.4  # bottom of upper U-notch                 (V15, V16)
DIAG_HORIZONTAL_Y      = 163.2  # short horizontal between big diag & step (V8, V9)
SMALL_STEP_TOP_Y       = 172.7  # top of small step before tab diagonal   (V10)
TOP_Y                  = 194.8  # top of plate / tab                      (V11, V12)

# --- derived (do not edit) --------------------------------------------------
LOWER_NOTCH_TOP_Y  = LOWER_NOTCH_BOTTOM_Y + BAR_PROFILE
UPPER_NOTCH_TOP_Y  = UPPER_NOTCH_BOTTOM_Y + BAR_PROFILE
UPPER_NOTCH_LEFT_X = RIGHT_MAIN_X - RIGHT_NOTCH_DEPTH

# =============================================================================
# outline (CCW, y-up). Vertex numbers map to the trace in
# source/Screenshot From 2026-06-27 15-29-35_polygon.json.
# =============================================================================
OUTLINE = [
    (BL_CHAMFER_X,        0),                       #  1
    (0,                   BL_CHAMFER_Y),            #  2  (V1→V2 chamfer)
    (0,                   LOWER_NOTCH_BOTTOM_Y),    #  3
    (LEFT_NOTCH_DEPTH,    LOWER_NOTCH_BOTTOM_Y),    #  4
    (LEFT_NOTCH_DEPTH,    LOWER_NOTCH_TOP_Y),       #  5
    (0,                   LOWER_NOTCH_TOP_Y),       #  6
    (0,                   BIG_DIAG_Y_START),        #  7
    (BIG_DIAG_X_END,      DIAG_HORIZONTAL_Y),       #  8  (V7→V8 big diagonal)
    (TAB_BASE_KINK_X,     DIAG_HORIZONTAL_Y),       #  9
    (TAB_BASE_KINK_X,     SMALL_STEP_TOP_Y),        # 10
    (TAB_TOPLEFT_X,       TOP_Y),                   # 11  (V10→V11 tab diagonal)
    (RIGHT_MAIN_X,        TOP_Y),                   # 12
    (RIGHT_MAIN_X,        UPPER_NOTCH_TOP_Y),       # 13
    (UPPER_NOTCH_LEFT_X,  UPPER_NOTCH_TOP_Y),       # 14
    (UPPER_NOTCH_LEFT_X,  UPPER_NOTCH_BOTTOM_Y),    # 15
    (RIGHT_MAIN_X,        UPPER_NOTCH_BOTTOM_Y),    # 16
    (RIGHT_MAIN_X,        LOWER_NOTCH_TOP_Y),       # 17
    (UPPER_NOTCH_LEFT_X,  LOWER_NOTCH_TOP_Y),       # 18
    (UPPER_NOTCH_LEFT_X,  LOWER_NOTCH_BOTTOM_Y),    # 19
    (RIGHT_MAIN_X,        LOWER_NOTCH_BOTTOM_Y),    # 20
    (RIGHT_MAIN_X,        RIGHT_PROTR_TOP_Y),       # 21
    (RIGHT_BOTTOM_X,      RIGHT_PROTR_TOP_Y),       # 22
    (RIGHT_BOTTOM_X,      BR_CHAMFER_TOP_Y),        # 23
    (BR_CHAMFER_X,        0),                       # 24  (V23→V24 chamfer)
]


def build_plate():
    pts = list(OUTLINE) + [OUTLINE[0]]
    with BuildPart() as plate:
        with BuildSketch(Plane.XY):
            with BuildLine():
                Polyline(*pts)
            make_face()
        extrude(amount=PLATE_THICKNESS)
    return plate.part


def main():
    part = build_plate()
    here = Path(__file__).resolve().parent
    out_dir = here.parent / "5_models_and_renders"
    out_dir.mkdir(exist_ok=True)
    step_out = out_dir / "P20_left_side_plate_outline.step"
    stl_out  = out_dir / "P20_left_side_plate_outline.stl"
    export_step(part, str(step_out))
    export_stl(part, str(stl_out))

    bb = part.bounding_box()
    print(f"wrote {step_out}")
    print(f"wrote {stl_out}")
    print(f"bbox  X[{bb.min.X:6.1f} .. {bb.max.X:6.1f}]"
          f"  Y[{bb.min.Y:6.1f} .. {bb.max.Y:6.1f}]"
          f"  Z[{bb.min.Z:6.1f} .. {bb.max.Z:6.1f}]   (mm)")
    print(f"size  {bb.max.X - bb.min.X:.1f} W  x  "
          f"{bb.max.Y - bb.min.Y:.1f} H  x  "
          f"{bb.max.Z - bb.min.Z:.1f} T  mm")
    print(f"vol   {part.volume:.0f} mm^3   (~{part.volume * 2.7e-3:.0f} g in aluminium)")


if __name__ == "__main__":
    main()
