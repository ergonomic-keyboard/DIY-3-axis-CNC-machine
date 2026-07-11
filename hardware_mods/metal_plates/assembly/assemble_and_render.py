#!/usr/bin/env python3
"""assemble_and_render.py — build the CNC FCStd assembly and render GIFs.

Coordinate system:
  X  →  machine depth   (front = 0, back = 900 mm)
  Y  →  machine width   (left outer = 0, right outer = 793 mm)
  Z  →  vertical        (Z=0 = plate attachment level)

Run from repo root:
    python hardware_mods/metal_plates/assembly/assemble_and_render.py

Outputs:
    assembly/cnc_assembly.FCStd
    assembly/cnc_assembly_gif.gif       — kinematic (gantry + z-slider)
    assembly/cnc_assembly_explode_gif.gif — explode / re-assemble animation

The render phase is re-invoked as a subprocess with --render / --explode-render
so that FreeCADGui.showMainWindow() is called before any document is created.
"""
from __future__ import annotations
import argparse
import math
import os
import subprocess
import sys
import tempfile
import time

# ── FreeCAD / render-dep discovery ──────────────────────────────────────────────
# FreeCAD is a compiled app located differently per machine (extracted AppImage on
# Ubuntu, nixpkgs on NixOS). env_bootstrap.ensure_freecad() auto-detects it, puts
# its lib dir on sys.path (exporting $FREECAD_LIB so re-invoked render subprocesses
# inherit it), forces the xcb Qt backend, strips the VS Code snap env leak, and adds
# the local pip-installed .render_deps (static imageio-ffmpeg). See env_bootstrap.py.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import env_bootstrap  # noqa: E402  (hardware_mods/metal_plates/env_bootstrap.py)

_RENDER_DEPS = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".render_deps")
FREECAD_LIB = env_bootstrap.ensure_freecad(render_deps_dir=_RENDER_DEPS)
FFMPEG = env_bootstrap.find_ffmpeg()

import FreeCAD
import Mesh          # noqa: F401 – keep import so FreeCAD mesh module is loaded
import Part

# ── Paths ─────────────────────────────────────────────────────────────────────
REPO   = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
           os.path.abspath(__file__)))))
METAL  = os.path.join(REPO, "hardware_mods/metal_plates/examples")
OUT    = os.path.join(REPO, "hardware_mods/metal_plates/assembly")

ASSEMBLY_VERSION  = "v2"

# Canonical name the `freecad` launcher wrapper auto-opens; a versioned copy is
# also written next to it for history (C.5).
FCSTD_PATH        = os.path.join(OUT, "cnc_assembly.FCStd")
FCSTD_VERSIONED   = os.path.join(OUT, f"cnc_assembly_{ASSEMBLY_VERSION}.FCStd")
GIF_PATH          = os.path.join(OUT, "cnc_assembly_gif.gif")
EXPLODE_GIF_PATH  = os.path.join(OUT, "cnc_assembly_explode_gif.gif")
STAGED_GIF_PATH   = os.path.join(OUT, "cnc_assembly_staged_gif.gif")
SUBCOMPONENT_DIR  = os.path.join(OUT, "subcomponents")

# ── Colors (R,G,B floats 0–1) ─────────────────────────────────────────────────
COL_EXTRUSION = (0.70, 0.72, 0.75)
COL_RAIL      = (0.82, 0.84, 0.86)
COL_METAL     = (0.55, 0.60, 0.65)
COL_BLOCK     = (0.40, 0.42, 0.45)
COL_BOLT      = (0.18, 0.18, 0.22)   # dark steel
COL_NUT       = (0.28, 0.24, 0.10)   # slightly warm / galvanised
COL_PLACEHOLDER = (0.86, 0.55, 0.20) # visible orange for missing STEP fallback

# ── C.2 / C.3 / C.4 — parametric fastener catalogue ───────────────────────────
# Single source of truth. Swap a bolt size (M3→M5) and shaft_d, head_d, hole_d
# all update together, and the hole clearance follows the bolt (ISO 273 medium
# clearance). Each entry also carries the thread spec used as an annotation on
# every produced hole / nut / bolt so tooling can distinguish M-through-hole
# from M-tapped-thread.
#
# Fields:
#   shaft_d   — nominal thread diameter (mm)
#   head_d    — hex socket head diameter (mm, ISO 4762)
#   head_h    — head height (mm)
#   nut_af    — hex-nut across-flats (mm, ISO 4032/DIN 934)
#   nut_thk   — hex-nut thickness    (mm, ISO 4032/DIN 934)
#   clearance — through-hole clearance diameter, medium fit (mm, ISO 273)
#   tap       — recommended tap-drill diameter for threaded engagement (mm)
FASTENERS: dict[str, dict] = {
    "M3": {"shaft_d": 3.0, "head_d": 5.5, "head_h": 3.0,
           "nut_af": 5.5,  "nut_thk": 2.4, "clearance": 3.4, "tap": 2.5},
    "M4": {"shaft_d": 4.0, "head_d": 7.0, "head_h": 3.5,
           "nut_af": 7.0,  "nut_thk": 3.2, "clearance": 4.5, "tap": 3.3},
    "M5": {"shaft_d": 5.0, "head_d": 9.0, "head_h": 4.0,
           "nut_af": 8.0,  "nut_thk": 4.0, "clearance": 5.5, "tap": 4.2},
    "M8": {"shaft_d": 8.0, "head_d": 13.,  "head_h": 5.5,
           "nut_af": 13.,  "nut_thk": 6.5, "clearance": 9.0, "tap": 6.8},
}


def fastener(size: str) -> dict:
    """Return the parametric spec for a bolt size (raises KeyError on unknown)."""
    return FASTENERS[size]


def hole_d(size: str) -> float:
    """Through-hole clearance diameter (medium fit ISO 273) for `size`."""
    return FASTENERS[size]["clearance"]


def thread_spec(size: str, tapped: bool = False) -> str:
    """Machine-readable thread spec used in annotations & object labels.

    - Through-hole:  "M5 clearance Ø5.5 (ISO 273 medium)"
    - Tapped hole:   "M5 tapped, pilot Ø4.2 (ISO 262)"
    """
    fs = FASTENERS[size]
    if tapped:
        return f"{size} tapped, pilot Ø{fs['tap']:.1f} (ISO 262)"
    return f"{size} clearance Ø{fs['clearance']:.1f} (ISO 273 medium)"


# ── Mutable globals ───────────────────────────────────────────────────────────
doc: "FreeCAD.Document | None" = None
_color_queue: list[tuple[str, tuple]] = []
_gantry:    list[tuple[str, float]] = []   # (name, base_x)
_z_slider:  list[tuple[str, float]] = []   # (name, base_z)

# explode animation
_explode_offsets: dict[str, tuple]                  = {}
_explode_bases:   dict[str, "FreeCAD.Placement"]   = {}

# thread annotations: object_name → spec string (surface for BOM + auditing)
_THREAD_SPEC: dict[str, str] = {}

# build-stage mapping  (1=frame, 2=side plates, 3=gantry beams, 4=Z-axis, 5=fasteners)
_STAGE: dict[str, int] = {}

# subcomponent mapping (I..VI) — used by --subcomponent-render (C.6)
_SUBCOMP: dict[str, str] = {}


# ── Low-level geometry helpers ────────────────────────────────────────────────

def _place(obj, x, y, z, yaw=0.0, pitch=0.0, roll=0.0) -> None:
    obj.Placement = FreeCAD.Placement(
        FreeCAD.Vector(x, y, z),
        FreeCAD.Rotation(yaw, pitch, roll),
    )


def add_box(name, lx, ly, lz, x, y, z, color=COL_EXTRUSION):
    obj = doc.addObject("Part::Feature", name)
    obj.Shape = Part.makeBox(lx, ly, lz)
    _place(obj, x, y, z)
    _color_queue.append((obj.Name, color))
    return obj


# Cross-axis (u,v) convention for a hole through a local box:
#   axis 'z' → (u,v) = (x,y)   axis 'y' → (u,v) = (x,z)   axis 'x' → (u,v) = (y,z)
def _hole_through(axis, u, v, d, lx, ly, lz):
    r = d / 2.0
    if axis == 'z':
        return Part.makeCylinder(r, lz + 2, FreeCAD.Vector(u, v, -1), FreeCAD.Vector(0, 0, 1))
    if axis == 'y':
        return Part.makeCylinder(r, ly + 2, FreeCAD.Vector(u, -1, v), FreeCAD.Vector(0, 1, 0))
    return Part.makeCylinder(r, lx + 2, FreeCAD.Vector(-1, u, v), FreeCAD.Vector(1, 0, 0))


