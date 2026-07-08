"""render_m36a_plan.py — regenerate docs/images/metal/components/M36a_plan.png
with the C.1-corrected nut orientation.

The upstream 4_outline polygon.json for engine_holder_vertical_plate_p1of2 was
removed in commit 7e2a68a, so we cannot re-run build_model.py end-to-end.  This
script rebuilds only the plan-view PNG from the still-present hole data
(2_flattened_image/holes_from_stl.json) plus a plate outline hand-derived from
the STL bounding rectangle plus the four tab extensions.

Produces the same image build_model.py's ``render_plan`` would produce, but
with each captive M5 nut drawn as a side-profile rectangle instead of the
plate-normal hex face — this is what the requirement C.1 asks for.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / ".venv/lib/python3.13/site-packages"))

import matplotlib          # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt   # noqa: E402


PLATE = (REPO / "hardware_mods/metal_plates/examples/mid_vertical_movement"
              / "engine_holder_vertical_plate_p1of2")
HOLES_JSON = PLATE / "2_flattened_image/holes_from_stl.json"
OUT_PNG    = REPO / "docs/images/metal/components/M36a_plan.png"


# ── plate outline (local plate-frame X, Z mm) ────────────────────────────────
# 147.5 mm W × 218.3 mm H, with two top tabs and two bottom tabs.  Plate is
# oriented so the diagonal chamfer sits at the RIGHT side (per the current
# M36a_plan.png).  Coordinates copied from starting_point_rect.json (plate
# body + observed tab positions).
PLATE_X_MIN = 352.19
PLATE_X_MAX = 505.61
PLATE_Z_MIN =  -8.0     # below the tab bottoms
PLATE_Z_MAX = 215.0
TAB_HALF_W  = 8.0       # tab is ~16 mm wide
TAB_H       = 12.0      # tab sticks out this far past the plate edge
CHAMFER_X0  = 462.0     # start of the diagonal chamfer on the right side
CHAMFER_Z0  = 100.0     # z where the chamfer meets the top edge

# Four tab centres (X, Z) at the plate top and bottom.
TAB_TL = (372.0, PLATE_Z_MAX)
TAB_TR = (437.0, PLATE_Z_MAX)
TAB_BL = (372.0, PLATE_Z_MIN)
TAB_BR = (437.0, PLATE_Z_MIN)

# Nut centres — inside each tab, one nut thickness in from the outer tab edge.
NUT_THK = 4.0    # M5 hex-nut thickness (DIN 934)
NUT_AF  = 8.0    # M5 across-flats

# Top nuts sit inside the top tabs, head is ABOVE them (bolt enters from
# above → −Z through the tab).  So draw the nut with head-side = +Z direction
# ⇒ orientation label "z_down" (bolt travelling −Z into the plate).
NUT_TL = (TAB_TL[0], PLATE_Z_MAX + TAB_H/2)
NUT_TR = (TAB_TR[0], PLATE_Z_MAX + TAB_H/2)

# Bottom nuts sit inside the bottom tabs, bolt enters from BELOW (+Z).
NUT_BL = (TAB_BL[0], PLATE_Z_MIN - TAB_H/2)
NUT_BR = (TAB_BR[0], PLATE_Z_MIN - TAB_H/2)


def _outline() -> list[tuple[float, float]]:
    """Rectangular plate with four tabs and one chamfer (approximation)."""
    x0, x1, z0, z1 = PLATE_X_MIN, PLATE_X_MAX, PLATE_Z_MIN, PLATE_Z_MAX

    pts: list[tuple[float, float]] = []
    # Start at bottom-left corner, walk counter-clockwise
    pts.append((x0, z0))

    # Bottom edge with two tabs (BL, BR)
    for cx, cz in [TAB_BL, TAB_BR]:
        pts.append((cx - TAB_HALF_W, z0))
        pts.append((cx - TAB_HALF_W, z0 - TAB_H))
        pts.append((cx + TAB_HALF_W, z0 - TAB_H))
        pts.append((cx + TAB_HALF_W, z0))
    pts.append((x1, z0))

    # Right edge with chamfer at top-right corner
    pts.append((x1, CHAMFER_Z0))
    pts.append((CHAMFER_X0, z1))

    # Top edge with two tabs (TR, TL) — walking leftwards
    for cx, cz in [TAB_TR, TAB_TL]:
        pts.append((cx + TAB_HALF_W, z1))
        pts.append((cx + TAB_HALF_W, z1 + TAB_H))
        pts.append((cx - TAB_HALF_W, z1 + TAB_H))
        pts.append((cx - TAB_HALF_W, z1))
    pts.append((x0, z1))

    return pts


def _draw_nut(ax, cx, cz, ori: str):
    """Same rectangle/hex logic as build_model._draw_m5_nuts but self-contained.

    ``ori`` conventions used here match the user-visible arrow direction:
        z_up   → bolt shaft points +Z (arrow ↑, "bolt points upwards")
        z_down → bolt shaft points −Z (arrow ↓, "bolt points downwards")
    """
    w, thk = NUT_AF / 2, NUT_THK
    edge = dict(color="red", lw=1.4, zorder=10)
    if ori not in ("z_up", "z_down"):
        raise ValueError(ori)
    # Rectangle (nut side-profile) — same in both orientations, size af × thk.
    z0, z1 = cz - thk/2, cz + thk/2
    xs = [cx - w, cx + w, cx + w, cx - w, cx - w]
    zs = [z0,     z0,     z1,     z1,     z0]
    ax.plot(xs, zs, **edge)
    # Arrow — head end is the direction the bolt SHAFT points.
    tail_len = thk * 1.8
    if ori == "z_up":
        tail_z, head_z = cz - tail_len/2, cz + tail_len/2
    else:
        tail_z, head_z = cz + tail_len/2, cz - tail_len/2
    ax.annotate("", xy=(cx, head_z),
                xytext=(cx, tail_z),
                arrowprops=dict(arrowstyle="->", color="red", lw=1.4),
                zorder=10)
    ax.plot([cx], [cz], "+", color="red", ms=6, zorder=10)


def main() -> None:
    holes = json.loads(HOLES_JSON.read_text())["holes"]
    y_holes = [h for h in holes if h["axis"] == "Y"]

    outline = _outline()

    fig, ax = plt.subplots(figsize=(8, 10))
    xs = [p[0] for p in outline] + [outline[0][0]]
    zs = [p[1] for p in outline] + [outline[0][1]]
    ax.fill(xs, zs, facecolor="lightgray", edgecolor="black", lw=1.2, alpha=0.7)

    for h in y_holes:
        ax.add_patch(
            plt.Circle((h["cx"], h["cz"]), h["r"], fill=True,
                       facecolor="white", edgecolor="black", lw=0.8)
        )

    # C.1 fix — per the requirement, "top 2 bolts should point upwards" and
    # "bottom 2 should point downwards".  So the shaft direction on the top
    # tabs is +Z (label z_up = arrow ↑) and on the bottom tabs is −Z
    # (label z_down = arrow ↓).  Nut axis is vertical either way — the plan
    # view is a side-profile rectangle, not the plate-normal hexagon.
    _draw_nut(ax, *NUT_TL, "z_up")
    _draw_nut(ax, *NUT_TR, "z_up")
    _draw_nut(ax, *NUT_BL, "z_down")
    _draw_nut(ax, *NUT_BR, "z_down")

    bbx0, bbx1 = min(xs), max(xs)
    bbz0, bbz1 = min(zs), max(zs)
    ax.set_xlim(bbx0 - 10, bbx1 + 10)
    ax.set_ylim(bbz0 - 10, bbz1 + 10)
    ax.set_aspect("equal")
    ax.set_xlabel("X (mm)")
    ax.set_ylabel("Z (mm)")
    ax.grid(alpha=0.3, lw=0.5)
    ax.set_title(
        f"starting_point_rect (M36.a) — C.1 corrected nut orientation\n"
        f"top bolts ↑ (rotated 90° from plate-normal),   "
        f"bottom bolts ↓\n"
        f"{bbx1 - bbx0:.1f} mm W  ×  {bbz1 - bbz0:.1f} mm H  "
        f"({len(y_holes)} Y-axis holes)"
    )
    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {OUT_PNG}")


if __name__ == "__main__":
    main()
