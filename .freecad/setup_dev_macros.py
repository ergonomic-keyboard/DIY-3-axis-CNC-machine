#!/usr/bin/env python3
"""Install the project's FreeCAD developer macros + keyboard shortcuts into the
repo-local FreeCAD config (.freecad/user.cfg), which the ~/.local/bin/freecad
wrapper loads via --user-cfg.

Idempotent: safe to re-run.  Run it with the SYSTEM python (no FreeCAD needed):

    python3 .freecad/setup_dev_macros.py

Currently installs:
  * CopyPreselection  (F4) — copy the hovered element's full path
    (e.g. cnc_live_VI.Engine_Holder_P2.Edge200) to the clipboard.  See developers.md.
"""
import os
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(HERE, "user.cfg")
MACRO_DIR = os.path.join(HERE, "Macro")

# (command name, macro filename, menu text, tooltip, accelerator)
MACROS = [
    # NB: use a MODIFIER-FREE key.  Touchpad nav grabs every modifier combo held
    # over the 3D view (Ctrl+Shift = zoom, Ctrl+Alt = rotate, ...), so any Ctrl/
    # Shift/Alt shortcut is swallowed before it fires; a plain function key isn't.
    ("Std_Macro_CopyPreselection", "CopyPreselection.FCMacro",
     "Copy preselection path",
     "Copy the hovered element's full path (Doc.Object.Sub) to the clipboard",
     "F4"),
]


def group(parent, name):
    """Find/create a <FCParamGroup Name="name"> child of `parent`."""
    for g in parent.findall("FCParamGroup"):
        if g.get("Name") == name:
            return g
    e = ET.SubElement(parent, "FCParamGroup")
    e.set("Name", name)
    return e


def set_text(grp, name, value):
    for t in grp.findall("FCText"):
        if t.get("Name") == name:
            t.text = value
            return
    e = ET.SubElement(grp, "FCText")
    e.set("Name", name)
    e.text = value


def set_bool(grp, name, value):
    val = "1" if value else "0"
    for b in grp.findall("FCBool"):
        if b.get("Name") == name:
            b.set("Value", val)
            return
    e = ET.SubElement(grp, "FCBool")
    e.set("Name", name)
    e.set("Value", val)


def main():
    tree = ET.parse(CFG)
    root = tree.getroot()                       # <FCParameters>
    base = group(group(root, "Root"), "BaseApp")
    prefs = group(base, "Preferences")

    # MacroPath → the repo macro dir, so FreeCAD finds the .FCMacro files here.
    set_text(group(prefs, "Macro"), "MacroPath", MACRO_DIR)

    macros_grp = group(group(base, "Macro"), "Macros")   # BaseApp/Macro/Macros
    shortcut_grp = group(prefs, "Shortcut")              # BaseApp/Preferences/Shortcut
    # A GLOBAL custom toolbar (visible in every workbench).  FreeCAD only creates a
    # command's QAction — and thus activates its keyboard accelerator — once the
    # command is placed on a toolbar/menu, so registering the macro alone is not
    # enough; it must live on a toolbar here too.
    toolbar = group(group(group(group(base, "Workbench"), "Global"), "Toolbar"),
                    "Custom_DevMacros")
    set_text(toolbar, "Name", "Dev macros")
    set_bool(toolbar, "Active", True)

    for cmd, script, menu, tip, accel in MACROS:
        g = group(macros_grp, cmd)
        set_text(g, "Script", script)
        set_text(g, "Menu", menu)
        set_text(g, "Tooltip", tip)
        set_text(g, "Statustip", tip)
        set_text(g, "WhatsThis", cmd)
        set_text(g, "Accel", accel)              # the keyboard shortcut
        set_bool(g, "System", False)
        # also record it as a shortcut override so the ShortcutManager binds it,
        # and place it on the global toolbar so its action (hence accel) is created.
        set_text(shortcut_grp, cmd, accel)
        set_text(toolbar, cmd, "FreeCAD")
        print("registered %-28s %-22s -> %s" % (cmd, accel, script))

    ET.indent(tree, space="  ")
    tree.write(CFG, encoding="UTF-8", xml_declaration=True)
    # FreeCAD writes a standalone="no" declaration; match it so diffs stay minimal.
    with open(CFG, "r", encoding="utf-8") as f:
        data = f.read()
    data = data.replace("<?xml version='1.0' encoding='UTF-8'?>",
                        '<?xml version="1.0" encoding="UTF-8" standalone="no" ?>', 1)
    with open(CFG, "w", encoding="utf-8") as f:
        f.write(data)
    print("updated %s" % CFG)
    print("macros in %s" % MACRO_DIR)


if __name__ == "__main__":
    main()