def _hole_blind(axis, u, v, d, depth, lx, ly, lz):
    """Counterbore of `depth` mm drilled inward from the box's HIGH face."""
    r = d / 2.0
    if axis == 'z':
        return Part.makeCylinder(r, depth + 1, FreeCAD.Vector(u, v, lz - depth), FreeCAD.Vector(0, 0, 1))
    if axis == 'y':
        return Part.makeCylinder(r, depth + 1, FreeCAD.Vector(u, ly - depth, v), FreeCAD.Vector(0, 1, 0))
    return Part.makeCylinder(r, depth + 1, FreeCAD.Vector(lx - depth, u, v), FreeCAD.Vector(1, 0, 0))


def add_beam(name, lx, ly, lz, x, y, z, wall=2.0, holes=(), color=COL_EXTRUSION):
    """Like add_box, but models a real aluminium extrusion: a hollow tube with
    `wall` mm walls (open along its longest axis) optionally drilled with `holes`.

    All geometry is computed in the box's LOCAL frame (corner at origin, spanning
    0..lx × 0..ly × 0..lz) then placed at (x,y,z) — matching add_box.

    holes: iterable of dicts {axis, u, v, d[, depth]}.  `axis` is the drilling
    direction ('x'/'y'/'z'); (u,v) is the hole centre in the two cross-axis local
    coords (see _hole_through); `d` is the diameter.  With `depth`, the hole is a
    blind counterbore from the high face (used for wrench/socket access); without
    it, the hole goes all the way through.  Pass wall=0 to keep the box solid.
    """
    solid = Part.makeBox(lx, ly, lz)
    if wall and wall > 0.0:
        la = max((('x', lx), ('y', ly), ('z', lz)), key=lambda kv: kv[1])[0]
        if la == 'x':
            inner = Part.makeBox(lx + 2, ly - 2 * wall, lz - 2 * wall, FreeCAD.Vector(-1, wall, wall))
        elif la == 'y':
            inner = Part.makeBox(lx - 2 * wall, ly + 2, lz - 2 * wall, FreeCAD.Vector(wall, -1, wall))
        else:
            inner = Part.makeBox(lx - 2 * wall, ly - 2 * wall, lz + 2, FreeCAD.Vector(wall, wall, -1))
        solid = solid.cut(inner)
    for h in holes:
        depth = h.get("depth")
        cut = (_hole_blind(h["axis"], h["u"], h["v"], h["d"], depth, lx, ly, lz)
               if depth is not None else
               _hole_through(h["axis"], h["u"], h["v"], h["d"], lx, ly, lz))
        solid = solid.cut(cut)
    obj = doc.addObject("Part::Feature", name)
    obj.Shape = solid
    _place(obj, x, y, z)
    _color_queue.append((obj.Name, color))
    return obj


def add_step(name, path, x=0., y=0., z=0.,
             yaw=0., pitch=0., roll=0., color=COL_METAL,
             fallback_box: tuple | None = None):
    """Load `path` as a Part::Feature. If it is missing and `fallback_box`
    is supplied (as (lx, ly, lz)), a labelled placeholder is added instead
    so the assembly still builds — this satisfies C.0 (a 3D representation
    is available for every metal part, even if the STEP export is pending).
    """
    if not os.path.exists(path):
        if fallback_box is not None:
            lx, ly, lz = fallback_box
            obj = doc.addObject("Part::Feature", name)
            obj.Shape = Part.makeBox(lx, ly, lz)
            _place(obj, x, y, z, yaw, pitch, roll)
            _color_queue.append((obj.Name, COL_PLACEHOLDER))
            print(f"[assemble] WARNING: missing STEP {path} — using placeholder box",
                  flush=True)
            return obj
        raise FileNotFoundError(
            f"STEP file not found and no fallback_box given: {path}")
    shape = Part.Shape()
    shape.read(path)
    obj = doc.addObject("Part::Feature", name)
    obj.Shape = shape
    _place(obj, x, y, z, yaw, pitch, roll)
    _color_queue.append((obj.Name, color))
    return obj


def add_step_mirror_y(name, path, x=0., y=0., z=0.,
                      yaw=0., pitch=0., roll=0.,
                      mirror_at_y=396.5, color=COL_METAL):
    shape = Part.Shape()
    shape.read(path)
    shape_m = shape.mirror(FreeCAD.Vector(0, mirror_at_y, 0),
                           FreeCAD.Vector(0, 1, 0))
    obj = doc.addObject("Part::Feature", name)
    obj.Shape = shape_m
    _place(obj, x, y, z, yaw, pitch, roll)
    _color_queue.append((obj.Name, color))
    return obj


# ── Fastener geometry ─────────────────────────────────────────────────────────

_DIR = {'+x': (1,0,0), '-x': (-1,0,0),
        '+y': (0,1,0), '-y': (0,-1,0),
        '+z': (0,0,1), '-z': (0,0,-1)}

def _cyl(r, h, bx, by, bz, axis):
    dv = FreeCAD.Vector(*_DIR[axis])
    return Part.makeCylinder(r, h, FreeCAD.Vector(bx, by, bz), dv)


def add_bolt(name, bx, by, bz, axis='+z',
             size='M5', shaft_l=20.,
             shaft_d=None, head_d=None, head_h=None,
             color=COL_BOLT):
    """Head base at (bx,by,bz); shaft extends in `axis` direction.

    Parametric on `size` (e.g. 'M3', 'M5'). shaft_d/head_d/head_h can be
    explicitly overridden but by default follow the FASTENERS catalogue —
    so `size='M4'` (swap from M5) automatically resizes the head and shaft
    and lets the associated hole-clearance function `hole_d(size)` return
    the matching Ø4.5. This satisfies C.2.
    """
    fs = FASTENERS[size]
    shaft_d = fs["shaft_d"] if shaft_d is None else shaft_d
    head_d  = fs["head_d"]  if head_d  is None else head_d
    head_h  = fs["head_h"]  if head_h  is None else head_h
    dv = _DIR[axis]
    head  = _cyl(head_d/2, head_h, bx, by, bz, axis)
    shaft = _cyl(shaft_d/2, shaft_l,
                 bx + dv[0]*head_h, by + dv[1]*head_h, bz + dv[2]*head_h,
                 axis)
    obj = doc.addObject("Part::Feature", name)
    obj.Shape = head.fuse(shaft)
    _color_queue.append((obj.Name, color))
    _THREAD_SPEC[obj.Name] = f"{size}×{shaft_l:.0f} bolt (ISO 4762)"
    return obj


def add_nut(name, cx, cy, cz, axis='+z', size='M5',
            af=None, thick=None, inner_d=None, color=COL_NUT):
    """Annular hex-nut centred at (cx,cy,cz), axis along `axis`.

    Parametric on `size`: swapping M4→M5 rescales AF/thickness and the
    through-bore. Overrides remain available for special captive nuts.
    """
    fs = FASTENERS[size]
    af      = fs["nut_af"]  if af      is None else af
    thick   = fs["nut_thk"] if thick   is None else thick
    inner_d = fs["shaft_d"] if inner_d is None else inner_d
    dv = _DIR[axis]
    r_out = af / math.sqrt(3)
    bx = cx - dv[0]*thick/2
    by = cy - dv[1]*thick/2
    bz = cz - dv[2]*thick/2
    outer = _cyl(r_out,     thick, bx, by, bz, axis)
    inner = _cyl(inner_d/2, thick, bx, by, bz, axis)
    obj = doc.addObject("Part::Feature", name)
    obj.Shape = outer.cut(inner)
    _color_queue.append((obj.Name, color))
    _THREAD_SPEC[obj.Name] = f"{size} hex-nut (ISO 4032/DIN 934)"
    return obj


def add_washer(name, cx, cy, cz, axis='+z', size='M5', color=COL_NUT):
    """Flat annular washer centred at (cx,cy,cz), axis along `axis`.  Outer Ø a
    little wider than the bolt head, bore just over the shaft.  (Complaint I-2 —
    the rings that go around each thread.)"""
    fs = FASTENERS[size]
    outer_d = fs["head_d"] + 2.0
    inner_d = fs["shaft_d"] + 1.0
    thick = 1.6
    dv = _DIR[axis]
    bx = cx - dv[0]*thick/2
    by = cy - dv[1]*thick/2
    bz = cz - dv[2]*thick/2
    ring = _cyl(outer_d/2, thick, bx, by, bz, axis).cut(
           _cyl(inner_d/2, thick, bx, by, bz, axis))
    obj = doc.addObject("Part::Feature", name)
    obj.Shape = ring
    _color_queue.append((obj.Name, color))
    return obj


# ── Kinematic animation helpers ───────────────────────────────────────────────

def gantry(obj):
    _gantry.append((obj.Name, obj.Placement.Base.x))
    return obj


def z_slide(obj):
    _z_slider.append((obj.Name, obj.Placement.Base.z))
    return obj


def set_gantry_x(delta):
    for name, base_x in _gantry:
        o = doc.getObject(name)
        if o is None:
            continue
        pl = o.Placement
        o.Placement = FreeCAD.Placement(
            FreeCAD.Vector(base_x + delta, pl.Base.y, pl.Base.z),
            pl.Rotation)


