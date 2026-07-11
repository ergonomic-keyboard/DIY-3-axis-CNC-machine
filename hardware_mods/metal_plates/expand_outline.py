#!/usr/bin/env python3
"""expand_outline.py — compile a human-authored ``outline.yaml`` into ``outline.json``.

Companion to ``expand_holes.py``. ``outline.yaml`` (in an example's
``4_outline/`` folder) is the editable, commented source of truth for a plate's
silhouette: an ordered list of vertices in the X–Z plane, each carrying the
edge that leaves it (``constraint``: free|horizontal|vertical, and an integer
``group``). This script expands it into the polygon JSON that ``build_model.py``
reads (``outline.json``), which build_model prefers over the raw/edited
``*_polygon.json`` traces.

Run (any Python with PyYAML — e.g. the FreeCAD AppImage one):
    ~/.local/opt/FreeCAD-1.1.1/usr/bin/python \
        hardware_mods/metal_plates/expand_outline.py \
        --example hardware_mods/metal_plates/examples/II_side_plates/M20a_left_body

Then rebuild:  python hardware_mods/metal_plates/build_model.py --example <same folder>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required. `pip install pyyaml`, or use the FreeCAD "
             "AppImage python (~/.local/opt/FreeCAD-*/usr/bin/python).")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--example", required=True, type=Path)
    ap.add_argument("--no-check", action="store_true",
                    help="skip the diff against the *_polygon_edited.json trace")
    args = ap.parse_args()

    stage4 = args.example / "4_outline"
    yaml_path = stage4 / "outline.yaml"
    out_path = stage4 / "outline.json"
    if not yaml_path.exists():
        sys.exit(f"missing {yaml_path}")

    spec = yaml.safe_load(yaml_path.read_text())
    meta = spec.get("meta", {})
    verts = spec.get("vertices", [])
    if len(verts) < 3:
        sys.exit(f"{yaml_path}: need at least 3 vertices, got {len(verts)}")

    xz: list[list[float]] = []
    constraints: list[str] = []
    groups: list[int] = []
    for i, v in enumerate(verts):
        try:
            xz.append([float(v["x"]), float(v["z"])])
        except (KeyError, TypeError):
            sys.exit(f"vertex #{i} ({v.get('id','?')}): needs numeric x and z")
        edge = v.get("edge", {}) or {}
        constraints.append(str(edge.get("constraint", "free")))
        groups.append(int(edge.get("group", 0)))

    payload = {
        "source_raw": "outline.yaml (expanded by expand_outline.py — do not edit by hand)",
        "coords": meta.get("coords", "mm"),
        "closed": bool(meta.get("closed", True)),
        "vertices_xz_mm": xz,
        "edge_constraints": constraints,
        "edge_groups": groups,
    }
    out_path.write_text(json.dumps(payload, indent=2))
    print(f"wrote {out_path}  ({len(xz)} vertices)")

    if not args.no_check:
        trace = sorted(stage4.glob("*_polygon_edited.json")) or \
                [p for p in sorted(stage4.glob("*_polygon.json"))
                 if not p.name.endswith("_edited.json")]
        if trace:
            t = json.loads(trace[0].read_text())
            tv = t.get("vertices_xz_mm")
            if tv is None:
                print(f"  (trace {trace[0].name} has no vertices_xz_mm — skipping check)")
            else:
                dmax = 0.0
                if len(tv) == len(xz):
                    for a, b in zip(tv, xz):
                        dmax = max(dmax, abs(a[0]-b[0]), abs(a[1]-b[1]))
                    cc = t.get("edge_constraints") == constraints
                    gg = t.get("edge_groups") == groups
                    tag = "MATCH ✓" if (dmax < 1e-6 and cc and gg) else "differs"
                    print(f"  self-check vs {trace[0].name}: {tag} "
                          f"(max vertex Δ={dmax:.2e} mm, constraints={'=' if cc else '≠'}, "
                          f"groups={'=' if gg else '≠'})")
                else:
                    print(f"  self-check: vertex count {len(xz)} vs trace {len(tv)} — differs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
