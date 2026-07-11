#!/usr/bin/env python3
"""expand_holes.py — compile a human-authored ``holes.yaml`` into ``holes.json``.

``holes.yaml`` (in an example's ``2_flattened_image/`` folder) is the editable,
commented, grouped, parametric source of truth for a plate's holes. This script
expands its groups/patterns into the flat hole list that ``build_model.py`` reads
(``holes.json``), preserving the exact schema build_model expects and passing
through the plate bounding box and any non-Y holes from the legacy
``holes_from_stl.json`` cache.

Because ``build_model.py`` builds each hole as a 2-D circle extruded through the
whole plate, only ``axis == "Y"`` holes and their (cx, cz, r) matter — which is
exactly what this expander produces.

Run (any Python that has PyYAML — e.g. the bundled FreeCAD one, which does):
    ~/.local/opt/FreeCAD-1.1.1/usr/bin/python \
        hardware_mods/metal_plates/expand_holes.py \
        --example hardware_mods/metal_plates/examples/II_side_plates/M20a_left_body

Then rebuild the STEP:
    python hardware_mods/metal_plates/build_model.py --example <same folder>

By default it also self-checks the expanded Y-hole set against the legacy
``holes_from_stl.json`` and prints any differences (so you can see exactly what
your edits changed relative to the STL extraction).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required. Install with `pip install pyyaml`, or run this "
             "with the FreeCAD AppImage python (~/.local/opt/FreeCAD-*/usr/bin/python).")


def _resolve_d(spec: dict, threads: dict, g_thread, g_fit, where: str) -> float:
    """Diameter for a hole/pattern: explicit ``d`` wins, else thread + fit."""
    if "d" in spec and spec["d"] is not None:
        return float(spec["d"])
    thread = spec.get("thread", g_thread)
    fit = spec.get("fit", g_fit) or "clearance"
    if thread is None:
        raise SystemExit(f"{where}: needs either `d:` or `thread:`")
    if thread not in threads:
        raise SystemExit(f"{where}: unknown thread {thread!r} (add it to `threads:`)")
    t = threads[thread]
    key = "clearance_d" if fit == "clearance" else "tap_d"
    if key not in t:
        raise SystemExit(f"{where}: thread {thread} has no {key}")
    return float(t[key])


def _z(spec: dict, bottom: float, where: str) -> float:
    if "z_from_bottom" in spec:
        return bottom + float(spec["z_from_bottom"])
    if "z" in spec:
        return float(spec["z"])
    raise SystemExit(f"{where}: needs `z_from_bottom:` or `z:`")


def _rec(cx: float, cz: float, d: float, group: str, hid, thread, plate: dict) -> dict:
    """One JSON hole record in build_model's schema (axis Y, drilled through)."""
    cy_mid = (plate.get("plate_y_min", 0.0) + plate.get("plate_y_max", 0.0)) / 2.0
    rec = {
        "axis": "Y",
        "cx": round(float(cx), 4),
        "cy": round(cy_mid, 4),
        "cz": round(float(cz), 4),
        "r": round(float(d) / 2.0, 4),
        "d": round(float(d), 4),
        "group": group,
    }
    if hid is not None:
        rec["id"] = hid
    if thread is not None:
        rec["thread"] = thread
    return rec