def set_slider_z(delta):
    for name, base_z in _z_slider:
        o = doc.getObject(name)
        if o is None:
            continue
        pl = o.Placement
        o.Placement = FreeCAD.Placement(
            FreeCAD.Vector(pl.Base.x, pl.Base.y, base_z + delta),
            pl.Rotation)


# ── Explode animation helpers ─────────────────────────────────────────────────

def explode_with(obj, dx=0., dy=0., dz=0.):
    """Register an explosion offset; call after the object has its final placement."""
    _explode_offsets[obj.Name] = (dx, dy, dz)
    _explode_bases[obj.Name]   = FreeCAD.Placement(obj.Placement)
    return obj


def set_explode_factor(t):
    """Move every registered object to assembled_pos + t * offset."""
    for name, (dx, dy, dz) in _explode_offsets.items():
        o = doc.getObject(name)
        if o is None:
            continue
        base = _explode_bases[name]
        o.Placement = FreeCAD.Placement(
            FreeCAD.Vector(base.Base.x + t*dx,
                           base.Base.y + t*dy,
                           base.Base.z + t*dz),
            base.Rotation)


def rerecord_explode_bases():
    """After a kinematic shift, snapshot current placements as new explode bases."""
    for name in list(_explode_offsets.keys()):
        o = doc.getObject(name)
        if o is not None:
            _explode_bases[name] = FreeCAD.Placement(o.Placement)


def _assign_stages():
    """
    Populate _STAGE based on object name patterns.
    Stages match the build guide pages:
      1 = Main frame   (01-main-frame.md)
      2 = Side plates  (02-y-axis.md)
      3 = Gantry beams (03-x-axis-and-z-axis.md, X part)
      4 = Z-axis parts (03-x-axis-and-z-axis.md, Z part)
      5 = Fasteners    (all bolts/nuts/rods)
    """
    _STAGE.clear()
    for name in _explode_offsets:
        if (name.startswith("Frame_") or
                name in ("Rail_Y_Left", "Rail_Y_Right")):
            _STAGE[name] = 1
        elif ("Side_Plate" in name or "Clip" in name):
            _STAGE[name] = 2
        elif (name.startswith("Gantry_Beam") or
              name.startswith("Rail_X")):
            _STAGE[name] = 3
        elif any(tok in name for tok in (
                "Engine_Holder", "Rail_Z", "MGN12H_Block",
                "Router_Clamp", "Top_Stepper", "Engine_Sideways")):
            _STAGE[name] = 4
        else:
            _STAGE[name] = 5   # all bolts, nuts, threaded rods


# ── C.6 — sub-component grouping (I..VI in the metal instructions site) ──────

SUBCOMP_ORDER = ["I", "II", "II_R", "III", "IV", "V", "VI"]
SUBCOMP_TITLES = {
    "I":    "Aluminium frame",
    "II":   "Side plate & Y-axis (left / M20)",
    "II_R": "Side plate & Y-axis (right / M29)",
    "III":  "Gantry & X-axis",
    "IV":   "Engine plate p1of2",
    "V":    "Z-axis drive",
    "VI":   "Engine plate p2of2 & router",
}


def _classify_subcomponent(name: str) -> str:
    """Map an assembly object name to the sub-component it belongs to.

    Rules mirror the docs/metal/01..06 pages so each rendered GIF matches the
    build-guide page it accompanies.  The side-plate group is split into
    II (left / M20) and II_R (right / M29) so a docs page dedicated to
    M20.a–d frames tightly around just the left assembly.
    """
    # I. Aluminium frame
    if (name.startswith("Frame_") or name in ("Rail_Y_Left", "Rail_Y_Right")
            or name.startswith("Bolt_RailY_") or "_Tie_" in name):
        return "I"
    # II_R. Right side plate & Y-axis (mirrored plates + right-clip bolts)
    if (name.endswith("_R") and "Side_Plate" in name) or \
       name.startswith("Bolt_RClip_") or name.startswith("Nut_RClip_"):
        return "II_R"
    # II. Left side plate & Y-axis (M20 series)
    if "Side_Plate" in name or "LClip" in name or name.startswith("Bolt_LClip_") \
       or name.startswith("Nut_LClip_"):
        return "II"
    # III. Gantry & X-axis (includes gantry-beam tie rods)
    if (name.startswith("Gantry_Beam") or name.startswith("Rail_X") or
            name.startswith("Bolt_RailX_") or
            name.startswith("Rod_Beam") or name.startswith("NutR_Beam") or
            "Engine_Sideways" in name):
        return "III"
    # IV. Engine plate p1of2 (p1 plate + MGN12H blocks + block bolts + p1 tab bolts)
    if (name == "Engine_Holder_P1" or "MGN12H_Block" in name or
            name.startswith("Bolt_Blk_") or "Bolt_P1_" in name or
            "Nut_P1_" in name):
        return "IV"
    # V. Z-axis drive (top stepper holder + its bolts)
    if "Top_Stepper" in name or name.startswith("Bolt_TSH_"):
        return "V"
    # VI. Engine plate p2of2 & router
    if (name == "Engine_Holder_P2" or "Router_Clamp" in name or
            name.startswith("Bolt_P2_") or name.startswith("Bolt_RC_") or
            name.startswith("Rail_Z") or name.startswith("Bolt_RailZ_")):
        return "VI"
    # Default catch-all: axis indicator etc.
    return "I"


def _assign_subcomponents():
    """Populate _SUBCOMP for every registered object (C.6)."""
    _SUBCOMP.clear()
    for name in _explode_offsets:
        _SUBCOMP[name] = _classify_subcomponent(name)


def set_staged_assembly(stage_num: int, stage_frac: float):
    """
    Animate a staged build:  earlier stages are assembled (t=0),
    current stage transitions from exploded (t=1) to assembled (t=0)
    as stage_frac goes 0→1, and later stages remain exploded (t=1).
    """
    for name, (dx, dy, dz) in _explode_offsets.items():
        s = _STAGE.get(name, stage_num)
        if s < stage_num:
            t = 0.0
        elif s == stage_num:
            t = 1.0 - stage_frac
        else:
            t = 1.0
        o = doc.getObject(name)
        if o is None:
            continue
        base = _explode_bases[name]
        o.Placement = FreeCAD.Placement(
            FreeCAD.Vector(base.Base.x + t * dx,
                           base.Base.y + t * dy,
                           base.Base.z + t * dz),
            base.Rotation)


# ── Fastener sub-assemblies ───────────────────────────────────────────────────

def _add_p1of2_outtake_bolts(bolt_size: str = 'M5'):
    """
    p1of2 has four TAB EXTENSIONS that protrude beyond the plate's top and
    bottom edges.  Each tab captures one hex nut (default M5, AF=8 mm).  The
    bolt comes from above (top tabs) or below (bottom tabs) — this is the
    'weird way' the bolt/nut assembly sticks out of the plate edge.

    C.1 — bolt axis is vertical (±Z), so the *nut axis is also vertical*.
    In every 2D plan view the nut must therefore appear as a rectangle
    (side profile) rather than a hexagon (face view).  See build_model.py's
    render_plan with orientation='z_up' / 'z_down'.

    C.2 — swap `bolt_size` (e.g. 'M4' vs 'M5') and both bolt+nut+hole
    dimensions update via the FASTENERS catalogue.

    p1of2 world position after placement (x=133, y=369, z=224, yaw=0):
        plate body spans world X[133,143] Y[310,497] Z[88,306]; the front face
        at x=143 carries the four MGN12H blocks, and P1_X=140 is the mid-plane
        of the 10 mm plate thickness (bolt shafts run through it).

    Tab centres (the four nut-carrying tab extensions, local → world):
        TL  world y=337, z=314   TR  world y=402, z=314
        BL  world y=337, z=81    BR  world y=402, z=81
    """
    P1_X = 140          # world X centre of plate
    fs = fastener(bolt_size)
    nut_thk = fs["nut_thk"]
    head_h  = fs["head_h"]
    gap = nut_thk + head_h + 4     # small clearance between head base and nut

    # Top tabs: head above, shaft pointing −Z through tab and into beam above
    for tag, wy in [("TL", 337), ("TR", 402)]:
        wz_nut  = 314
        wz_head = wz_nut + gap
        gantry(explode_with(
            add_bolt(f"Bolt_P1_Top_{tag}_{bolt_size}", P1_X, wy, wz_head,
                     axis='-z', size=bolt_size, shaft_l=22),
            dx=80))
        gantry(explode_with(
            add_nut(f"Nut_P1_Top_{tag}_{bolt_size}", P1_X, wy, wz_nut,
                    axis='+z', size=bolt_size),
            dx=80))

    # Bottom tabs: head below, shaft pointing +Z through tab and into beam below
    for tag, wy in [("BL", 337), ("BR", 402)]:
        wz_nut  = 81
        wz_head = wz_nut - gap
        gantry(explode_with(
            add_bolt(f"Bolt_P1_Bot_{tag}_{bolt_size}", P1_X, wy, wz_head,
                     axis='+z', size=bolt_size, shaft_l=22),
            dx=80))
        gantry(explode_with(
            add_nut(f"Nut_P1_Bot_{tag}_{bolt_size}", P1_X, wy, wz_nut,
                    axis='+z', size=bolt_size),
            dx=80))


