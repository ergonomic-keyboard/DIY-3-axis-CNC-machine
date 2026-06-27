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
  H / V / N               mark selected edge horizontal / vertical / none
                            (immediate snap to mean coord on H or V)
  1 / 2                   snap selected edge onto the highlighted plastic
                            candidate line (perpendicular shift, length
                            preserved)
  F                       cycle to the next pair of candidate plastic lines
  M                       manual snap mode — click any plastic boundary
                            segment to snap the selected edge onto it
  G                       enter group-edit mode for the selected edge's
                            group (creates a new group if it had none).
                            Members are highlighted in magenta. Click any
                            edge to toggle its membership. Press G again to
                            commit: all members spring to the longest
                            edge's position (longest decides H or V), and
                            from then on nudging any member moves them all
                            together. Esc cancels without committing.
  ← → ↑ ↓                 nudge selected edge 0.5 mm perpendicular
  Shift + ← → ↑ ↓         nudge by 0.1 mm (fine)
  U                       undo last edit (one step)
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
from collections import Counter
from pathlib import Path

import matplotlib

if not os.environ.get("MPLBACKEND"):
    for backend in ("QtAgg", "TkAgg", "WebAgg"):
        try:
            matplotlib.use(backend, force=True)
            break
        except Exception:
            continue

# Disable matplotlib's default keymap so our explicit single-key bindings
# (S = save to stage folder, R = reset, F = next candidate, G = group, …)
# don't double-trigger matplotlib's native actions like opening a save
# dialog in a random folder.
for _k in list(matplotlib.rcParams):
    if _k.startswith("keymap.") and _k != "keymap.quit":
        matplotlib.rcParams[_k] = []

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
    groups = [0] * n
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
                # Groups are optional; default to 0 for older files.
                eg = prev.get("edge_groups")
                if isinstance(eg, list) and len(eg) == n:
                    groups = [int(g) for g in eg]
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
        groups=groups,
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
    groups: list[int] | None = None,
) -> list[tuple[float, float]]:
    """Apply every constraint once (left-to-right). Used at save time.

    If ``groups`` is given, edges sharing a non-zero group number AND a
    consistent H/V constraint type are collapsed to a single shared coord
    (mean of their per-edge means).
    """
    out = list(verts)
    n = len(out)
    if groups is None:
        groups = [0] * n
    # 1) Apply per-edge H/V constraint (snap to own mean).
    for i, c in enumerate(constraints):
        if c != "free":
            apply_constraint(out, i, c, n)
    # 2) Collapse groups to a shared coord.
    by_group: dict[tuple[int, str], list[int]] = {}
    for i, (g, c) in enumerate(zip(groups, constraints)):
        if g == 0 or c == "free":
            continue
        by_group.setdefault((g, c), []).append(i)
    for (g, c), edges in by_group.items():
        # Per-edge coord (each edge is already collinear in its constrained axis).
        if c == "horizontal":
            shared = float(np.mean([out[i][1] for i in edges]))
            for i in edges:
                j = (i + 1) % n
                out[i] = (out[i][0], shared)
                out[j] = (out[j][0], shared)
        elif c == "vertical":
            shared = float(np.mean([out[i][0] for i in edges]))
            for i in edges:
                j = (i + 1) % n
                out[i] = (shared, out[i][1])
                out[j] = (shared, out[j][1])
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
# Plastic boundary + snap candidates
# =============================================================================
def plastic_boundary_segments(
    tris_xz: np.ndarray,
) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """Return (p1, p2) segments forming the outer boundary of the Y-face projection."""
    grid = 100  # quantize to 0.01 mm to spot shared edges
    edge_count: Counter = Counter()
    edge_points: dict = {}
    for tri in tris_xz:
        for k in range(3):
            a = tri[k]
            b = tri[(k + 1) % 3]
            ka = (int(round(a[0] * grid)), int(round(a[1] * grid)))
            kb = (int(round(b[0] * grid)), int(round(b[1] * grid)))
            ek = tuple(sorted([ka, kb]))
            edge_count[ek] += 1
            edge_points.setdefault(
                ek,
                ((float(a[0]), float(a[1])), (float(b[0]), float(b[1]))),
            )
    return [edge_points[k] for k, c in edge_count.items() if c == 1]


