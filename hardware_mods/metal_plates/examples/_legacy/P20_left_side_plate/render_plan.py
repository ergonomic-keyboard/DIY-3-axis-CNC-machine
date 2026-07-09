"""Render a 2D plan view of the metal plate showing outline + holes."""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.patches as patches
import matplotlib.pyplot as plt

from side_plate_left import OUTLINE, load_holes, metal_holes  # type: ignore

HERE = Path(__file__).resolve().parent

holes = metal_holes(load_holes())

fig, ax = plt.subplots(figsize=(7, 12))
poly = patches.Polygon(OUTLINE, closed=True, fill=True, facecolor="#cfd8dc", edgecolor="#263238", linewidth=1.5)
ax.add_patch(poly)
for h in holes:
    ax.add_patch(patches.Circle((h["cx"], h["cz"]), h["d"] / 2, facecolor="white", edgecolor="#b71c1c", linewidth=1))
    ax.annotate(f"{h['d']:.1f}", xy=(h["cx"], h["cz"]), fontsize=6, ha="center", va="center", color="#b71c1c")

ax.set_aspect("equal")
ax.set_xlim(70, 200)
ax.set_ylim(-15, 200)
ax.set_xlabel("X (mm)")
ax.set_ylabel("Z (mm)")
ax.set_title("Left side plate — metal version\n(plan view, hole diameters in mm)")
ax.grid(alpha=0.2)
fig.tight_layout()
out = HERE / "side_plate_left_metal_plan.png"
fig.savefig(out, dpi=150)
print(f"Wrote {out}")