def _add_mgn12h_block_bolts(bolt_size: str = 'M3'):
    """
    Each MGN12H block is 13 mm deep (X) × 26 mm wide (Y) × 34 mm tall (Z).
    Blocks are bolted FIXED to p1of2 back face at world X=143 (block X: 143→156).
    Hex-head bolts (default M3): head on outer block face, shaft into p1of2.
    4 bolts per block at ±8 mm Y, ±10 mm Z from block centre.

    C.3 — bolt-head base is offset from the block outer face by exactly
    head_h(size), so the shaft enters the block hole rather than clipping
    into solid metal, regardless of `bolt_size`.
    """
    fs = fastener(bolt_size)
    head_base_x = 143 + 13 + fs["head_h"]   # block outer face + head height
    for blk_y0, blk_z0 in [
        (444, 140),   # LL
        (444, 240),   # LU
        (379, 140),   # RL
        (379, 240),   # RU
    ]:
        bc_y = blk_y0 + 13
        bc_z = blk_z0 + 17
        for n, (dy, dz) in enumerate([(+8,+10),(+8,-10),(-8,+10),(-8,-10)]):
            gantry(explode_with(
                add_bolt(f"Bolt_Blk_{blk_y0}_{blk_z0}_{n}_{bolt_size}",
                         head_base_x, bc_y+dy, bc_z+dz,
                         axis='-x', size=bolt_size, shaft_l=20),
                dx=130))


def _add_p2of2_bolts(bolt_size: str = 'M3'):
    """
    p2of2 (the sliding plate) rides on the four MGN12H block carriages.
    Default M3 bolts through p2of2 front face into each carriage.
    Head on p2of2 front, shaft in −X direction.  These bolts travel with z_slide.
    """
    fs = fastener(bolt_size)
    head_base_x = 166 + fs["head_h"]     # p2of2 front face + head height
    for blk_y0, blk_z0 in [
        (444, 140), (444, 240),
        (379, 140), (379, 240),
    ]:
        bc_y = blk_y0 + 13
        bc_z = blk_z0 + 17
        for n, (dy, dz) in enumerate([(+6,+8),(+6,-8),(-6,+8),(-6,-8)]):
            gantry(z_slide(explode_with(
                add_bolt(f"Bolt_P2_{blk_y0}_{blk_z0}_{n}_{bolt_size}",
                         head_base_x, bc_y+dy, bc_z+dz,
                         axis='-x', size=bolt_size, shaft_l=14),
                dx=200)))


def _add_stepper_holder_bolts(bolt_size: str = 'M5'):
    """
    Top stepper holder bolts down into p1of2 via holes A and B (M40.a).
    Bolt head at top of holder, shaft −Z into plate.  Default M5.
    """
    P1_X = 140
    wz_head = 320
    for tag, wy in [("A", 351), ("B", 388)]:
        gantry(explode_with(
            add_bolt(f"Bolt_TSH_{tag}_{bolt_size}", P1_X, wy, wz_head,
                     axis='-z', size=bolt_size, shaft_l=22),
            dz=70))


def _add_gantry_beam_rods(GZ_L, GZ_U, bolt_size: str = 'M5'):
    """
    Two threaded rods (default M5) run the full Y width (0→793) through the
    gantry beam stack, tying beams and side plates together.  One rod per
    beam level (lower and upper).
    """
    for tag, rx, rz in [
        ("Lo", 85,  GZ_L + 15),
        ("Up", 123, GZ_U + 15),
    ]:
        gantry(explode_with(
            add_bolt(f"Rod_Beam_{tag}_{bolt_size}", rx, -2, rz,
                     axis='+y', size=bolt_size, shaft_l=797),
            dz=90))
        gantry(explode_with(
            add_nut(f"NutR_Beam_{tag}_{bolt_size}", rx, 793, rz,
                    axis='+y', size=bolt_size),
            dz=90))


def _add_side_plate_clip_bolts(bolt_size: str = 'M5'):
    """
    Bolts through the beam-blocker clips into the side plates (Y direction).
    Left clips: bolt head at Y≈−5, shaft going +Y into side plate.
    Right clips: mirrored.  Default M5.
    """
    for clip_x, clip_z, expl_y in [
        (30,  155, -60),   # left back clip
        (30,  180, -60),   # left back clip (second bolt)
        (10,  145, -60),   # left lower-front clip
        (10,  190, -60),   # left upper-front clip
    ]:
        gantry(explode_with(
            add_bolt(f"Bolt_LClip_{clip_x}_{clip_z}_{bolt_size}",
                     clip_x, -4, clip_z,
                     axis='+y', size=bolt_size, shaft_l=28),
            dy=expl_y))
        gantry(explode_with(
            add_nut(f"Nut_LClip_{clip_x}_{clip_z}_{bolt_size}",
                    clip_x, 20, clip_z,
                    axis='+y', size=bolt_size),
            dy=expl_y))
        gantry(explode_with(
            add_bolt(f"Bolt_RClip_{clip_x}_{clip_z}_{bolt_size}",
                     clip_x, 797, clip_z,
                     axis='-y', size=bolt_size, shaft_l=28),
            dy=-expl_y))
        gantry(explode_with(
            add_nut(f"Nut_RClip_{clip_x}_{clip_z}_{bolt_size}",
                    clip_x, 773, clip_z,
                    axis='+y', size=bolt_size),
            dy=-expl_y))


def _add_router_clamp_bolts(bolt_size: str = 'M4'):
    """Bolts clamping the router inside the clamp pair (running in Y).  Default M4."""
    for clamp_z, expl_x in [(160, 240), (195, 240)]:
        for n, cy in enumerate([415, 435]):
            gantry(z_slide(explode_with(
                add_bolt(f"Bolt_RC_{clamp_z}_{n}_{bolt_size}",
                         165, cy, clamp_z,
                         axis='+x', size=bolt_size, shaft_l=20),
                dx=expl_x)))


def _add_frame_rail_bolts(bolt_size: str = 'M3'):
    """
    Complaint I-7: the MGN12H rails on the frame (Rail_Y_Left / _Right) are
    screwed down along their length into the frame top rail, but those screws
    were missing from the render.  Head sits on top of the rail (z ≈ 0), shaft
    runs −Z through the 7 mm rail and into the frame beneath.  Bolts travel with
    their rail's explode offset (dy ±80).  (The matching through-holes are part
    of the rail/frame geometry and are tracked as a FreeCAD design task.)
    """
    fs = fastener(bolt_size)
    for side, ry, expl in [("L", -4.5, -80), ("R", 797.5, +80)]:
        for rx in (200, 350, 500, 650):
            explode_with(
                add_bolt(f"Bolt_RailY_{side}_{rx}_{bolt_size}",
                         rx, ry, fs["head_h"], axis='-z',
                         size=bolt_size, shaft_l=15),
                dy=expl)


def _add_gantry_rail_bolts(bolt_size: str = 'M3'):
    """
    Complaint III-1/2: the screws/bolts that attach the two X-axis rails
    (Rail_X_Upper on beam Upper1, Rail_X_Lower on beam Upper2) to the steel
    gantry beams were missing.  Head on top of each rail, shaft −Z through the
    7 mm rail and into the beam below.  Bolts move with the gantry (X) and share
    the rails' explode lift (dz=100).
    """
    fs = fastener(bolt_size)
    # (tag, rail centre-X, rail top-Z)
    for tag, rcx, rtop in [("U", 132.5, 185), ("L", 162.5, 155)]:
        for ry in (160, 290, 420, 550, 660):
            gantry(explode_with(
                add_bolt(f"Bolt_RailX_{tag}_{ry}_{bolt_size}",
                         rcx, ry, rtop + fs["head_h"], axis='-z',
                         size=bolt_size, shaft_l=22),
                dz=100))


def _add_p2of2_rail_bolts(bolt_size: str = 'M3'):
    """
    Complaint VI (plate rails): the two Z-rails (Rail_Z_Left / _Right) bolt onto
    the p2of2 sliding plate, but the rail bolts themselves were missing.  Head on
    the rail front face (low X), shaft +X through the rail and into p2of2 behind
    it.  Bolts slide with p2of2 (z_slide) and share each rail's explode offsets.
    """
    fs = fastener(bolt_size)
    for side, rcy, expl_y in [("L", 457, +40), ("R", 392, -40)]:
        for rz in (140, 200, 260):
            gantry(z_slide(explode_with(
                add_bolt(f"Bolt_RailZ_{side}_{rz}_{bolt_size}",
                         147 - fs["head_h"], rcy, rz, axis='+x',
                         size=bolt_size, shaft_l=25),
                dy=expl_y, dx=130)))


