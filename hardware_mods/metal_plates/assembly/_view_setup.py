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
