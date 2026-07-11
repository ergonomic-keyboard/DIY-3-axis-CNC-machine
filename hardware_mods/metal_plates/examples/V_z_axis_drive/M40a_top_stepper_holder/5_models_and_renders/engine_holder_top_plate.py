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

# ── cross-env bootstrap: make the build123d toolchain importable on Nix or Ubuntu ─
# Walks up to hardware_mods/metal_plates/env_bootstrap.py, then re-execs this script
# into a set-up env (.venv on Ubuntu / nix-shell on NixOS) when build123d is not
# already importable. No-op when already inside the right environment.
import os as _os, sys as _sys  # noqa: E402
_d = _os.path.dirname(_os.path.abspath(__file__))
while _d != _os.path.dirname(_d) and not _os.path.exists(_os.path.join(_d, "env_bootstrap.py")):
    _d = _os.path.dirname(_d)
if _d not in _sys.path:
    _sys.path.insert(0, _d)
import env_bootstrap as _env  # noqa: E402
_env.ensure_build123d(__file__)

import json
from pathlib import Path

import matplotlib
import matplotlib.patches as mpatches

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
POCKET_R = POCKET_DIAM / 2  # 11 mm

# M5 mounting features at the back edge, 65 mm pitch to match
# engine_holder_vertical_p1of2's top keyhole-slot spacing, plus a
# central one through the lead-screw axis.
M5_PITCH = 65.0
M5_HOLE_DIAM = 5.5

# Motor centre (mid-point of the 4 M3 holes from Z_MOTOR_MOUNT.stl
# Z-face: X = (82.289 + 152.289)/2, Z = (348.131 + 379.131)/2).
CENTER_X = 117.289
CENTER_Z = 363.631

# Slider slots — horizontal (long axis in X), one above each pocket semicircle.
# Positioned along the positive-Z side of the merged oval cutout.
SLIDER_TOTAL_LEN = 25.0   # mm — total horizontal slot length including end caps
SLIDER_WIDTH = M5_HOLE_DIAM  # 5.5 mm — slot thickness (Z extent)
SLIDER_GAP = 2.0          # mm — clearance between oval top edge and slot bottom

# Holes A and B — M5 clearance mounting holes in the top cross-member of the
# T-bar, aligned with the bolt holes on p1of2's top edge (edges 49/51 and 57/59).
# X positions follow the M5_PITCH spacing; Z chosen to sit in the upper
# cross-member clear of the slider slots.
HOLE_AB_Z = 385.0


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


# ---------------------------------------------------------------------------
# Derived geometry helpers
# ---------------------------------------------------------------------------
def oval_params(pockets: list[tuple[float, float]]) -> dict:
    """Return geometry of the merged athletics-track oval from the two pocket centres."""
    left_cx  = min(p[0] for p in pockets)
    right_cx = max(p[0] for p in pockets)
    cz       = pockets[0][1]          # both pockets share the same Z
    straight = right_cx - left_cx     # 39 mm straight section between centres
    return dict(left_cx=left_cx, right_cx=right_cx, cz=cz,
                cx=(left_cx + right_cx) / 2, straight=straight)


def slider_centres(oval: dict) -> list[tuple[float, float]]:
    """Two horizontal slider slots: one centred above each oval end-semicircle."""
    slider_z = oval["cz"] + POCKET_R + SLIDER_GAP + SLIDER_WIDTH / 2
    return [(oval["left_cx"], slider_z), (oval["right_cx"], slider_z)]


def hole_ab_centres() -> list[tuple[float, float]]:
    """Holes A and B: M5 clearance holes in the top cross-member at M5_PITCH spacing."""
    return [
        (CENTER_X - M5_PITCH / 2, HOLE_AB_Z),
        (CENTER_X + M5_PITCH / 2, HOLE_AB_Z),
    ]


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------
def build(silhouette: list[tuple[float, float]],
          m3: list[tuple[float, float]],
          pockets: list[tuple[float, float]]) -> BuildPart:
    oval    = oval_params(pockets)
    sliders = slider_centres(oval)
    holes_ab = hole_ab_centres()

    slider_straight = SLIDER_TOTAL_LEN - SLIDER_WIDTH  # straight section of each slot

    with BuildPart() as plate:
        with BuildSketch():
            with BuildLine():
                Polyline(*silhouette, close=True)
            make_face()

            # M3 motor-mount holes
            if m3:
                with Locations(*m3):
                    Circle(3.5 / 2, mode=Mode.SUBTRACT)

            # ── Merged oval (single athletics-track cutout) ───────────────────
            # Rectangle spanning the straight section + a full circle at each end.
            with Locations((oval["cx"], oval["cz"])):
                Rectangle(oval["straight"], POCKET_DIAM, mode=Mode.SUBTRACT)
            with Locations((oval["left_cx"], oval["cz"])):
                Circle(POCKET_R, mode=Mode.SUBTRACT)
            with Locations((oval["right_cx"], oval["cz"])):
                Circle(POCKET_R, mode=Mode.SUBTRACT)

            # ── Two horizontal slider slots ───────────────────────────────────
            # Long axis in X, positioned along the top of the merged oval.
            with Locations(*sliders):
                Rectangle(slider_straight, SLIDER_WIDTH, mode=Mode.SUBTRACT)
            # Semicircular end caps (left and right of each slot)
            cap_offset = slider_straight / 2
            slider_caps = []
            for cx, cz in sliders:
                slider_caps.append((cx - cap_offset, cz))
                slider_caps.append((cx + cap_offset, cz))
            with Locations(*slider_caps):
                Circle(SLIDER_WIDTH / 2, mode=Mode.SUBTRACT)

            # ── Holes A and B (top cross-member, aligned with p1of2 top edge) ─
            with Locations(*holes_ab):
                Circle(M5_HOLE_DIAM / 2, mode=Mode.SUBTRACT)

        extrude(amount=PLATE_THICKNESS)
    return plate