def _add_frame_tie_rods(rod_size: str = 'M8'):
    """
    Complaint I-1/I-2/I-3: vertical M8 tie rods clamp the upper & lower beam rows
    to the eight corner/mid posts.  Each stud runs +Z through the drilled holes:
    head (bottom stop) below the lower beam with a washer, then a washer + nut on
    top (reached through the Ø16 wrench-access counterbore).  Frame-static (no
    gantry wrap); the rod + washers + nut lift clear (dz) in the explode view.
    """
    posts = [(0,0),(0,763),(870,0),(870,763),(285,0),(285,763),(585,0),(585,763)]
    for vx, vy in posts:
        cx, cy, tag = vx + 15, vy + 15, f"{vx}_{vy}"
        explode_with(add_bolt(f"Rod_Tie_{tag}_{rod_size}", cx, cy, -148,
                              axis='+z', size=rod_size, shaft_l=160), dz=180)
        explode_with(add_washer(f"WasherB_Tie_{tag}_{rod_size}", cx, cy, -141.0,
                                axis='+z', size=rod_size), dz=180)
        explode_with(add_washer(f"WasherT_Tie_{tag}_{rod_size}", cx, cy, 0.8,
                                axis='+z', size=rod_size), dz=180)
        explode_with(add_nut(f"NutT_Tie_{tag}_{rod_size}", cx, cy, 4.75,
                             axis='+z', size=rod_size), dz=180)


# ── Main assembly builder ─────────────────────────────────────────────────────

def _build_assembly(document):
    global doc
    doc = document
    _color_queue.clear()
    _gantry.clear()
    _z_slider.clear()
    _explode_offsets.clear()
    _explode_bases.clear()

    # ── FRAME ─────────────────────────────────────────────────────────────────
    # Complaint I: the frame extrusions were solid blocks with no holes.  They are
    # now hollow 2 mm-wall beams (add_beam) drilled with:
    #   • vertical M8 tie-rod holes (Ø8.5) on the post centre-lines that clamp the
    #     upper/lower beam rows to the corner/mid posts;
    #   • wrench/socket-access counterbores (Ø16, top row) coaxial with each tie
    #     rod so the nut inside the hollow beam can be reached and tightened;
    #   • MGN12H rail mounting holes (Ø3.5) drilled in the rails themselves.
    POST_UX = (15, 300, 600, 885)      # post centre-lines in the long beams' local X
    RAIL_UX = (200, 350, 500, 650)     # rail-screw world-X (matches _add_frame_rail_bolts)

    def _frame_row(sfx, z, top=False):
        tie = [{'axis': 'z', 'u': ux, 'v': 15, 'd': hole_d('M8')} for ux in POST_UX]
        yh = list(tie)
        if top:                        # wrench/socket access from the top face
            yh += [{'axis': 'z', 'u': ux, 'v': 15, 'd': 16, 'depth': 4} for ux in POST_UX]
        explode_with(add_beam(f"Frame_{sfx}_Left_Y",  900, 30, 30,   0,   0, z, holes=yh), dy=-120)
        explode_with(add_beam(f"Frame_{sfx}_Right_Y", 900, 30, 30,   0, 763, z, holes=yh), dy=+120)
        explode_with(add_beam(f"Frame_{sfx}_Front_X",  30, 733, 30,   0,  30, z), dx=-120)
        explode_with(add_beam(f"Frame_{sfx}_Back_X",   30, 733, 30, 870,  30, z), dx=+120)

    _frame_row("Lo", -140)
    _frame_row("Up",  -30, top=True)

    for vx, vy in [(0,0),(0,763),(870,0),(870,763),
                   (285,0),(285,763),(585,0),(585,763)]:
        explode_with(add_beam(f"Frame_Vert_{vx}_{vy}", 30, 30, 80, vx, vy, -110,
                              holes=[{'axis': 'z', 'u': 15, 'v': 15, 'd': hole_d('M8')}]), dz=-120)

    _rail_holes = [{'axis': 'z', 'u': rx - 150, 'v': 4.5, 'd': hole_d('M3')} for rx in RAIL_UX]
    explode_with(add_beam("Rail_Y_Left",  600, 9, 7, 150,  -9, -7,
                          wall=0, holes=_rail_holes, color=COL_RAIL), dy=-80)
    explode_with(add_beam("Rail_Y_Right", 600, 9, 7, 150, 793, -7,
                          wall=0, holes=_rail_holes, color=COL_RAIL), dy=+80)

    # ── AXIS INDICATOR ────────────────────────────────────────────────────────
    AL, AW = 160, 18
    OX, OY, OZ = 0, 793, 0
    add_box("Axis_Z", AW, AW, AL, OX-AW/2, OY-AW/2, OZ,           color=(0.05,0.20,0.95))
    add_box("Axis_X", AL, AW, AW, OX,      OY-AW/2, OZ-AW/2,      color=(0.95,0.10,0.05))
    add_box("Axis_Y", AW, AL, AW, OX-AW/2, OY-AL,   OZ-AW/2,      color=(0.05,0.85,0.10))
    for lbl, lx, ly, lz in [
        ("Z", OX, OY, OZ+AL+15), ("X", OX+AL+15, OY, OZ), ("Y", OX, OY-AL-15, OZ)]:
        ann = doc.addObject("App::Annotation", f"AxisLabel_{lbl}")
        ann.LabelText = [lbl]
        ann.Position  = FreeCAD.Vector(lx, ly, lz)

    # ── GANTRY BEAMS ──────────────────────────────────────────────────────────
    GZ_U, GZ_U2, GZ_L = 148, 118, 78
    GX = 107

    # (c) Same fix as the frame: the three gantry beams were solid blocks — now
    # hollow 2 mm-wall extrusions.  The two rail-carrying beams (Upper1, Upper2)
    # are drilled with the MGN12H X-rail mounting holes (Ø3.4) that pair with the
    # rail screws from _add_gantry_rail_bolts.  The two Y-tie rods run the full
    # width inside the now-hollow beams (open ends), so they need no cross-holes.
    _grail = [{'axis': 'z', 'u': 25.5, 'v': ry + 10, 'd': hole_d('M3')}
              for ry in (160, 290, 420, 550, 660)]
    gantry(explode_with(add_beam("Gantry_Beam_Upper1", 30, 803, 30, GX,    -10, GZ_U,  holes=_grail), dz=100))
    gantry(explode_with(add_beam("Gantry_Beam_Upper2", 30, 803, 30, GX+30, -10, GZ_U2, holes=_grail), dz=100))
    gantry(explode_with(add_beam("Gantry_Beam_Lower",  30, 803, 30, GX-30, -10, GZ_L),  dz=100))
    gantry(explode_with(add_box("Rail_X_Upper", 9, 600, 7, GX+21,      110, GZ_U +30, COL_RAIL), dz=100))
    gantry(explode_with(add_box("Rail_X_Lower", 9, 600, 7, GX+30+21,   110, GZ_U2+30, COL_RAIL), dz=100))

    # ── SIDE PLATES (II) ──────────────────────────────────────────────────────
    SP = f"{METAL}/II_side_plates"
    _sp_files = [
        # (object name, path, M-code)
        ("Side_Plate_Left",              f"{SP}/M20a_left_body/5_models_and_renders/source_rect_metal.step"),
        ("Side_Plate_Back_Clip",         f"{SP}/M20b_back_clip/5_models_and_renders/back_clip.step"),
        ("Side_Plate_Lower_Front_Clip",  f"{SP}/M20cd_front_clips/5_models_and_renders/lower_front_clip.step"),
        ("Side_Plate_Upper_Front_Clip",  f"{SP}/M20cd_front_clips/5_models_and_renders/upper_front_clip.step"),
    ]
    for nm, path in _sp_files:
        gantry(explode_with(add_step(nm, path, x=0, y=0, z=93),       dy=-90))
        gantry(explode_with(add_step_mirror_y(nm+"_R", path, x=0, y=0, z=93), dy=+90))

    # ── Z-AXIS ────────────────────────────────────────────────────────────────
    # p1of2 (M36.a): gantry-fixed back plate.  STEP is regenerated from
    # manual_design/vN.FCStd — see export_manual_steps.py.  If missing,
    # a 6 × 147.5 × 218.3 mm placeholder box is used so the assembly still
    # renders (C.0).
    # The real M36a STEP is authored thin-in-X (10 mm) already, spanning Y (187 mm)
    # and Z (217 mm). Placing it with yaw=0 at (133, 369, 224) lands its front face
    # exactly at x=143 — flush with the four MGN12H blocks (x 143→156) — and makes
    # it span the full block footprint in Y (310→497 ⊇ 379→470) and Z (88→306 ⊇
    # 140→274), with the tab bolts (z 81 / 314) sitting on its top/bottom edges.
    # (The old yaw=90 rotated it thin-in-Y and parked it at the machine's far left,
    # so the blocks/rails/p2of2 — which were always placed for the plate to be here
    # — floated in space. See assembly_description.md "p1of2 orientation (desired)".)
    gantry(explode_with(
        add_step("Engine_Holder_P1",
            f"{METAL}/IV_engine_plate_p1of2/M36a_vertical_plate"
            "/5_models_and_renders/starting_point_rect_metal.step",
            x=133, y=369, z=224, yaw=0,
            fallback_box=(10, 187, 218)),
        dx=80))

    # Z-rails: slide with p2of2
    gantry(z_slide(explode_with(add_box("Rail_Z_Left",  8,12,200, 147,451,100,COL_RAIL), dy=+40,dx=130)))
    gantry(z_slide(explode_with(add_box("Rail_Z_Right", 8,12,200, 147,386,100,COL_RAIL), dy=-40,dx=130)))

    # MGN12H blocks: fixed to p1of2 front face
    for blk_name, by, bz in [
        ("MGN12H_Block_LL", 444, 140),
        ("MGN12H_Block_LU", 444, 240),
        ("MGN12H_Block_RL", 379, 140),
        ("MGN12H_Block_RU", 379, 240),
    ]:
        gantry(explode_with(add_box(blk_name, 13, 26, 34, 143, by, bz, COL_BLOCK), dx=130))

    # p2of2 (M36.b): sliding plate.  Missing STEP falls back to a placeholder
    # so the assembly still animates (C.0).
    VI = f"{METAL}/VI_engine_plate_p2of2_and_router"
    P2 = (f"{VI}/M36b_vertical_plate"
          "/5_models_and_renders/engine_holder_vertical_plate_p2of2.step")
    gantry(z_slide(explode_with(
        add_step("Engine_Holder_P2", P2,
                 x=166, y=425, z=210, yaw=90, pitch=180, roll=-90,
                 fallback_box=(6, 145, 200)),
        dx=190)))

    # Router clamps (M24.a bottom, M24.b top)
    gantry(z_slide(explode_with(
        add_step("Router_Clamp_Bottom",
            f"{VI}/M24a_router_clamp_bottom/5_models_and_renders/router_clamp.step",
            x=170, y=425, z=160),
        dx=240)))
    gantry(z_slide(explode_with(
        add_step("Router_Clamp_Top",
            f"{VI}/M24b_router_clamp_top/5_models_and_renders/router_clamp.step",
            x=170, y=425, z=185),
        dx=240)))

    # ── TOP STEPPER HOLDER (M40.a) ────────────────────────────────────────────
    gantry(explode_with(
        add_step("Top_Stepper_Holder",
            f"{METAL}/V_z_axis_drive/M40a_top_stepper_holder"
            "/5_models_and_renders/engine_holder_top_plate.step",
            x=137, y=490-363.5, z=93+212),
        dz=70))

    # ── ENGINE SIDEWAYS BELT CLAMP (MX.1) ─────────────────────────────────────
    gantry(explode_with(
        add_step("Engine_Sideways_Belt_Clamp",
            f"{METAL}/III_gantry/MX1_engine_sideways_belt_clamp"
            "/5_models_and_renders/engine_sideways_belt_clamp.step",
            x=137, y=-10, z=93+50),
        dy=-80))

    # ── FASTENERS ─────────────────────────────────────────────────────────────
    _add_p1of2_outtake_bolts()
    _add_mgn12h_block_bolts()
    _add_p2of2_bolts()
    _add_stepper_holder_bolts()
    _add_gantry_beam_rods(GZ_L, GZ_U)
    _add_side_plate_clip_bolts()
    _add_router_clamp_bolts()
    _add_frame_rail_bolts()      # I-7:   MGN12H frame-rail screws
    _add_gantry_rail_bolts()     # III-1/2: X-rail → gantry-beam screws
    _add_p2of2_rail_bolts()      # VI:    Z-rail → p2of2 mounting bolts
    _add_frame_tie_rods()        # I-1/2/3: vertical tie rods + washers + nuts

    # C.4 — attach the thread spec to each fastener as a FreeCAD label so the
    # BOM export and any downstream reader can inspect it without inferring
    # from the object name.
    for obj_name, spec in _THREAD_SPEC.items():
        obj = doc.getObject(obj_name)
        if obj is None:
            continue
        try:
            obj.Label = f"{obj_name} — {spec}"
        except Exception:
            pass

    doc.recompute()