def snap_candidates(
    metal_edge: tuple[tuple[float, float], tuple[float, float]],
    plastic_segments: list[tuple[tuple[float, float], tuple[float, float]]],
    *,
    angle_tol_deg: float = 8.0,
    min_overlap_ratio: float = 0.1,
) -> list[dict]:
    """Return plastic segments parallel-ish to the metal edge, sorted by perp distance.

    Each candidate dict has:
        seg     : ((x1,z1), (x2,z2)) of the plastic boundary segment
        d_perp  : signed perpendicular distance from metal midpoint to plastic
                  segment's infinite line (used for sorting + the snap shift)
        target  : projected (x, z) on the plastic line, where the metal mid
                  would land after snap
    """
    (mx1, mz1), (mx2, mz2) = metal_edge
    mdx, mdz = mx2 - mx1, mz2 - mz1
    mL = float(np.hypot(mdx, mdz))
    if mL < 1e-9:
        return []
    udx, udz = mdx / mL, mdz / mL
    mid_x, mid_z = 0.5 * (mx1 + mx2), 0.5 * (mz1 + mz2)
    cos_tol = float(np.cos(np.deg2rad(angle_tol_deg)))

    out = []
    for (px1, pz1), (px2, pz2) in plastic_segments:
        pdx, pdz = px2 - px1, pz2 - pz1
        pL = float(np.hypot(pdx, pdz))
        if pL < 1e-9:
            continue
        # Parallelism (sign-agnostic): compare unit vectors via |dot|.
        upd_x, upd_z = pdx / pL, pdz / pL
        if abs(udx * upd_x + udz * upd_z) < cos_tol:
            continue
        # Length-overlap heuristic: project metal endpoints onto plastic line
        # and require some overlap with [0, pL].
        def proj_t(x, z):
            return ((x - px1) * pdx + (z - pz1) * pdz) / (pL * pL)

        t1 = proj_t(mx1, mz1) * pL
        t2 = proj_t(mx2, mz2) * pL
        lo, hi = min(t1, t2), max(t1, t2)
        overlap = max(0.0, min(hi, pL) - max(lo, 0.0))
        if overlap < min_overlap_ratio * min(mL, pL):
            continue
        # Perp distance from metal midpoint to plastic infinite line.
        # Perp to plastic direction: (-upd_z, upd_x); signed distance:
        nx, nz = -upd_z, upd_x
        d_perp = (mid_x - px1) * nx + (mid_z - pz1) * nz
        # Target on plastic line for the metal midpoint (along the metal direction,
        # but at the plastic line's perpendicular position).
        target_x = mid_x - d_perp * nx
        target_z = mid_z - d_perp * nz
        out.append(dict(
            seg=((px1, pz1), (px2, pz2)),
            d_perp=float(d_perp),
            target=(float(target_x), float(target_z)),
        ))

    out.sort(key=lambda c: abs(c["d_perp"]))
    return out


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
    groups: list[int] = state.get("groups") or [0] * len(state["vertices"])
    raw_mm = state["raw_vertices_mm"]
    stl_path: Path = state["stl_path"]
    n = len(verts)

    # Y-axis hole projection (for the white circles in the overlay)
    y_holes = [h for h in state["holes_data"]["holes"] if h["axis"] == "Y"]

    # Plastic Y-face triangles + boundary segments (for snap targets)
    stl_proj = None
    plastic_segments: list = []
    if stl_path.exists():
        m = stl_mesh.Mesh.from_file(str(stl_path))
        tris = m.vectors
        norms = m.normals.copy()
        nlen = np.linalg.norm(norms, axis=1, keepdims=True)
        n_unit = np.where(nlen > 1e-12, norms / nlen, 0.0)
        y_face_mask = np.abs(n_unit[:, 1]) > 0.95
        if y_face_mask.any():
            stl_proj = tris[y_face_mask][:, :, [0, 2]]
            plastic_segments = plastic_boundary_segments(stl_proj)
            print(f"plastic boundary: {len(plastic_segments)} segments")
    else:
        print(f"note: STL not found at {stl_path}; overlay + snap disabled.")

    selected: list[int] = [0]
    saved_at_least_once = [False]
    dirty = [False]  # have edits been made since last save / since load?
    cand_offset: list[int] = [0]  # which pair of snap candidates is shown
    manual_pick = [False]  # in manual-snap mode, the next left-click picks a plastic segment
    editing_group: list[int] = [0]  # 0 = not in group-edit mode; otherwise the gid being edited
    history: list[tuple[list[tuple[float, float]], list[str], list[int]]] = []  # 1-step undo

    def snapshot():
        # Single-step undo: keep at most one snapshot.
        history.clear()
        history.append((
            [tuple(v) for v in verts],
            list(constraints),
            list(groups),
        ))

    def edge_length(i: int) -> float:
        x1, z1 = verts[i]
        x2, z2 = verts[(i + 1) % n]
        return float(np.hypot(x2 - x1, z2 - z1))

    def next_free_group() -> int:
        used = set(groups)
        for k in range(1, 10):
            if k not in used:
                return k
        # All taken — reuse the highest. Rare; user would need 9 groups.
        return 9

    fig, ax = plt.subplots(figsize=(10, 12))
    try:
        fig.canvas.manager.set_window_title("Align outline — H/V constraints + nudging")
    except Exception:
        pass

    banner = ax.text(
        0.5, 1.02,
        "click edge  |  H/V/N constraint  |  1/2 snap to candidate  |  F next candidates  |  "
        "←→↑↓ nudge (Shift=fine)  |  U undo  R reset  S save  D save+exit",
        transform=ax.transAxes, ha="center", va="bottom",
        color="white", fontsize=10,
        bbox=dict(boxstyle="round,pad=0.4", fc="black", ec="white", alpha=0.85),
        zorder=100,
    )
    status = ax.text(
        0.99, 0.01, "",
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
        # In manual-snap mode, brighten ALL plastic boundary segments so the
        # user can clearly see what they're clicking on.
        if manual_pick[0]:
            for (px1, pz1), (px2, pz2) in plastic_segments:
                ax.plot([px1, px2], [pz1, pz2], color="cyan", lw=2.2,
                        alpha=0.95, zorder=5)
        # Hole circles
        for h in y_holes:
            ax.add_patch(plt.Circle(
                (h["cx"], h["cz"]), h["r"], fill=False,
                edgecolor="dimgray", lw=0.6, alpha=0.6,
            ))
        # Polygon edges (colour by constraint).
        # During group-edit mode, the group's members get a thick magenta
        # underlay so they stand out.
        for i in range(n):
            x1, z1 = verts[i]
            x2, z2 = verts[(i + 1) % n]
            if editing_group[0] != 0 and groups[i] == editing_group[0]:
                ax.plot([x1, x2], [z1, z2], color="magenta", lw=7.0,
                        alpha=0.55, zorder=3, solid_capstyle="round")
            colour = CONSTRAINT_COLORS[constraints[i]]
            lw = 4.0 if i == selected[0] else 1.6
            ax.plot([x1, x2], [z1, z2], color=colour, lw=lw, solid_capstyle="round",
                    zorder=6 if i == selected[0] else 4)
        # Vertices
        vx = [v[0] for v in verts]
        vz = [v[1] for v in verts]
        ax.plot(vx, vz, "o", color="yellow", ms=4, mec="black", mew=0.5, zorder=7)
        # Group labels (small badge near the midpoint, only when group > 0)
        for ei in range(n):
            g = groups[ei]
            if g == 0:
                continue
            x1, z1 = verts[ei]
            x2, z2 = verts[(ei + 1) % n]
            ax.annotate(
                f"g{g}", (0.5 * (x1 + x2), 0.5 * (z1 + z2)),
                color="black", fontsize=8, fontweight="bold",
                ha="center", va="center",
                xytext=(0, -14), textcoords="offset points",
                bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="black", lw=0.6),
                zorder=8,
            )
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
        # Snap candidates for the selected edge (top 2 within current window).
        # Skipped in manual-pick mode to keep the canvas readable.
        if not manual_pick[0]:
            candidates = snap_candidates((verts[i], verts[(i + 1) % n]), plastic_segments)
            visible = candidates[cand_offset[0] : cand_offset[0] + 2]
            cand_colors = ["lime", "darkorange"]
            for k, c in enumerate(visible, start=1):
                (cx1, cz1), (cx2, cz2) = c["seg"]
                ax.plot([cx1, cx2], [cz1, cz2], color=cand_colors[k - 1],
                        lw=3.0, alpha=0.9, zorder=9)
                tx, tz = c["target"]
                ax.annotate(
                    str(k), (tx, tz),
                    color="black", fontsize=12, fontweight="bold",
                    ha="center", va="center",
                    bbox=dict(boxstyle="circle,pad=0.3",
                              fc=cand_colors[k - 1], ec="black"),
                    zorder=10,
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
        if manual_pick[0]:
            banner.set_text(
                f"MANUAL SNAP — click a cyan plastic segment to snap E{i} onto it  "
                "|  Esc = cancel"
            )
        elif editing_group[0] != 0:
            banner.set_text(
                f"GROUP EDIT g{editing_group[0]} — click edges to toggle "
                "membership  |  G = commit (snap to longest)  |  Esc = cancel"
            )
        else:
            banner.set_text(
                "click edge  |  H/V/N constraint  |  1/2 snap  |  F next cands  |  "
                "M manual snap  |  G group-edit  |  ←→↑↓ nudge (Shift=fine)  |  "
                "U undo  R reset  S save  D save+exit"
            )
        status.set_text(
            f"E{i}  {constraints[i]:>10}  g{groups[i]}   "
            f"{'•dirty' if dirty[0] else 'clean'}"
        )
        fig.canvas.draw_idle()

    def shift_selected_edge(dx: float, dz: float):
        snapshot()
        i = selected[0]
        gid = groups[i]
        # If the selected edge is in a committed group (and we're NOT mid-edit
        # of that group), shift all members by the same delta.
        in_committed_group = gid != 0 and editing_group[0] != gid
        members = [k for k, g in enumerate(groups) if g == gid] if in_committed_group else [i]
        for ei in members:
            j = (ei + 1) % n
            c = constraints[ei]
            if c == "horizontal":
                verts[ei] = (verts[ei][0], verts[ei][1] + dz)
                verts[j] = (verts[j][0], verts[j][1] + dz)
            elif c == "vertical":
                verts[ei] = (verts[ei][0] + dx, verts[ei][1])
                verts[j] = (verts[j][0] + dx, verts[j][1])
            else:
                px, pz = edge_perp(verts, ei)
                mag = dx * px + dz * pz
                verts[ei] = (verts[ei][0] + mag * px, verts[ei][1] + mag * pz)
                verts[j] = (verts[j][0] + mag * px, verts[j][1] + mag * pz)
        dirty[0] = True

    def set_constraint(c: str):
        snapshot()
        i = selected[0]
        constraints[i] = c
        if c in ("horizontal", "vertical"):
            apply_constraint(verts, i, c, n)
        dirty[0] = True

    def _snap_to_plastic_segment(seg) -> None:
        """Perpendicular-shift the selected edge so its midpoint sits on
        ``seg``'s infinite line. Length and direction preserved."""
        i = selected[0]
        j = (i + 1) % n
        (px1, pz1), (px2, pz2) = seg
        pdx, pdz = px2 - px1, pz2 - pz1
        pL = float(np.hypot(pdx, pdz))
        if pL < 1e-9:
            print("degenerate plastic segment, ignoring.")
            return
        # Perp to the plastic line.
        nx, nz = -pdz / pL, pdx / pL
        mid_x = 0.5 * (verts[i][0] + verts[j][0])
        mid_z = 0.5 * (verts[i][1] + verts[j][1])
        d = (mid_x - px1) * nx + (mid_z - pz1) * nz  # signed perp distance
        snapshot()
        verts[i] = (verts[i][0] - d * nx, verts[i][1] - d * nz)
        verts[j] = (verts[j][0] - d * nx, verts[j][1] - d * nz)
        dirty[0] = True
        print(f"snapped E{i} (shift {-d:+.3f} mm perpendicular)")

    def snap_to_candidate(k: int):
        """Snap the selected edge perpendicularly onto candidate k (1 or 2)."""
        i = selected[0]
        candidates = snap_candidates(
            (verts[i], verts[(i + 1) % n]), plastic_segments,
        )
        visible = candidates[cand_offset[0] : cand_offset[0] + 2]
        if not visible:
            print("no snap candidates for this edge — try nudging closer or check parallelism.")
            return
        if k - 1 >= len(visible):
            print(f"snap candidate {k} not available (only {len(visible)} shown).")
            return
        _snap_to_plastic_segment(visible[k - 1]["seg"])

    def nearest_plastic_segment(px: float, pz: float):
        if not plastic_segments:
            return None
        best = None
        best_d = float("inf")
        for seg in plastic_segments:
            (x1, z1), (x2, z2) = seg
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
                best = seg
        return best

    def toggle_group_edit():
        """G key handler — enter/commit group-edit mode."""
        i = selected[0]
        if editing_group[0] == 0:
            # Entering edit mode.
            snapshot()
            gid = groups[i]
            if gid == 0:
                gid = next_free_group()
                groups[i] = gid
            editing_group[0] = gid
            members = [k for k, g in enumerate(groups) if g == gid]
            print(f"group edit g{gid}: members {members}")
        else:
            # Committing — snap members to the longest edge's position.
            gid = editing_group[0]
            commit_group(gid)
            editing_group[0] = 0

    def commit_group(gid: int):
        members = [k for k, g in enumerate(groups) if g == gid]
        if not members:
            print(f"group g{gid} is empty — nothing to commit.")
            return
        snapshot()
        if len(members) == 1:
            # A single-member group is just an edge label; nothing to snap.
            print(f"committed g{gid} (single member, no snap).")
            dirty[0] = True
            return
        # Pick the longest edge as the anchor.
        longest = max(members, key=edge_length)
        x1, z1 = verts[longest]
        x2, z2 = verts[(longest + 1) % n]
        dx, dz = abs(x2 - x1), abs(z2 - z1)
        is_h = dx >= dz
        if is_h:
            target_z = 0.5 * (z1 + z2)
            for ei in members:
                j = (ei + 1) % n
                verts[ei] = (verts[ei][0], target_z)
                verts[j] = (verts[j][0], target_z)
                constraints[ei] = "horizontal"
            print(f"committed g{gid}: {len(members)} edges → horizontal at Z={target_z:.3f} "
                  f"(anchor E{longest}, length {edge_length(longest):.2f} mm)")
        else:
            target_x = 0.5 * (x1 + x2)
            for ei in members:
                j = (ei + 1) % n
                verts[ei] = (target_x, verts[ei][1])
                verts[j] = (target_x, verts[j][1])
                constraints[ei] = "vertical"
            print(f"committed g{gid}: {len(members)} edges → vertical at X={target_x:.3f} "
                  f"(anchor E{longest}, length {edge_length(longest):.2f} mm)")
        dirty[0] = True

    def toggle_group_membership(edge_index: int):
        """In group-edit mode, clicking an edge toggles its membership."""
        gid = editing_group[0]
        if gid == 0:
            return
        snapshot()
        if groups[edge_index] == gid:
            groups[edge_index] = 0
            print(f"E{edge_index} removed from g{gid}")
        else:
            groups[edge_index] = gid  # an edge is in at most 1 group
            print(f"E{edge_index} added to g{gid}")
        dirty[0] = True

    def force_next_candidates():
        i = selected[0]
        candidates = snap_candidates(
            (verts[i], verts[(i + 1) % n]), plastic_segments,
        )
        if not candidates:
            print("no snap candidates for this edge.")
            return
        cand_offset[0] = (cand_offset[0] + 2) % max(1, len(candidates))
        print(f"showing candidates {cand_offset[0] + 1}-{cand_offset[0] + 2} "
              f"of {len(candidates)}.")

    def undo():
        if not history:
            print("nothing to undo.")
            return
        prev_verts, prev_constraints, prev_groups = history.pop()
        verts[:] = [tuple(v) for v in prev_verts]
        constraints[:] = list(prev_constraints)
        groups[:] = list(prev_groups)
        dirty[0] = True

    def save():
        snapped = apply_all_constraints(verts, constraints, groups)
        payload = {
            "source_raw": str(state["raw_poly_json"]),
            "coords": "mm",
            "closed": True,
            "vertices_xz_mm": [[float(x), float(z)] for x, z in snapped],
            "edge_constraints": list(constraints),
            "edge_groups": list(groups),
        }
        state["edited_json_path"].write_text(json.dumps(payload, indent=2))
        saved_at_least_once[0] = True
        dirty[0] = False
        print(f"wrote {state['edited_json_path']}")

    def reset():
        snapshot()
        verts[:] = [tuple(v) for v in raw_mm]
        for k in range(n):
            constraints[k] = "free"
            groups[k] = 0
        dirty[0] = True
        cand_offset[0] = 0
        manual_pick[0] = False
        print("reset to raw trace.")

    def on_click(e):
        if e.inaxes is not ax or e.button != 1 or e.xdata is None:
            return
        if manual_pick[0]:
            seg = nearest_plastic_segment(e.xdata, e.ydata)
            if seg is None:
                print("no plastic segments available.")
            else:
                _snap_to_plastic_segment(seg)
            manual_pick[0] = False
            repaint()
            return
        if editing_group[0] != 0:
            # In group-edit mode, clicks toggle group membership on the
            # nearest edge instead of re-selecting.
            target = nearest_edge_to_point(e.xdata, e.ydata, verts)
            toggle_group_membership(target)
            repaint()
            return
        new_sel = nearest_edge_to_point(e.xdata, e.ydata, verts)
        if new_sel != selected[0]:
            cand_offset[0] = 0  # reset candidate window for the new edge
        selected[0] = new_sel
        repaint()

    def on_key(e):
        if e.key is None:
            return
        # Esc cancels manual-pick or group-edit mode without applying.
        if e.key in ("escape", "esc"):
            if manual_pick[0]:
                manual_pick[0] = False
                print("manual snap cancelled.")
                repaint()
                return
            if editing_group[0] != 0:
                editing_group[0] = 0
                print("group edit cancelled (members not committed).")
                repaint()
                return
            return
        k = e.key.lower()
        step = 0.1 if "shift+" in e.key else 0.5
        if k in ("h", "shift+h"):
            set_constraint("horizontal"); repaint()
        elif k in ("v", "shift+v"):
            set_constraint("vertical"); repaint()
        elif k in ("n", "shift+n"):
            set_constraint("free"); repaint()
        elif k in ("g", "shift+g"):
            toggle_group_edit(); repaint()
        elif k in ("1", "shift+1"):
            snap_to_candidate(1); repaint()
        elif k in ("2", "shift+2"):
            snap_to_candidate(2); repaint()
        elif k in ("f", "shift+f"):
            force_next_candidates(); repaint()
        elif k in ("m", "shift+m"):
            if not plastic_segments:
                print("no plastic segments available — STL not loaded?")
            else:
                manual_pick[0] = True
                print(f"manual snap mode — click a plastic segment to snap E{selected[0]}")
                repaint()
        elif k in ("u", "shift+u"):
            undo(); repaint()
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