# ---------------------------------------------------------------------------
# Plan render
# ---------------------------------------------------------------------------
def _draw_oblong_h(ax, cx, cz, total_len, width, **kw):
    """Draw a horizontal oblong (stadium) outline on ax."""
    straight = total_len - width
    r = width / 2
    rect = mpatches.FancyBboxPatch(
        (cx - straight / 2 - r, cz - r),
        straight + 2 * r, 2 * r,
        boxstyle=f"round,pad=0,rounding_size={r}",
        **kw,
    )
    ax.add_patch(rect)


def _draw_oblong_v(ax, cx, cz, total_len, width, **kw):
    """Draw a vertical oblong (stadium) outline on ax."""
    straight = total_len - width
    r = width / 2
    rect = mpatches.FancyBboxPatch(
        (cx - r, cz - straight / 2 - r),
        2 * r, straight + 2 * r,
        boxstyle=f"round,pad=0,rounding_size={r}",
        **kw,
    )
    ax.add_patch(rect)


def render_plan(silhouette, m3, pockets, out_png: Path) -> None:
    oval     = oval_params(pockets)
    sliders  = slider_centres(oval)
    holes_ab = hole_ab_centres()

    fig, ax = plt.subplots(figsize=(9, 6))
    xs = [p[0] for p in silhouette] + [silhouette[0][0]]
    zs = [p[1] for p in silhouette] + [silhouette[0][1]]
    ax.plot(xs, zs, "k-", lw=2)
    ax.fill(xs, zs, color="lightgray", alpha=0.4)

    # M3 motor holes
    for cx, cz in m3:
        ax.add_patch(plt.Circle((cx, cz), 3.5 / 2,
                                fill=False, color="tab:blue", lw=1.5))

    # Merged oval
    oval_total_x = oval["straight"] + 2 * POCKET_R
    _draw_oblong_h(ax, oval["cx"], oval["cz"], oval_total_x, POCKET_DIAM,
                   fill=False, edgecolor="tab:green", linewidth=2)

    # Slider slots (horizontal)
    for cx, cz in sliders:
        _draw_oblong_h(ax, cx, cz, SLIDER_TOTAL_LEN, SLIDER_WIDTH,
                       fill=False, edgecolor="tab:orange", linewidth=1.5)

    # Holes A and B
    for i, (cx, cz) in enumerate(holes_ab):
        ax.add_patch(plt.Circle((cx, cz), M5_HOLE_DIAM / 2,
                                fill=False, color="tab:red", lw=1.5))
        ax.text(cx, cz, f"{'AB'[i]}", ha="center", va="center",
                fontsize=7, color="tab:red", fontweight="bold")

    ax.set_aspect("equal")
    ax.grid(True, alpha=0.3, lw=0.5)
    ax.set_xlabel("X (mm)")
    ax.set_ylabel("Z (mm)")
    ax.set_title(
        f"{NAME}  —  M3 (blue), merged oval (green), "
        f"slider slots (orange), holes A/B (red)"
    )
    fig.tight_layout()
    fig.savefig(out_png, dpi=150, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    silhouette = load_silhouette()
    y_holes = load_y_holes()
    m3      = m3_centres(y_holes)
    pockets = pocket_centres(y_holes)

    plate = build(silhouette, m3, pockets)

    step_path = HERE / f"{NAME}.step"
    stl_path  = HERE / f"{NAME}.stl"
    plan_path = HERE / f"{NAME}_plan.png"
    export_step(plate.part, str(step_path))
    export_stl(plate.part, str(stl_path))
    render_plan(silhouette, m3, pockets, plan_path)
    print(f"wrote {step_path.name}")
    print(f"wrote {stl_path.name}")
    print(f"wrote {plan_path.name}")


# -- YAML parameter override (optional) --------------------------------------
# If a sibling "<thisfile>.params.yaml" exists, its UPPER_CASE keys replace the
# module constants above, so the geometry can be tuned without editing code.
# The shipped params.yaml equals these defaults (no behaviour change until you
# edit it). Guarded so a missing PyYAML / file can never break the build.
def _apply_yaml_param_overrides():
    try:
        import yaml
        from pathlib import Path
        pf = Path(__file__).with_suffix(".params.yaml")
        if not pf.exists():
            return
        data = yaml.safe_load(pf.read_text()) or {}
        g = globals()
        applied = []
        for k, v in data.items():
            if isinstance(k, str) and k.isupper() and k in g:
                g[k] = v
                applied.append(k)
        if applied:
            print(f"[params] {pf.name}: overrode {len(applied)} constant(s)")
    except Exception as exc:
        print(f"[params] YAML override skipped ({exc})")


_apply_yaml_param_overrides()


if __name__ == "__main__":
    main()