# ── Image post-processing (axis labels) ───────────────────────────────────────

def _rotate_frame(png_path):
    """Rotate 90° CW and draw X/Y/Z labels next to the coloured axis rods."""
    try:
        from PIL import Image, ImageDraw, ImageChops, ImageFont
    except ImportError:
        return

    img = Image.open(png_path).rotate(-90, expand=True).convert("RGB")
    r_ch, g_ch, b_ch = img.split()
    draw = ImageDraw.Draw(img)

    font = None
    for _fp in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/run/current-system/sw/share/fonts/truetype/DejaVuSans-Bold.ttf"):
        try:
            font = ImageFont.truetype(_fp, 36); break
        except Exception:
            continue
    if font is None:
        try:    font = ImageFont.load_default(size=36)
        except: font = ImageFont.load_default()

    def _mask(ch, lo=None, hi=None):
        if lo is not None and hi is not None:
            return ch.point(lambda v: 255 if lo < v < hi else 0)
        if lo is not None:
            return ch.point(lambda v: 255 if v > lo else 0)
        return ch.point(lambda v: 255 if v < hi else 0)

    def _find_bbox(r_lo=None,r_hi=None,g_lo=None,g_hi=None,b_lo=None,b_hi=None):
        layers = []
        for ch, lo, hi in [(r_ch,r_lo,r_hi),(g_ch,g_lo,g_hi),(b_ch,b_lo,b_hi)]:
            if lo is not None or hi is not None:
                layers.append(_mask(ch, lo, hi))
        if not layers: return None
        combined = layers[0]
        for lyr in layers[1:]:
            combined = ImageChops.multiply(combined, lyr)
        return combined.getbbox()

    axes = [
        ("Z", None,80, None,120, 160,None, "right",  (30,80,220)),
        ("X", 160,None, None,60, None,60,  "right",  (220,30,20)),
        ("Y", None,60, 140,None, None,60,  "bottom", (20,180,30)),
    ]
    for label,r_lo,r_hi,g_lo,g_hi,b_lo,b_hi,tip,fill in axes:
        bb = _find_bbox(r_lo,r_hi,g_lo,g_hi,b_lo,b_hi)
        if bb is None: continue
        left,top,right,bottom = bb
        PAD = 6
        if tip == "right":
            tx, ty = right+PAD, (top+bottom)//2-18
        else:
            tx, ty = (left+right)//2-10, bottom+PAD
        for ox,oy in [(-2,0),(2,0),(0,-2),(0,2)]:
            draw.text((tx+ox,ty+oy), label, font=font, fill=(255,255,255))
        draw.text((tx,ty), label, font=font, fill=fill)

    img.save(png_path)


# ── Shared render utilities ───────────────────────────────────────────────────

def _apply_colours(FreeCADGui):
    gdoc = FreeCADGui.getDocument(doc.Name)
    if gdoc is None:
        FreeCADGui.setActiveDocument(doc.Name)
        time.sleep(0.2)
        gdoc = FreeCADGui.getDocument(doc.Name)

    if gdoc is None:
        print("[render] WARNING: no GUI document — colours skipped", flush=True)
        return

    for obj_name, rgb in _color_queue:
        vobj = gdoc.getObject(obj_name)
        if vobj is None: continue
        try: vobj.ShapeColor = rgb
        except: pass
        try: vobj.LineColor = (0.15, 0.15, 0.15)
        except: pass

    for lbl in ("X", "Y", "Z"):
        ann = gdoc.getObject(f"AxisLabel_{lbl}")
        if ann is None: continue
        try: ann.TextColor = (0.0, 0.0, 0.0)
        except: pass
        try: ann.FontSize = 120
        except: pass


def _get_view(FreeCADGui):
    for _ in range(5):
        try:
            v = FreeCADGui.ActiveDocument.ActiveView
            if v is not None:
                return v
        except: pass
        time.sleep(0.5)
    return None


def _camera_theta(frame, total_frames):
    START_A = math.radians(210)
    SWEEP   = math.radians(45)
    t = frame / total_frames
    if   t < 0.25: frac =  t / 0.25
    elif t < 0.75: frac =  1 - 2*(t-0.25)/0.5
    else:          frac = -1 + (t-0.75)/0.25
    return START_A + frac * SWEEP


def _set_camera(view, frame, total_frames, bbox=None):
    """Rotate the camera each frame.  If `bbox` is given, fit the view to that
    fixed box (sub-component render uses this so the camera does not zoom out
    to include hidden objects); otherwise call fitAll()."""
    ELEV = math.radians(35)
    theta = _camera_theta(frame, total_frames)
    ce = math.cos(ELEV)
    try:
        view.setViewDirection((ce*math.cos(theta), ce*math.sin(theta), -math.sin(ELEV)))
        if bbox is not None:
            try:
                view.viewBoundBox(bbox)
            except Exception:
                view.fitAll()
        else:
            view.fitAll()
    except: pass


