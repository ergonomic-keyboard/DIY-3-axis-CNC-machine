#!/usr/bin/env bash
# Build the current assembly (with the render colours) into a live FCStd and open
# it in the FreeCAD GUI so you can orbit/pan/zoom it freely.
#
# Usage:
#   ./view_assembly.sh            # full assembled machine
#   ./view_assembly.sh II         # just one sub-component
#                                 # (I  II  II_R  III  IV  V  VI)
#
# It regenerates the FCStd from assemble_and_render.py every run, so it always
# reflects the current code. Output goes to a scratch file (cnc_assembly_live.FCStd
# or cnc_live_<SC>.FCStd) — your git-tracked cnc_assembly.FCStd is left untouched.
set -euo pipefail
cd "$(dirname "$0")"

FC="$HOME/.local/opt/FreeCAD-1.1.1"
SC="${1:-}"                                   # optional sub-component code
OUT="cnc_assembly_live.FCStd"
[ -n "$SC" ] && OUT="cnc_live_${SC}.FCStd"

SC="$SC" OUTFILE="$OUT" DISPLAY="${DISPLAY:-:0}" \
  PYTHONPATH="$FC/usr/lib" "$FC/usr/bin/python" - <<'PY'
import os, time, FreeCAD, FreeCADGui
import assemble_and_render as m
FreeCADGui.showMainWindow(); time.sleep(1.2)
doc = FreeCAD.newDocument("CNC_Assembly"); m.doc = doc
m._build_assembly(doc)
# Keep only the requested sub-component.  DELETE the others (a document-level op)
# rather than hiding them via the GUI — hiding depends on the GUI being fully
# initialised and can silently no-op if it isn't ready yet, leaving the frame etc.
# visible in the saved file.
sc = os.environ.get("SC", "").strip()
if sc:
    for o in list(doc.Objects):
        if m._classify_subcomponent(o.Name) != sc:
            try:
                doc.removeObject(o.Name)
            except Exception:
                pass
    doc.recompute()
m._apply_colours(FreeCADGui)
doc.recompute(); time.sleep(0.6)
doc.saveAs(os.path.abspath(os.environ["OUTFILE"]))
print("saved %s — %d objects (sc=%r)" % (os.environ["OUTFILE"], len(doc.Objects), sc))
PY

exec "$HOME/.local/bin/freecad" "$PWD/$OUT"