def expand_group(g: dict, bottom: float, threads: dict, plate: dict) -> list[dict]:
    gid = g.get("id", "?")
    g_thread = g.get("thread")
    g_fit = g.get("fit")
    out: list[dict] = []

    if "pattern" in g:
        p = g["pattern"]
        if p.get("type") != "rect4":
            raise SystemExit(f"group {gid}: only pattern type 'rect4' is supported")
        dx, dy = float(p["dx"]), float(p["dy"])
        anchor = p["anchor"]
        x0 = float(anchor["x"])
        z0 = _z(anchor, bottom, f"group {gid} anchor")
        d = _resolve_d(p, threads, g_thread, g_fit, f"group {gid} pattern")
        # clockwise from top-left; anchor (#4) is bottom-left
        pts = {1: (x0, z0 + dy), 2: (x0 + dx, z0 + dy),
               3: (x0 + dx, z0), 4: (x0, z0)}
        overrides = p.get("holes", {}) or {}
        for n in (1, 2, 3, 4):
            ov = overrides.get(n, overrides.get(str(n), {})) or {}
            dn = float(ov["d"]) if "d" in ov else d
            cx, cz = pts[n]
            out.append(_rec(cx, cz, dn, gid, f"{gid}.{n}", g_thread, plate))
    elif "holes" in g:
        for h in g["holes"]:
            x = float(h["x"])
            z = _z(h, bottom, f"group {gid} hole {h.get('id','?')}")
            d = _resolve_d(h, threads, g_thread, g_fit,
                           f"group {gid} hole {h.get('id','?')}")
            out.append(_rec(x, z, d, gid, h.get("id"), h.get("thread", g_thread), plate))
    else:
        raise SystemExit(f"group {gid}: needs either `pattern:` or `holes:`")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--example", required=True, type=Path,
                    help="part folder, e.g. .../examples/II_side_plates/M20a_left_body")
    ap.add_argument("--no-check", action="store_true",
                    help="skip the diff against holes_from_stl.json")
    args = ap.parse_args()

    stage2 = args.example / "2_flattened_image"
    yaml_path = stage2 / "holes.yaml"
    out_path = stage2 / "holes.json"
    legacy_path = stage2 / "holes_from_stl.json"

    if not yaml_path.exists():
        sys.exit(f"missing {yaml_path}")
    spec = yaml.safe_load(yaml_path.read_text())

    # plate bbox + non-Y holes are passed through from the legacy extraction so
    # build_model and the plan renderer keep all the context they expect.
    plate: dict = {}
    passthrough_non_y: list[dict] = []
    if legacy_path.exists():
        legacy = json.loads(legacy_path.read_text())
        for k in ("plate_x_min", "plate_x_max", "plate_y_min",
                  "plate_y_max", "plate_z_min", "plate_z_max"):
            if k in legacy:
                plate[k] = legacy[k]
        passthrough_non_y = [h for h in legacy.get("holes", []) if h.get("axis") != "Y"]

    bottom = float(spec["datums"]["plate_bottom_edge_z"])
    threads = spec.get("threads", {})

    y_holes: list[dict] = []
    for g in spec.get("groups", []):
        y_holes.extend(expand_group(g, bottom, threads, plate))

    payload = dict(plate)
    payload["_generated_from"] = "holes.yaml (do not edit by hand; run expand_holes.py)"
    payload["holes"] = y_holes + passthrough_non_y
    out_path.write_text(json.dumps(payload, indent=2))

    print(f"wrote {out_path}")
    print(f"  {len(y_holes)} Y-holes from {len(spec.get('groups', []))} group(s)"
          f" + {len(passthrough_non_y)} passthrough non-Y hole(s)")
    for g in spec.get("groups", []):
        n = len(expand_group(g, bottom, threads, plate))
        print(f"    · {g.get('id'):24s} {n} hole(s)")

    if not args.no_check and legacy_path.exists():
        def netset(holes):
            net: dict = {}
            for h in holes:
                if h.get("axis") != "Y":
                    continue
                k = (round(h["cx"], 1), round(h["cz"], 1))
                net[k] = max(net.get(k, 0.0), round(h["r"], 2))
            return net
        want = netset(json.loads(legacy_path.read_text()).get("holes", []))
        got = netset(y_holes)
        added = sorted(set(got) - set(want))
        removed = sorted(set(want) - set(got))
        changed = sorted(k for k in set(want) & set(got)
                         if abs(want[k] - got[k]) > 0.01)
        if not (added or removed or changed):
            print("  self-check: expanded holes MATCH holes_from_stl.json exactly ✓")
        else:
            print("  self-check vs holes_from_stl.json (your edits changed):")
            for k in changed:
                print(f"    ~ {k}: Ø{2*want[k]:.2f} -> Ø{2*got[k]:.2f}")
            for k in added:
                print(f"    + {k}: Ø{2*got[k]:.2f} (new / not in STL)")
            for k in removed:
                print(f"    - {k}: Ø{2*want[k]:.2f} (in STL, dropped)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