def _render_frames_to_gif(view, out_gif, frames, fps, W, H,
                           gantry_fn, slider_fn, explode_fn=None):
    """Core frame loop. explode_fn(i) → t ∈ [0,1] or None to skip explode."""
    frame_paths = []
    tmpdir = tempfile.mkdtemp(prefix="cnc_gif_")

    _set_camera(view, 0, frames)
    doc.recompute()
    time.sleep(0.3)

    for i in range(frames):
        set_gantry_x(gantry_fn(i))
        set_slider_z(slider_fn(i))
        if explode_fn is not None:
            set_explode_factor(explode_fn(i))
        doc.recompute()
        _set_camera(view, i, frames)

        png = os.path.join(tmpdir, f"frame_{i:03d}.png")
        view.saveImage(png, W, H, "White")
        _rotate_frame(png)
        frame_paths.append(png)
        info = f"  frame {i+1:02d}/{frames}  x={gantry_fn(i):.0f}  z={slider_fn(i):+.0f}"
        if explode_fn is not None:
            info += f"  t={explode_fn(i):.2f}"
        print(info + f" → {png}", flush=True)

    concat = os.path.join(tmpdir, "frames.txt")
    with open(concat, "w") as f:
        for p in frame_paths:
            f.write(f"file '{p}'\nduration {1/fps:.4f}\n")

    subprocess.run([
        FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", concat,
        "-vf", "split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse",
        "-loop", "0", out_gif,
    ], check=True)
    print(f"[render] GIF saved → {out_gif}", flush=True)


# ── Kinematic render subprocess ───────────────────────────────────────────────

