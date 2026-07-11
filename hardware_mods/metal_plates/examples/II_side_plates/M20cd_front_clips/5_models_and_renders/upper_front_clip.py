"""Metal LEFT_PLATE_UPPER_FRONT_CLIP.

Aluminium replacement for plastic LEFT_PLATE_UPPER_FRONT_CLIP.stl. Same
construction as the lower clip but longer (47.8 mm along Z) and with the
neck slightly asymmetric, since the original plastic top edge has a
chamfer toward +Z+X.

Run from inside nix-shell:
  nix-shell hardware_mods/metal_plates/shell.nix --run \\
    "python hardware_mods/metal_plates/examples/side_movement/P20_left_side_plate_p3of3/5_models_and_renders/upper_front_clip.py"
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from build123d import export_step, export_stl  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _front_clip_common import build_front_clip  # noqa: E402

NAME = "upper_front_clip"

# Plastic STL bbox: 167..190, 10..30, 142.22..190
X_MIN, X_MAX = 167.0, 190.0
Y_MIN, Y_MAX = 10.0, 30.0
Z_MIN, Z_MAX = 142.222, 190.0

# Neck region — from Y=20 slice, neck spans roughly Z=160..180 with the
# body recessed to X=180..190.
NECK_Z_MIN, NECK_Z_MAX = 160.0, 180.0
NECK_X_START = 180.0

BOLT_DIAM = 8.4   # M8 clearance
BOLT_CZ = (Z_MIN + Z_MAX) / 2


def render_plan(out_png: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12, 6))

    ax = axes[0]
    ax.add_patch(plt.Rectangle(
        (Z_MIN, X_MIN), Z_MAX - Z_MIN, X_MAX - X_MIN,
        fill=False, edgecolor="black", lw=2,
    ))
    ax.add_patch(plt.Rectangle(
        (NECK_Z_MIN, X_MIN), NECK_Z_MAX - NECK_Z_MIN, NECK_X_START - X_MIN,
        facecolor="lightblue", edgecolor="tab:blue", lw=1, alpha=0.6,
    ))
    ax.add_patch(plt.Circle(
        (BOLT_CZ, (X_MIN + X_MAX) / 2),
        BOLT_DIAM / 2, fill=False, color="tab:red", lw=1.5,
    ))
    ax.set_aspect("equal")
    ax.set_xlim(Z_MIN - 5, Z_MAX + 5)
    ax.set_ylim(X_MIN - 5, X_MAX + 5)
    ax.set_xlabel("Z (mm) — bar axis")
    ax.set_ylabel("X (mm)")
    ax.set_title("Side view (Y midplane)")
    ax.grid(True, alpha=0.3)

    ax = axes[1]
    ax.add_patch(plt.Rectangle(
        (Y_MIN, X_MIN), Y_MAX - Y_MIN, X_MAX - X_MIN,
        fill=False, edgecolor="black", lw=2,
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
    ax.set_title("End view (bolt axis through page)")
    ax.grid(True, alpha=0.3)

    fig.suptitle(f"{NAME} — envelope (black), neck cut (blue), M8 bolt (red)")
    fig.tight_layout()
    fig.savefig(out_png, dpi=150, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    part = build_front_clip(
        x_min=X_MIN, x_max=X_MAX,
        y_min=Y_MIN, y_max=Y_MAX,
        z_min=Z_MIN, z_max=Z_MAX,
        neck_z_min=NECK_Z_MIN, neck_z_max=NECK_Z_MAX,
        neck_x_start=NECK_X_START,
        bolt_diam=BOLT_DIAM, bolt_cz=BOLT_CZ,
    )
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
