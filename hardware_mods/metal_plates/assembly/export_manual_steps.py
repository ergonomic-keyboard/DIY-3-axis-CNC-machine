#!/usr/bin/env python3
"""export_manual_steps.py — export STEP from the highest-versioned FCStd in
each manual_design/ folder (C.5 versioning).

For every metal part that lives in
    examples/*/*/manual_design/vN.FCStd,
this script picks the FCStd with the largest N and exports it into the same
example's 5_models_and_renders/<name>.step (creating that folder if needed).
The output filename encodes the version (e.g. p1of2_v15.step) alongside the
canonical filename the assembly script consumes.

Run from repo root:
    python hardware_mods/metal_plates/assembly/export_manual_steps.py

Usage note: FreeCAD reads STEP files reliably in-process but its Python API
can segfault when spawned from a fresh interpreter under some Nix stores.
This script therefore runs each conversion in its own subprocess via
`FreeCADCmd`, which is the officially supported CLI.
"""
from __future__ import annotations
import argparse
import os
import re
import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
EXAMPLES = REPO / "hardware_mods/metal_plates/examples"


# For each part we know: (manual_design folder, output filename the assembly
# script expects, human name).  Add new metal parts here.
PARTS: list[dict] = [
    dict(
        folder="IV_engine_plate_p1of2/M36a_vertical_plate",
        step_name="starting_point_rect_metal.step",
        label="M36.a (Engine_Holder_P1)",
    ),
    dict(
        folder="VI_engine_plate_p2of2_and_router/M36b_vertical_plate",
        step_name="engine_holder_vertical_plate_p2of2.step",
        label="M36.b (Engine_Holder_P2)",
    ),
    dict(
        folder="V_z_axis_drive/_threaded_rod_clamper_experiment",
        step_name="threaded_rod_clamper.step",
        label="threaded rod clamper (O03 housing, no M-code — WIP)",
    ),
]


_VER_RE = re.compile(r"^v(\d+)\.FCStd$")


def _latest_fcstd(manual_design: Path) -> tuple[Path, int] | None:
    """Return (path, version) of the highest-numbered vN.FCStd, or None."""
    best: tuple[Path, int] | None = None
    for fp in manual_design.iterdir():
        m = _VER_RE.match(fp.name)
        if not m:
            continue
        n = int(m.group(1))
        if best is None or n > best[1]:
            best = (fp, n)
    return best


def _export(fcstd: Path, step_out: Path) -> bool:
    """Run FreeCADCmd to open `fcstd` and export its first solid to `step_out`.
    Returns True on success."""
    script = f'''
import FreeCAD, Part, sys
doc = FreeCAD.open({str(fcstd)!r})
solids = []
for o in doc.Objects:
    sh = getattr(o, "Shape", None)
    if sh is None:
        continue
    try:
        solids.extend(sh.Solids)
    except Exception:
        pass
if not solids:
    print("no solid found in", {str(fcstd)!r}, file=sys.stderr)
    sys.exit(2)
comp = solids[0] if len(solids) == 1 else Part.Compound(solids)
Part.export([o for o in doc.Objects if getattr(o, "Shape", None) is not None
             and o.Shape.Solids], {str(step_out)!r})
print("wrote", {str(step_out)!r})
'''
    fc = os.environ.get("FREECADCMD", "FreeCADCmd")
    r = subprocess.run([fc, "-c", script], check=False)
    return r.returncode == 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dry-run", action="store_true",
                    help="just report which FCStd would be exported")
    args = ap.parse_args()

    exit_code = 0
    for part in PARTS:
        manual = EXAMPLES / part["folder"] / "manual_design"
        if not manual.is_dir():
            print(f"[{part['label']}] SKIP — no manual_design/ folder")
            continue
        latest = _latest_fcstd(manual)
        if latest is None:
            print(f"[{part['label']}] SKIP — no vN.FCStd in {manual}")
            continue
        fcstd, ver = latest
        stage5 = EXAMPLES / part["folder"] / "5_models_and_renders"
        stage5.mkdir(exist_ok=True)
        step_out = stage5 / part["step_name"]
        versioned = stage5 / f"{step_out.stem}_v{ver}.step"

        print(f"[{part['label']}] {fcstd.name} → {step_out.name} "
              f"(also as {versioned.name})")
        if args.dry_run:
            continue

        if not _export(fcstd, step_out):
            print(f"[{part['label']}] FAILED to export", file=sys.stderr)
            exit_code = 1
            continue
        # copy to versioned name too so history is preserved on disk
        try:
            versioned.write_bytes(step_out.read_bytes())
        except Exception as e:
            print(f"[{part['label']}] warning: could not write "
                  f"{versioned}: {e}", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