def _render_inner():
    import FreeCADGui
    FRAMES, FPS, W, H = 48, 6, 960, 600
    X_FRONT, X_BACK, Z_BOT, Z_TOP = 13., 517., -80., 80.

    def gantry_fn(i):
        half = FRAMES//2
        return X_FRONT + (X_BACK-X_FRONT)*i/(half-1) if i < half \
               else X_BACK - (X_BACK-X_FRONT)*(i-half)/(half-1)

    def slider_fn(i):
        phase = (i + FRAMES//4) % FRAMES; half = FRAMES//2
        return Z_BOT+(Z_TOP-Z_BOT)*phase/(half-1) if phase < half \
               else Z_TOP-(Z_TOP-Z_BOT)*(phase-half)/(half-1)

    print("[render] Starting FreeCADGui ...", flush=True)
    FreeCADGui.showMainWindow(); time.sleep(1.0)

    doc_obj = FreeCAD.newDocument("CNC_Assembly")
    _build_assembly(doc_obj); time.sleep(0.5)
    _apply_colours(FreeCADGui)

    view = _get_view(FreeCADGui)
    if view is None:
        print("[render] ERROR: no active view", flush=True); return

    try: view.setCameraType("Perspective")
    except: pass

    _render_frames_to_gif(view, GIF_PATH, FRAMES, FPS, W, H,
                          gantry_fn, slider_fn, explode_fn=None)


# ── Explode render subprocess ─────────────────────────────────────────────────

def _render_explode_inner():
    """
    Explode / re-assemble animation:
      Frames  0-11  : hold EXPLODED view (parts spread out), camera rotates
      Frames 12-35  : parts fly IN to assembled position  (t: 1→0)
      Frames 36-47  : hold ASSEMBLED view, camera rotates

    Gantry fixed at mid-travel; Z-slider fixed at rest (delta=0).
    """
    import FreeCADGui
    FRAMES, FPS, W, H = 48, 6, 960, 600
    GANTRY_MID = 265.

    PHASE_HOLD_EXP  = 12   # frames 0..11
    PHASE_ASSEMBLE  = 24   # frames 12..35
    PHASE_HOLD_ASSM = 12   # frames 36..47

    def explode_fn(i):
        if i < PHASE_HOLD_EXP:
            return 1.0
        elif i < PHASE_HOLD_EXP + PHASE_ASSEMBLE:
            return 1.0 - (i - PHASE_HOLD_EXP) / (PHASE_ASSEMBLE - 1)
        else:
            return 0.0

    print("[explode] Starting FreeCADGui ...", flush=True)
    FreeCADGui.showMainWindow(); time.sleep(1.0)

    doc_obj = FreeCAD.newDocument("CNC_Explode")
    _build_assembly(doc_obj); time.sleep(0.5)
    _apply_colours(FreeCADGui)

    # Fix gantry at mid-travel, then re-record explode bases from those positions
    # so that set_explode_factor(0) == assembled-at-mid-travel.
    set_gantry_x(GANTRY_MID)
    set_slider_z(0.)
    doc.recompute()
    rerecord_explode_bases()

    view = _get_view(FreeCADGui)
    if view is None:
        print("[explode] ERROR: no active view", flush=True); return
    try: view.setCameraType("Perspective")
    except: pass

    # gantry_fn returns GANTRY_MID every frame — this keeps the (few) non-registered
    # gantry objects fixed; set_explode_factor overrides all registered objects.
    _render_frames_to_gif(view, EXPLODE_GIF_PATH, FRAMES, FPS, W, H,
                          gantry_fn=lambda i: GANTRY_MID,
                          slider_fn=lambda i: 0.,
                          explode_fn=explode_fn)


# ── Staged assembly render subprocess ────────────────────────────────────────

def _render_staged_inner():
    """
    Stage-by-stage assembly animation (5 build stages, each 8 frames):
      Stage 1  frames  0- 7 : main frame + Y-rails assemble
      Stage 2  frames  8-15 : side plates + clips assemble
      Stage 3  frames 16-23 : gantry beams + X-rails assemble
      Stage 4  frames 24-31 : Z-axis components assemble
      Stage 5  frames 32-39 : all fasteners assemble
      Final    frames 40-47 : fully assembled machine, camera sweep
    Gantry fixed at mid-travel throughout.
    """
    import FreeCADGui
    FRAMES, FPS, W, H = 48, 6, 960, 600
    GANTRY_MID = 265.
    N_STAGES   = 5
    STAGE_FRAMES = 8    # frames per stage
    FINAL_FRAMES = FRAMES - N_STAGES * STAGE_FRAMES   # = 8

    print("[staged] Starting FreeCADGui ...", flush=True)
    FreeCADGui.showMainWindow(); time.sleep(1.0)

    doc_obj = FreeCAD.newDocument("CNC_Staged")
    _build_assembly(doc_obj); time.sleep(0.5)
    _apply_colours(FreeCADGui)

    set_gantry_x(GANTRY_MID)
    set_slider_z(0.)
    doc.recompute()
    rerecord_explode_bases()   # bake mid-travel into explode bases
    _assign_stages()           # map object names → stage numbers

    view = _get_view(FreeCADGui)
    if view is None:
        print("[staged] ERROR: no active view", flush=True); return
    try: view.setCameraType("Perspective")
    except: pass

    def staged_fn(i):
        if i >= N_STAGES * STAGE_FRAMES:
            # final hold: all assembled
            set_staged_assembly(N_STAGES + 1, 1.0)
        else:
            stage = i // STAGE_FRAMES + 1
            frac  = (i % STAGE_FRAMES) / max(STAGE_FRAMES - 1, 1)
            set_staged_assembly(stage, frac)

    frame_paths = []
    tmpdir = tempfile.mkdtemp(prefix="cnc_staged_")
    _set_camera(view, 0, FRAMES)
    staged_fn(0)
    doc.recompute()
    time.sleep(0.3)

    for i in range(FRAMES):
        staged_fn(i)
        doc.recompute()
        _set_camera(view, i, FRAMES)

        png = os.path.join(tmpdir, f"frame_{i:03d}.png")
        view.saveImage(png, W, H, "White")
        _rotate_frame(png)
        frame_paths.append(png)

        stage = min(i // STAGE_FRAMES + 1, N_STAGES + 1)
        frac  = (i % STAGE_FRAMES) / max(STAGE_FRAMES - 1, 1) if i < N_STAGES * STAGE_FRAMES else 1.0
        print(f"  frame {i+1:02d}/{FRAMES}  stage={stage}  frac={frac:.2f} → {png}", flush=True)

    concat = os.path.join(tmpdir, "frames.txt")
    with open(concat, "w") as f:
        for p in frame_paths:
            f.write(f"file '{p}'\nduration {1/FPS:.4f}\n")

    subprocess.run([
        FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", concat,
        "-vf", "split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse",
        "-loop", "0", STAGED_GIF_PATH,
    ], check=True)
    print(f"[staged] GIF saved → {STAGED_GIF_PATH}", flush=True)


# ── Sub-component render subprocess (C.6) ─────────────────────────────────────

def _render_subcomponent_inner(sc: str):
    """
    Exploded-view GIF + MP4 of a single sub-component I..VI.
    Objects not in the requested sub-component are hidden (visibility=False).
    Camera pans while the sub-component explodes → assembles → holds.

    Outputs (into assembly/subcomponents/):
      cnc_subcomponent_<sc>_explode.gif
      cnc_subcomponent_<sc>_explode.mp4
    """
    import FreeCADGui
    FRAMES, FPS, W, H = 36, 6, 800, 600
    GANTRY_MID = 265.

    print(f"[sub {sc}] Starting FreeCADGui ...", flush=True)
    FreeCADGui.showMainWindow(); time.sleep(1.0)

    doc_obj = FreeCAD.newDocument(f"CNC_Sub_{sc}")
    _build_assembly(doc_obj); time.sleep(0.5)
    _apply_colours(FreeCADGui)

    set_gantry_x(GANTRY_MID); set_slider_z(0.); doc.recompute()
    rerecord_explode_bases()
    _assign_subcomponents()

    # hide every object that is not in the requested sub-component
    gdoc = FreeCADGui.getDocument(doc.Name)
    hidden_names: list[str] = []
    for name, group in _SUBCOMP.items():
        if group == sc:
            continue
        vobj = gdoc.getObject(name) if gdoc else None
        if vobj is not None:
            try:
                vobj.Visibility = False
                hidden_names.append(name)
            except Exception: pass
    # hide non-registered helper objects too (axis indicator + labels), so the
    # camera can tightly frame just this sub-component
    for ax in ("Axis_X", "Axis_Y", "Axis_Z",
               "AxisLabel_X", "AxisLabel_Y", "AxisLabel_Z"):
        if gdoc:
            v = gdoc.getObject(ax)
            if v is not None:
                try:
                    v.Visibility = False
                    hidden_names.append(ax)
                except Exception: pass

    view = _get_view(FreeCADGui)
    if view is None:
        print(f"[sub {sc}] ERROR: no active view", flush=True); return
    try: view.setCameraType("Perspective")
    except Exception: pass

    # Compute the bounding box of visible objects at explode-factor t=1
    # (fully exploded — the widest state the animation reaches), so the
    # camera never has to pan/zoom mid-clip.
    set_explode_factor(1.0)
    doc.recompute()
    visible_bbox = None
    visible_objs = [o for o in doc.Objects
                    if getattr(o, "Shape", None) is not None
                    and o.Name not in hidden_names]
    if visible_objs:
        import FreeCAD as _FC
        bb = None
        for o in visible_objs:
            try:
                sbb = o.Shape.BoundBox
                if bb is None:
                    bb = _FC.BoundBox(sbb)
                else:
                    bb.add(sbb)
            except Exception:
                pass
        if bb is not None:
            try:
                pad = max(bb.XLength, bb.YLength, bb.ZLength) * 0.15
                bb.enlarge(pad)
                visible_bbox = bb
            except Exception:
                pass
    set_explode_factor(1.0)  # start of animation is fully exploded

    def explode_fn(i):
        if i < 8:                       # hold exploded, camera rotates
            return 1.0
        if i < 24:                      # assemble (16 frames)
            return 1.0 - (i - 8) / 15.0
        return 0.0                      # hold assembled, camera rotates

    os.makedirs(SUBCOMPONENT_DIR, exist_ok=True)
    out_gif = os.path.join(SUBCOMPONENT_DIR, f"cnc_subcomponent_{sc}_explode.gif")
    out_mp4 = os.path.join(SUBCOMPONENT_DIR, f"cnc_subcomponent_{sc}_explode.mp4")

    frame_paths = []
    tmpdir = tempfile.mkdtemp(prefix=f"cnc_sub_{sc}_")
    _set_camera(view, 0, FRAMES, bbox=visible_bbox)
    doc.recompute(); time.sleep(0.3)

    for i in range(FRAMES):
        set_explode_factor(explode_fn(i))
        doc.recompute()
        _set_camera(view, i, FRAMES, bbox=visible_bbox)
        png = os.path.join(tmpdir, f"frame_{i:03d}.png")
        view.saveImage(png, W, H, "White")
        _rotate_frame(png)
        frame_paths.append(png)
        print(f"  [sub {sc}] frame {i+1:02d}/{FRAMES}  t={explode_fn(i):.2f}", flush=True)

    concat = os.path.join(tmpdir, "frames.txt")
    with open(concat, "w") as f:
        for p in frame_paths:
            f.write(f"file '{p}'\nduration {1/FPS:.4f}\n")

    # GIF
    subprocess.run([
        FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", concat,
        "-vf", "split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse",
        "-loop", "0", out_gif,
    ], check=True)
    # MP4 (C.6.1 — same source frames, H.264 encode)
    subprocess.run([
        FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", concat,
        "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "22", out_mp4,
    ], check=False)   # tolerate missing libx264
    print(f"[sub {sc}] Saved → {out_gif}", flush=True)


# ── Entry point ───────────────────────────────────────────────────────────────

def _sh_which(name):
    import shutil
    return shutil.which(name)


def _main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--render",         action="store_true")
    parser.add_argument("--explode-render", action="store_true")
    parser.add_argument("--staged-render",  action="store_true")
    parser.add_argument("--subcomponent-render", metavar="SC",
                        choices=SUBCOMP_ORDER,
                        help="internal subprocess mode: render one sub-component I..VI")
    parser.add_argument("--subcomponents",  action="store_true",
                        help="produce a GIF+MP4 per sub-component (I..VI) (C.6)")
    parser.add_argument("--explode",        action="store_true",
                        help="skip kinematic GIF, produce explode + staged GIFs only")
    args = parser.parse_args()

    if args.render:
        _render_inner(); return
    if args.explode_render:
        _render_explode_inner(); return
    if args.staged_render:
        _render_staged_inner(); return
    if args.subcomponent_render:
        _render_subcomponent_inner(args.subcomponent_render); return

    # Phase 1: build & save FCStd (no GUI)
    print("[assemble] Building geometry ...", flush=True)
    doc_obj = FreeCAD.newDocument("CNC_Assembly")
    _build_assembly(doc_obj)
    doc_obj.saveAs(FCSTD_PATH)
    print(f"[assemble] Saved → {FCSTD_PATH}", flush=True)
    try:
        import shutil as _sh
        _sh.copyfile(FCSTD_PATH, FCSTD_VERSIONED)
        print(f"[assemble] Versioned copy → {FCSTD_VERSIONED}", flush=True)
    except Exception as _e:
        print(f"[assemble] warning: could not write versioned copy: {_e}", flush=True)

    # Phase 2: render GIFs.  Prefer an existing X display (the AppImage renders
    # fine on the live :0 via XWayland); only spin up an Xvfb if none is present
    # and the binary is available.
    xvfb = None
    display = os.environ.get("DISPLAY")
    if display:
        print(f"[assemble] Rendering on existing DISPLAY={display}", flush=True)
    elif _sh_which("Xvfb"):
        display = ":98"
        print(f"[assemble] No DISPLAY — starting Xvfb on {display} ...", flush=True)
        xvfb = subprocess.Popen(["Xvfb", display, "-screen", "0", "1280x720x24"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1.5)
    else:
        print("[assemble] ERROR: no DISPLAY and no Xvfb available — cannot render",
              flush=True)
        sys.exit(1)
    env = dict(os.environ, DISPLAY=display)

    def _subprocess(flag):
        r = subprocess.run([sys.executable, os.path.abspath(__file__), flag],
                           env=env, check=False)
        if r.returncode != 0:
            print(f"[assemble] Subprocess {flag} exited with {r.returncode}", flush=True)
            sys.exit(r.returncode)

    try:
        if not args.explode:
            print("[assemble] Rendering kinematic GIF ...", flush=True)
            _subprocess("--render")
        print("[assemble] Rendering explode GIF ...", flush=True)
        _subprocess("--explode-render")
        print("[assemble] Rendering staged assembly GIF ...", flush=True)
        _subprocess("--staged-render")
        if args.subcomponents:
            for sc in SUBCOMP_ORDER:
                print(f"[assemble] Rendering sub-component {sc} "
                      f"({SUBCOMP_TITLES[sc]}) ...", flush=True)
                # each sub-component runs in its own subprocess with a
                # positional argument so FreeCAD's global state stays clean
                r = subprocess.run(
                    [sys.executable, os.path.abspath(__file__),
                     "--subcomponent-render", sc],
                    env=env, check=False)
                if r.returncode != 0:
                    print(f"[assemble] Sub-component {sc} exited {r.returncode}",
                          flush=True)
    finally:
        if xvfb is not None:
            xvfb.terminate(); xvfb.wait()

    print(f"[assemble] Done!\n"
          f"  FCStd     → {FCSTD_PATH}\n"
          f"  Kinematic → {GIF_PATH}\n"
          f"  Explode   → {EXPLODE_GIF_PATH}\n"
          f"  Staged    → {STAGED_GIF_PATH}",
          flush=True)
    if args.subcomponents:
        print(f"  Sub-components → {SUBCOMPONENT_DIR}/cnc_subcomponent_*.gif",
              flush=True)


if __name__ == "__main__":
    _main()
