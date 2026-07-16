#!/usr/bin/env bash
# Build the current assembly (with the render colours) into a live FCStd and open
# it in the FreeCAD GUI so you can orbit/pan/zoom it freely.
#
# Usage:
#   ./view_assembly.sh            # full assembled machine
#   ./view_assembly.sh II         # just one sub-component
#                                 # (I  II  II_R  III  IV  V  VI)
#   ./view_assembly.sh VI --params  # + labelled double-arrow dimensions for each
#                                 # locatable value in the component's *.params.yaml (R.3)
#
# It regenerates the FCStd from assemble_and_render.py every run, so it always
# reflects the current code. Output goes to a scratch file (cnc_assembly_live.FCStd
# or cnc_live_<SC>.FCStd) — your git-tracked cnc_assembly.FCStd is left untouched.
set -euo pipefail
cd "$(dirname "$0")"

FC="$HOME/.local/opt/FreeCAD-1.1.1"
SC=""                                          # optional sub-component code
PARAMS=""                                      # R.3: --params dimension overlay
for a in "$@"; do
  case "$a" in
    --params) PARAMS=1 ;;
    -*)       echo "unknown flag: $a" >&2; exit 2 ;;
    *)        SC="$a" ;;
  esac
done
OUT="cnc_assembly_live.FCStd"
[ -n "$SC" ] && OUT="cnc_live_${SC}.FCStd"
SETUP="_view_setup.py"                        # startup macro (view fit + navigation)

SC="$SC" PARAMS="$PARAMS" OUTFILE="$OUT" DISPLAY="${DISPLAY:-:0}" \
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
# R.3: draw the parameter dimensions AFTER the sub-component filter (so they survive).
if os.environ.get("PARAMS"):
    m._annotate_params(doc, sc or None)
    doc.recompute()
m._apply_colours(FreeCADGui)
doc.recompute(); time.sleep(0.6)
doc.saveAs(os.path.abspath(os.environ["OUTFILE"]))
print("saved %s — %d objects (sc=%r)" % (os.environ["OUTFILE"], len(doc.Objects), sc))
PY

# ── Startup macro (render_improvements.md R.0/R.1/R.2) ──────────────────────
# FreeCAD executes a .py given on its command line once the GUI + document are
# up, so this runs inside the interactive session (not the headless build above).
# We defer the actual work on a QTimer and retry until the 3D view exists, because
# the script can fire before the document finishes loading (same GUI-init race the
# sub-component deletion avoids up top).
cat > "$SETUP" <<'PY'
import FreeCAD, FreeCADGui
try:
    from PySide2 import QtCore, QtGui, QtWidgets
except Exception:
    from PySide import QtCore, QtGui
    QtWidgets = QtGui

# ── CopyPreselection: press F4 to copy the HOVERED element's full path (e.g.
# cnc_live_VI.Engine_Holder_P2.Face42) to the clipboard.  Installed as an
# APPLICATION-WIDE event filter, NOT a command/keyboard shortcut: the Coin 3D view
# swallows shortcut keys (and every Ctrl/Shift/Alt combo — those drive touchpad
# rotate/pan/zoom) before FreeCAD's command system sees them, but an app event
# filter gets the key press first.  Only consumes F4 when something is preselected,
# so F4 is left alone everywhere else.
_app = QtWidgets.QApplication.instance()

class _CopyPreselFilter(QtCore.QObject):
    def eventFilter(self, obj, ev):
        if ev.type() == QtCore.QEvent.KeyPress and ev.key() == QtCore.Qt.Key_F4:
            p = FreeCADGui.Selection.getPreselection()
            if p and p.ObjectName:
                sub = p.SubElementNames[0] if p.SubElementNames else ""
                txt = ".".join(x for x in (p.DocumentName, p.ObjectName, sub) if x)
                _app.clipboard().setText(txt)
                FreeCAD.Console.PrintMessage("CopyPreselection: copied %s\n" % txt)
                return True
        return False

if _app is not None:
    _copy_presel_filter = _CopyPreselFilter()
    _app.installEventFilter(_copy_presel_filter)   # module-global ref keeps it alive

# R.2: navigation method = touchpad (render_improvements R.2).
_NAV = "Gui::TouchpadNavigationStyle"
_tries = {"n": 0}

def _setup_view():
    _tries["n"] += 1
    ad = FreeCADGui.ActiveDocument
    view = ad.ActiveView if ad else None
    if view is None or not hasattr(view, "setNavigationType"):
        if _tries["n"] < 60:
            QtCore.QTimer.singleShot(250, _setup_view)
        return
    pg = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/View")
    pg.SetString("NavigationStyle", _NAV)   # R.2 (persisted for future sessions)
    pg.SetInt("RotationMode", 0)            # R.0: rotate about the WINDOW centre —
                                            #      the red dot sits at screen centre
    try:
        view.setNavigationType(_NAV)        # R.2 (live view, this session)
    except Exception:
        pass
    try:
        view.viewIsometric()
    except Exception:
        pass
    # R.0 + R.1: frame the whole (sub)assembly, centred and as large as the window
    # allows, so nothing has to be hunted for by zoom/pan.
    FreeCADGui.SendMsgToActiveView("ViewFit")

QtCore.QTimer.singleShot(500, _setup_view)
PY

exec "$HOME/.local/bin/freecad" "$PWD/$OUT" "$PWD/$SETUP"
