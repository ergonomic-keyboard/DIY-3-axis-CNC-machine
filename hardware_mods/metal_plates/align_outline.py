"""align_outline.py — interactive polygon editor for the metal plate outline.

Opens the same overlay you saw in build_model.py (plastic STL in red,
traced metal polygon in blue) and lets you:

  * **mark edges horizontal / vertical** so the next model regeneration
    snaps them to perfect H/V (mean Z / mean X of their endpoints);
  * **nudge edges perpendicularly** with the arrow keys so they line up
    with the plastic silhouette underneath.

Edits live in a separate ``<...>_polygon_edited.json`` next to the raw
trace. build_model.py prefers ``_edited.json`` if present, so you can
re-run the model after every save and see the change immediately. The
original trace stays untouched as ground truth.

Reads:
  <example>/4_outline/<...>_polygon.json           (raw trace, stage 5)
  <example>/2_flattened_image/<...>_rect.json      (px→mm calibration)
  <example>/2_flattened_image/holes_from_stl.json  (plastic STL hole cache)

Writes:
  <example>/4_outline/<...>_polygon_edited.json    (mm coords + constraints)

Controls (also shown as a persistent banner):
  left-click on an edge   select that edge
  H / V / F               mark selected edge horizontal / vertical / free
                            (immediate snap to mean coord on H or V)
  ← → ↑ ↓                 nudge selected edge 0.5 mm perpendicular
  Shift + ← → ↑ ↓         nudge by 0.1 mm (fine)
  R                       reset to the raw trace (clears all edits)
  S                       save now
  D                       save and exit
  Q / window-close        discard unsaved edits and exit

Adjacent edges stretch (their other endpoint stays fixed) to keep the
polygon closed.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import matplotlib

if not os.environ.get("MPLBACKEND"):
    for backend in ("QtAgg", "TkAgg", "WebAgg"):
        try:
            matplotlib.use(backend, force=True)
            break
        except Exception:
            continue

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.collections import PolyCollection  # noqa: E402
from stl import mesh as stl_mesh  # noqa: E402


CONSTRAINT_COLORS = {
    "free": "tab:blue",
    "horizontal": "tab:cyan",
    "vertical": "tab:purple",
}


# =============================================================================
# Inputs
# =============================================================================
def _single_file(stage_dir: Path, pattern: str, what: str) -> Path:
    if not stage_dir.is_dir():
        raise SystemExit(f"missing stage folder: {stage_dir}")
    hits = sorted(stage_dir.glob(pattern))
    if not hits:
        raise SystemExit(
            f"no {what} in {stage_dir} (pattern {pattern}) — run earlier stages first."
        )
    if len(hits) > 1:
        listing = "\n  ".join(p.name for p in hits)
        raise SystemExit(
            f"{len(hits)} {what} candidates in {stage_dir}; ambiguous:\n  {listing}"
        )
    return hits[0]


def px_to_mm(rect: dict):
    scale = float(rect["scale_px_per_mm"])
    x_min = float(rect["canvas_real_bounds_mm"]["x_min"])
    z_max = float(rect["canvas_real_bounds_mm"]["z_max"])

    def to_mm(px, py):
        return (x_min + px / scale, z_max - py / scale)

    return to_mm


def load_initial(example: Path) -> dict:
    stage2 = example / "2_flattened_image"
    stage4 = example / "4_outline"
    rect_json = _single_file(stage2, "*_rect.json", "rectification metadata")
    holes_cache = stage2 / "holes_from_stl.json"
    if not holes_cache.exists():
        raise SystemExit(f"missing {holes_cache} — re-run rectify.py.")

    # Prefer an existing edit if one is already there.
    edited = sorted(stage4.glob("*_polygon_edited.json"))
    raw = sorted(stage4.glob("*_polygon.json"))
    raw = [p for p in raw if not p.name.endswith("_edited.json")]
    if not raw:
        raise SystemExit(f"no polygon trace in {stage4} — run trace_polygon first.")
    if len(raw) > 1:
        raise SystemExit(
            f"multiple raw polygon traces in {stage4}; remove the stale ones."
        )
    raw_json = raw[0]

    rect = json.loads(rect_json.read_text())
    raw_poly = json.loads(raw_json.read_text())
    to_mm = px_to_mm(rect)
    raw_mm = [to_mm(x, y) for x, y in raw_poly["vertices_px"]]
    n = len(raw_mm)

    constraints = ["free"] * n  # one per EDGE (edge i = vertex i -> vertex i+1)
    verts = list(raw_mm)
    edited_json: Path | None = None

    if edited:
        if len(edited) > 1:
            raise SystemExit(
                f"multiple edited polygons in {stage4}; remove the stale ones."
            )
        edited_json = edited[0]
        prev = json.loads(edited_json.read_text())
        try:
            ev = prev["vertices_xz_mm"]
            ec = prev["edge_constraints"]
            if len(ev) == n and len(ec) == n:
                verts = [(float(x), float(z)) for x, z in ev]
                constraints = list(ec)
                print(f"loaded existing edit from {edited_json.name}")
            else:
                print(f"warning: {edited_json.name} vertex count "
                      f"({len(ev)}/{len(ec)}) mismatches raw ({n}); discarding edit.")
        except (KeyError, TypeError) as e:
            print(f"warning: could not read {edited_json.name} ({e}); ignoring.")

    holes_data = json.loads(holes_cache.read_text())
    return dict(
        rect=rect,
        rect_json=rect_json,
        raw_poly_json=raw_json,
        raw_vertices_mm=raw_mm,
        vertices=verts,
        constraints=constraints,
        edited_json_path=edited_json
        or stage4 / f"{raw_json.stem}_edited.json",
        holes_data=holes_data,
        stl_path=Path(rect["stl"]),
    )


# =============================================================================
# Constraint application
# =============================================================================
def apply_constraint(verts: list[tuple[float, float]], i: int,
                     constraint: str, n: int) -> list[tuple[float, float]]:
    """Snap edge i (i → i+1 mod n) endpoints per its constraint."""
    j = (i + 1) % n
    x1, z1 = verts[i]
    x2, z2 = verts[j]
    if constraint == "horizontal":
        z_new = 0.5 * (z1 + z2)
        verts[i] = (x1, z_new)
        verts[j] = (x2, z_new)
    elif constraint == "vertical":
        x_new = 0.5 * (x1 + x2)
        verts[i] = (x_new, z1)
        verts[j] = (x_new, z2)
    return verts


def apply_all_constraints(
    verts: list[tuple[float, float]],
    constraints: list[str],
) -> list[tuple[float, float]]:
    """Apply every constraint once (left-to-right). Used at save time."""
    out = list(verts)
    n = len(out)
    for i, c in enumerate(constraints):
        if c != "free":
            apply_constraint(out, i, c, n)
    return out


# =============================================================================
# Edge picking
# =============================================================================
def nearest_edge_to_point(
    px: float, pz: float,
    verts: list[tuple[float, float]],
) -> int:
    """Return the edge index whose segment is closest to (px, pz) in mm."""
    n = len(verts)
    best_d = float("inf")
    best_i = 0
    for i in range(n):
        x1, z1 = verts[i]
        x2, z2 = verts[(i + 1) % n]
        # Distance from point to segment.
        dx, dz = x2 - x1, z2 - z1
        L2 = dx * dx + dz * dz
        if L2 < 1e-9:
            d = float(np.hypot(px - x1, pz - z1))
        else:
            t = max(0.0, min(1.0, ((px - x1) * dx + (pz - z1) * dz) / L2))
            cx = x1 + t * dx
            cz = z1 + t * dz
            d = float(np.hypot(px - cx, pz - cz))
        if d < best_d:
            best_d = d
            best_i = i
    return best_i


def edge_perp(verts: list[tuple[float, float]], i: int) -> tuple[float, float]:
    """Unit vector perpendicular to edge i (pointing 'outward' isn't enforced)."""
    n = len(verts)
    x1, z1 = verts[i]
    x2, z2 = verts[(i + 1) % n]
    dx, dz = x2 - x1, z2 - z1
    L = max(np.hypot(dx, dz), 1e-9)
    # Perpendicular: (-dz, dx) / L (rotate +90°).
    return (-dz / L, dx / L)


# =============================================================================
# Main editor
# =============================================================================
def run(example: Path) -> None:
    example = example.resolve()
    if not example.is_dir():
        raise SystemExit(f"example folder does not exist: {example}")

    state = load_initial(example)
    rect = state["rect"]
    verts: list[tuple[float, float]] = state["vertices"]
    constraints: list[str] = state["constraints"]
    raw_mm = state["raw_vertices_mm"]
    stl_path: Path = state["stl_path"]
    n = len(verts)

    # Y-axis hole projection (for the white circles in the overlay)
    y_holes = [h for h in state["holes_data"]["holes"] if h["axis"] == "Y"]

    # Plastic Y-face triangles
    stl_proj = None
    if stl_path.exists():
        m = stl_mesh.Mesh.from_file(str(stl_path))
        tris = m.vectors
        norms = m.normals.copy()
        nlen = np.linalg.norm(norms, axis=1, keepdims=True)
        n_unit = np.where(nlen > 1e-12, norms / nlen, 0.0)
        y_face_mask = np.abs(n_unit[:, 1]) > 0.95
        if y_face_mask.any():
            stl_proj = tris[y_face_mask][:, :, [0, 2]]
    else:
        print(f"note: STL not found at {stl_path}; overlay will be skipped.")

    selected: list[int] = [0]
    saved_at_least_once = [False]
    dirty = [False]  # have edits been made since last save / since load?

    fig, ax = plt.subplots(figsize=(10, 12))
    try:
        fig.canvas.manager.set_window_title("Align outline — H/V constraints + nudging")
    except Exception:
        pass

    banner = ax.text(
        0.5, 1.02,
        "click an edge to select  |  H/V/F = horizontal/vertical/free  |  "
        "←→↑↓ nudge (Shift = fine)  |  R reset  S save  D save+exit",
        transform=ax.transAxes, ha="center", va="bottom",
        color="white", fontsize=10,
        bbox=dict(boxstyle="round,pad=0.4", fc="black", ec="white", alpha=0.85),
        zorder=100,
    )
    status = ax.text(
        0.99, 1.02, "",
        transform=ax.transAxes, ha="right", va="bottom",
        color="white", fontsize=10,
        bbox=dict(boxstyle="round,pad=0.3", fc="black", ec="white", alpha=0.85),
        zorder=100,
    )

    def repaint():
        ax.clear()
        # Plastic silhouette
        if stl_proj is not None:
            ax.add_collection(PolyCollection(
                stl_proj, facecolor="tab:red", edgecolor="darkred",
                lw=0.1, alpha=0.18,
            ))
        # Hole circles
        for h in y_holes:
            ax.add_patch(plt.Circle(
                (h["cx"], h["cz"]), h["r"], fill=False,
                edgecolor="dimgray", lw=0.6, alpha=0.6,
            ))
        # Polygon edges (colour by constraint)
        for i in range(n):
            x1, z1 = verts[i]
            x2, z2 = verts[(i + 1) % n]
            colour = CONSTRAINT_COLORS[constraints[i]]
            lw = 4.0 if i == selected[0] else 1.6
            ax.plot([x1, x2], [z1, z2], color=colour, lw=lw, solid_capstyle="round",
                    zorder=6 if i == selected[0] else 4)
        # Vertices
        vx = [v[0] for v in verts]
        vz = [v[1] for v in verts]
        ax.plot(vx, vz, "o", color="yellow", ms=4, mec="black", mew=0.5, zorder=7)
        # Selected-edge midpoint label
        i = selected[0]
        x1, z1 = verts[i]
        x2, z2 = verts[(i + 1) % n]
        ax.annotate(
            f"E{i}", ((x1 + x2) / 2, (z1 + z2) / 2),
            color="black", fontsize=11, fontweight="bold",
            ha="center", va="center",
            bbox=dict(boxstyle="round,pad=0.3", fc="yellow", ec="black"),
            zorder=8,
        )
        # Limits
        xs = vx + ([stl_proj[:, :, 0].min(), stl_proj[:, :, 0].max()]
                   if stl_proj is not None else [])
        zs = vz + ([stl_proj[:, :, 1].min(), stl_proj[:, :, 1].max()]
                   if stl_proj is not None else [])
        ax.set_xlim(min(xs) - 8, max(xs) + 8)
        ax.set_ylim(min(zs) - 8, max(zs) + 8)
        ax.set_aspect("equal")
        ax.set_xlabel("X (mm)")
        ax.set_ylabel("Z (mm)")
        ax.grid(alpha=0.25, lw=0.5)
        # Re-attach banner / status
        ax.add_artist(banner)
        ax.add_artist(status)
        status.set_text(
            f"E{i}  {constraints[i]:>10}   {'•dirty' if dirty[0] else 'clean'}"
        )
        fig.canvas.draw_idle()

    def shift_selected_edge(dx: float, dz: float):
        i = selected[0]
        j = (i + 1) % n
        c = constraints[i]
        if c == "horizontal":
            # Allowed: only Z component.
            verts[i] = (verts[i][0], verts[i][1] + dz)
            verts[j] = (verts[j][0], verts[j][1] + dz)
        elif c == "vertical":
            # Allowed: only X component.
            verts[i] = (verts[i][0] + dx, verts[i][1])
            verts[j] = (verts[j][0] + dx, verts[j][1])
        else:
            # Perpendicular shift.
            px, pz = edge_perp(verts, i)
            # Take the user's (dx, dz) and project onto the perp direction:
            mag = dx * px + dz * pz
            verts[i] = (verts[i][0] + mag * px, verts[i][1] + mag * pz)
            verts[j] = (verts[j][0] + mag * px, verts[j][1] + mag * pz)
        dirty[0] = True

    def set_constraint(c: str):
        i = selected[0]
        constraints[i] = c
        if c in ("horizontal", "vertical"):
            apply_constraint(verts, i, c, n)
        dirty[0] = True

    def save():
        snapped = apply_all_constraints(verts, constraints)
        payload = {
            "source_raw": str(state["raw_poly_json"]),
            "coords": "mm",
            "closed": True,
            "vertices_xz_mm": [[float(x), float(z)] for x, z in snapped],
            "edge_constraints": list(constraints),
        }
        state["edited_json_path"].write_text(json.dumps(payload, indent=2))
        saved_at_least_once[0] = True
        dirty[0] = False
        print(f"wrote {state['edited_json_path']}")

    def reset():
        nonlocal_verts = list(raw_mm)
        verts[:] = nonlocal_verts
        for k in range(n):
            constraints[k] = "free"
        dirty[0] = True
        print("reset to raw trace.")

    def on_click(e):
        if e.inaxes is not ax or e.button != 1 or e.xdata is None:
            return
        selected[0] = nearest_edge_to_point(e.xdata, e.ydata, verts)
        repaint()

    def on_key(e):
        if e.key is None:
            return
        k = e.key.lower()
        fine = "shift+" in e.key
        step = 0.1 if fine else 0.5
        if k in ("h", "shift+h"):
            set_constraint("horizontal")
            repaint()
        elif k in ("v", "shift+v"):
            set_constraint("vertical")
            repaint()
        elif k in ("f", "shift+f"):
            set_constraint("free")
            repaint()
        elif e.key in ("left", "shift+left"):
            shift_selected_edge(-step, 0); repaint()
        elif e.key in ("right", "shift+right"):
            shift_selected_edge(+step, 0); repaint()
        elif e.key in ("up", "shift+up"):
            shift_selected_edge(0, +step); repaint()
        elif e.key in ("down", "shift+down"):
            shift_selected_edge(0, -step); repaint()
        elif k in ("r", "shift+r"):
            reset(); repaint()
        elif k in ("s", "shift+s"):
            save(); repaint()
        elif k in ("d", "shift+d"):
            save(); plt.close(fig)
        elif k == "q":
            plt.close(fig)

    fig.canvas.mpl_connect("button_press_event", on_click)
    fig.canvas.mpl_connect("key_press_event", on_key)
    repaint()
    # Maximise where possible.
    mgr = fig.canvas.manager
    for fn in (
        lambda: mgr.window.showMaximized(),
        lambda: mgr.window.state("zoomed"),
        lambda: mgr.full_screen_toggle(),
    ):
        try:
            fn()
            break
        except Exception:
            continue
    plt.show()

    if dirty[0] and not saved_at_least_once[0]:
        print("exited with unsaved edits — discarded.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--example", type=Path, required=True,
                    help="example folder (the one containing the 0_..5_ stage dirs)")
    args = ap.parse_args()
    run(args.example)


if __name__ == "__main__":
    main()
