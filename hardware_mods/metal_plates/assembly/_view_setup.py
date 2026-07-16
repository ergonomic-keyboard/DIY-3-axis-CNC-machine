import FreeCAD, FreeCADGui
try:
    from PySide2 import QtCore
except Exception:
    from PySide import QtCore

# R.2: navigation method = touchscreen.  FreeCAD 1.1 has no style literally named
# "Touchscreen"; its touch-oriented style (pinch-zoom / two-finger orbit) is
# "Gesture".  Persist it and apply it to the live view.
_NAV = "Gui::GestureNavigationStyle"
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
