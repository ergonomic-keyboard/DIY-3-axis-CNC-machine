"""Metal LEFT_PLATE_BACK_CLIP (used for both lower- and upper-back bar clips).

Aluminium replacement for plastic LEFT_PLATE_BACK_CLIP.stl. Geometry from
the plastic STL bbox (15.4 x 20 x 72.5 mm), the mid-Z cross-section (a
20 x 15.4 rectangle with a 13 x 5.4 mm notch on the +X side that hooks
onto the steel bar), and a single M8 bolt centred on the bolt midplane.

Coordinate system matches the plastic STL: bar axis along +Z, plate face
contact along -X, bolt axis along +X. Outer envelope preserved so it
drops into the assembly at the same world position.

Run from inside nix-shell:
  nix-shell hardware_mods/metal_plates/shell.nix --run \\
    "python hardware_mods/metal_plates/examples/side_movement/P20_left_side_plate_p2of3/5_models_and_renders/back_clip.py"
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

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from build123d import (  # noqa: E402
    Axis,
    Box,
    Cylinder,
    Location,
    Mode,
    Part,
    Plane,
    export_step,
    export_stl,
)

HERE = Path(__file__).resolve().parent
NAME = "back_clip"

# ---------------------------------------------------------------------------
# Parameters — outer envelope from plastic STL
# ---------------------------------------------------------------------------
X_MIN, X_MAX = 54.0, 69.385      # plate-facing -> outer face
Y_MIN, Y_MAX = 10.0, 30.0
Z_MIN, Z_MAX = 18.034, 90.514

# Bar-engagement notch on the +X face (matches the Z-midplane slice corner
# notch: Y from 13 to 26, X from 64 to 69.4, depth 5.4 mm).
NOTCH_Y_MIN, NOTCH_Y_MAX = 13.0, 26.0
NOTCH_X_START = 64.0             # back wall stays from NOTCH_X_START to X_MAX

# Bolt — single M8 clearance through the bolt midplane in +X direction.
BOLT_DIAM = 8.4


def build() -> Part:
    body = Box(
        X_MAX - X_MIN,
        Y_MAX - Y_MIN,
        Z_MAX - Z_MIN,
    ).locate(Location((
        (X_MIN + X_MAX) / 2,
        (Y_MIN + Y_MAX) / 2,
        (Z_MIN + Z_MAX) / 2,
    )))

    notch = Box(
        X_MAX - NOTCH_X_START,
        NOTCH_Y_MAX - NOTCH_Y_MIN,
        Z_MAX - Z_MIN,
    ).locate(Location((
        (NOTCH_X_START + X_MAX) / 2,
        (NOTCH_Y_MIN + NOTCH_Y_MAX) / 2,
        (Z_MIN + Z_MAX) / 2,
    )))

    # Bolt hole through the body in +X direction (axis along X).
    bolt = Cylinder(
        radius=BOLT_DIAM / 2,
        height=(X_MAX - X_MIN) * 1.5,
        rotation=(0, 90, 0),
    ).locate(Location((
        (X_MIN + X_MAX) / 2,
        (Y_MIN + Y_MAX) / 2,
        (Z_MIN + Z_MAX) / 2,
    )))

    return body - notch - bolt


def render_plan(out_png: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12, 6))

    # Top view (looking -Y): Z horizontal, X vertical
    ax = axes[0]
    ax.add_patch(plt.Rectangle(
        (Z_MIN, X_MIN), Z_MAX - Z_MIN, X_MAX - X_MIN,
        fill=False, edgecolor="black", lw=2,
    ))
    ax.add_patch(plt.Rectangle(
        (Z_MIN, NOTCH_X_START), Z_MAX - Z_MIN, X_MAX - NOTCH_X_START,
        fill=True, facecolor="lightblue", edgecolor="tab:blue", lw=1,
        alpha=0.6,
    ))
    ax.add_patch(plt.Circle(
        ((Z_MIN + Z_MAX) / 2, (X_MIN + X_MAX) / 2),
        BOLT_DIAM / 2, fill=False, color="tab:red", lw=1.5,
    ))
    ax.set_aspect("equal")
    ax.set_xlim(Z_MIN - 5, Z_MAX + 5)
    ax.set_ylim(X_MIN - 5, X_MAX + 5)
    ax.set_xlabel("Z (mm) — bar axis")
    ax.set_ylabel("X (mm) — away from plate")
    ax.set_title("Top view")
    ax.grid(True, alpha=0.3)

    # End view (looking -Z): Y horizontal, X vertical
    ax = axes[1]
    ax.add_patch(plt.Rectangle(
        (Y_MIN, X_MIN), Y_MAX - Y_MIN, X_MAX - X_MIN,
        fill=False, edgecolor="black", lw=2,
    ))
    ax.add_patch(plt.Rectangle(
        (NOTCH_Y_MIN, NOTCH_X_START),
        NOTCH_Y_MAX - NOTCH_Y_MIN, X_MAX - NOTCH_X_START,
        fill=True, facecolor="lightblue", edgecolor="tab:blue", lw=1,
        alpha=0.6,
    ))
    ax.add_patch(plt.Circle(
        ((Y_MIN + Y_MAX) / 2, (X_MIN + X_MAX) / 2),
        BOLT_DIAM / 2, fill=False, color="tab:red", lw=1.5,
    ))
    ax.set_aspect("equal")
    ax.set_xlim(Y_MIN - 5, Y_MAX + 5)
    ax.set_ylim(X_MIN - 5, X_MAX + 5)
    ax.set_xlabel("Y (mm)")
    ax.set_ylabel("X (mm)")
    ax.set_title("End view")
    ax.grid(True, alpha=0.3)

    fig.suptitle(
        f"{NAME} — envelope (black), bar notch (blue), M8 bolt (red)")
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
