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
    "M6": {"shaft_d": 6.0, "head_d": 10.,  "head_h": 5.0,
           "nut_af": 10.,  "nut_thk": 5.0, "clearance": 6.5, "tap": 5.0},
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

# ── Frame post / tie-rod layout (complaint I) ─────────────────────────────────
# The eight vertical tie rods pass through posts at these X positions on the two
# machine edges (Y = 0 and Y = 763).  The outer pair is inset from the extreme
# corners (CORNER_INSET) so the corners stay clear for the four long HORIZONTAL
# tie rods that run the length of the Left/Right beams and their end hardware.
CORNER_INSET = 60
POST_X = (CORNER_INSET, 285, 585, 900 - 30 - CORNER_INSET)   # (60, 285, 585, 810)
POST_Y = (0, 763)


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


# ── Imported-shape editing (merge / thin / rotate STEP parts in-place) ─────────

def _read_shape(path):
    s = Part.Shape()
    s.read(path)
    return s


def _xform_about_center(shape, core_matrix):
    """Apply `core_matrix` about the shape's own bounding-box centre."""
    c = shape.BoundBox.Center
    m1 = FreeCAD.Matrix(); m1.move(FreeCAD.Vector(-c.x, -c.y, -c.z))
    m2 = FreeCAD.Matrix(); m2.move(FreeCAD.Vector(c.x, c.y, c.z))
    return shape.transformGeometry(m1).transformGeometry(core_matrix).transformGeometry(m2)


def _scale_about_center(shape, sx, sy, sz):
    mm = FreeCAD.Matrix(); mm.scale(sx, sy, sz)
    return _xform_about_center(shape, mm)


def _rotate_about_center(shape, axis, deg):
    mm = FreeCAD.Matrix()
    getattr(mm, {'x': 'rotateX', 'y': 'rotateY', 'z': 'rotateZ'}[axis])(math.radians(deg))
    return _xform_about_center(shape, mm)


def _thin_axis(shape, axis, thickness):
    """Trim a shape to `thickness` mm along `axis`, centred on its mid-plane
    ('cut off the sides').  Best applied while the shape is still axis-aligned
    (before any bake-in rotation), so the slab cut is clean."""
    bb = shape.BoundBox
    dims = [bb.XLength + 2, bb.YLength + 2, bb.ZLength + 2]
    base = [bb.XMin - 1, bb.YMin - 1, bb.ZMin - 1]
    ctr  = [bb.Center.x, bb.Center.y, bb.Center.z]
    i = {'x': 0, 'y': 1, 'z': 2}[axis]
    dims[i] = thickness
    base[i] = ctr[i] - thickness / 2
    slab = Part.makeBox(dims[0], dims[1], dims[2], FreeCAD.Vector(*base))
    return shape.common(slab)


def add_shape_obj(name, shape, x=0., y=0., z=0., yaw=0., pitch=0., roll=0.,
                  mirror_y=None, color=COL_METAL):
    """Register a pre-built Part.Shape (already merged/thinned/rotated) as an
    object, optionally mirrored about world Y=`mirror_y` (for the right side)."""
    s = (shape.mirror(FreeCAD.Vector(0, mirror_y, 0), FreeCAD.Vector(0, 1, 0))
         if mirror_y is not None else shape)
    obj = doc.addObject("Part::Feature", name)
    obj.Shape = s
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


# ── R.3: parameter dimension overlay ──────────────────────────────────────────
# Map an assembly object to the *.params.yaml that drives its source script, so the
# --params flag (view_assembly.sh) can draw a labelled double-arrow for each numeric
# parameter it can locate on the geometry.
_PARAMS_YAML = {
    "Router_Clamp_Top":    "VI_engine_plate_p2of2_and_router/M24b_router_clamp_top/5_models_and_renders/router_clamp.params.yaml",
    "Router_Clamp_Bottom": "VI_engine_plate_p2of2_and_router/M24a_router_clamp_bottom/5_models_and_renders/router_clamp.params.yaml",
    "Engine_Sideways_Belt_Clamp": "III_gantry/MX1_engine_sideways_belt_clamp/5_models_and_renders/engine_sideways_belt_clamp.params.yaml",
    "Top_Stepper_Holder":  "V_z_axis_drive/M40a_top_stepper_holder/5_models_and_renders/engine_holder_top_plate.params.yaml",
}


def _read_params_yaml(path):
    """Parse a flat `NAME: value   # comment` params.yaml.  Returns a list of
    (name, value, axis) where axis is the leading X/Y/Z token of the comment (or None)."""
    import re
    out = []
    with open(path) as f:
        for line in f:
            m = re.match(r"\s*([A-Za-z_]\w*)\s*:\s*(-?\d+(?:\.\d+)?)\s*(#.*)?$", line)
            if not m:
                continue
            cmt = m.group(3) or ""
            am = re.search(r"#\s*([XYZ])\b", cmt)
            out.append((m.group(1), float(m.group(2)), am.group(1) if am else None))
    return out


def _make_dim(doc, tag, p1, p2, p3, label, color=(0.85, 0.15, 0.05)):
    """Draft linear dimension p1→p2 (double arrow), offset onto the line through p3,
    with `label` overriding the shown text.  Returns the dimension object."""
    import Draft
    d = Draft.makeDimension(FreeCAD.Vector(*p1), FreeCAD.Vector(*p2), FreeCAD.Vector(*p3))
    d.Label = tag
    vo = d.ViewObject
    try:
        vo.Override = label + " = $dim"
        vo.Decimals = 0
        vo.FontSize = 9
        vo.ArrowSize = 2
        vo.LineColor = color
        vo.TextColor = color
        vo.ExtLines = 8
    except Exception:
        pass
    return d


def _annotate_params(doc, only_sc=None):
    """R.3: for every object that has a *.params.yaml, draw labelled double-arrow
    dimensions for the parameters that can be located on the geometry — the three
    bounding-box extents (matched to a param by its axis hint + value) and any
    diameter parameter (matched to a circular edge of the same size).  Call this
    AFTER any sub-component filtering so the dimensions are not pruned."""
    drawn = 0
    skipped = []
    for name, rel in _PARAMS_YAML.items():
        obj = doc.getObject(name)
        if obj is None or not getattr(obj, "Shape", None):
            continue
        if only_sc and _classify_subcomponent(name) != only_sc:
            continue
        path = os.path.join(METAL, rel)
        if not os.path.exists(path):
            continue
        params = _read_params_yaml(path)
        bb = obj.Shape.BoundBox
        used = set()

        def take(pred):
            for i, (n, v, a) in enumerate(params):
                if i not in used and pred(n, v, a):
                    used.add(i); return n, v
            return None, None

        # the three overall extents, matched to a param by axis + value ≈ extent
        off = max(12.0, 0.12 * bb.DiagonalLength)
        for axis, ext, (p1, p2, p3) in (
            ("X", bb.XLength, ((bb.XMin, bb.YMin, bb.ZMax), (bb.XMax, bb.YMin, bb.ZMax),
                               ((bb.XMin + bb.XMax) / 2, bb.YMin - off, bb.ZMax))),
            ("Y", bb.YLength, ((bb.XMin, bb.YMin, bb.ZMax), (bb.XMin, bb.YMax, bb.ZMax),
                               (bb.XMin - off, (bb.YMin + bb.YMax) / 2, bb.ZMax))),
            ("Z", bb.ZLength, ((bb.XMax, bb.YMin, bb.ZMin), (bb.XMax, bb.YMin, bb.ZMax),
                               (bb.XMax + off, bb.YMin, (bb.ZMin + bb.ZMax) / 2))),
        ):
            n, v = take(lambda nm, vv, a: a == axis and abs(vv - ext) <= 1.5)
            _make_dim(doc, f"Param_{name}_{axis}", p1, p2, p3, n or axis)
            drawn += 1

        # diameter params → a diameter arrow across the matching circular edge.  Only
        # the large bore is annotated; the small bolt-hole diameters and the
        # offset/pitch params are skipped (they clutter tiny features) — logged so the
        # user can ask for them (they'd need per-feature placement to read cleanly).
        circ = [(e.Curve.Radius, e.Curve.Center) for e in obj.Shape.Edges
                if type(e.Curve).__name__ == "Circle" and abs(e.Curve.Axis.z) > 0.9]
        for i, (n, v, a) in enumerate(params):
            if i in used:
                continue
            if "DIAM" in n.upper() and v >= 20.0:
                hit = next(((r, c) for r, c in circ if abs(2 * r - v) <= 1.5), None)
                if hit is not None:
                    r, c = hit
                    _make_dim(doc, f"Param_{name}_{n}",
                              (c.x, c.y - r, bb.ZMax), (c.x, c.y + r, bb.ZMax),
                              (c.x + off, c.y, bb.ZMax), n)
                    drawn += 1
                    continue
            skipped.append(n)
    print("[params] drew %d dimension(s); not annotated (would clutter / need per-feature "
          "placement): %s" % (drawn, ", ".join(skipped) or "none"), flush=True)


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


# Component-VI p2of2 plate rail parameters (WORLD coords, as placed).  The two
# Z-rails run vertically on the plate's BACK face (X166 — render_improvements VI
# item 1: they were on the front, they belong on the back, facing the gantry);
# the router clamps get the front face instead (item 2).  Shared by the plate
# builder (rail grooves + mounting holes), the rail placement, and the rail
# bolts so the groove, the holes, and the bolts all line up.
_P2_XF, _P2_XB = 156.0, 166.0        # plate front / back face (world X)
_P2_RAIL_YC    = (457.0, 392.0)      # rail centre Y (Left, Right)
_P2_RAIL_Z     = (120.0, 160.0, 200.0, 240.0, 280.0)   # rail-bolt Z positions
_P2_RAIL_W     = 12.0                # rail width (Y)
_P2_RAIL_TX    = 8.0                 # rail thickness in X (the add_box lx dim)
_P2_GROOVE_D   = 3.0                 # rail-groove depth into the back face (X)
_P2_RAIL_X     = 163.0               # rail low-X: bedded 3 mm into the back face
                                     # (166) and standing 5 mm proud (X163→171)


def _build_p2of2_plate(path):
    """Load the M36.b p2of2 vertical plate STEP and apply the component-VI plate
    fixes (render_improvements VI, plate items 1-6), returning the shape in WORLD
    coordinates (placement baked in):
      1-4. rebuild the central outtake as a top-to-bottom stack — a shallow (~3 cm)
           rectangular outtake OPEN at the top edge, then a thin thread slot, then a
           wider bolt-head outtake below;
      5.   CNC a rail groove ("rail river") for each Z-rail on the front face;
      6.   drill the rail mounting holes through the plate (threads = item 7; the
           rail bolts themselves are added by _add_p2of2_rail_bolts, item 8).
    """
    shape = Part.Shape(); shape.read(path)
    pl = FreeCAD.Placement(FreeCAD.Vector(166.0, 425.0, 210.0),
                           FreeCAD.Rotation(90.0, 180.0, -90.0))
    shape = shape.transformShape(pl.Matrix, True)     # bake add_step's placement
    if len(shape.Solids) > 1:
        shape = shape.Solids[0]                        # STEP ships a duplicate solid

    XF, XB = _P2_XF, _P2_XB
    def _xcut(y0, y1, z0, z1):                          # through-X rectangular cutter
        return Part.makeBox(XB - XF + 2, y1 - y0, z1 - z0, FreeCAD.Vector(XF - 1, y0, z0))

    # render_improvements VI items 6/7/8: the M36b STEP ships a full block-bolt mounting
    # system on the front face at THREE Z levels — a bottom cluster of holes + half-moon
    # slots at Z~95 (item 6), and identical 4-hole clusters + rectangular "bolt-holder"
    # recesses at Z145/165 (item 7, lower) and Z255/275 (item 8, upper), left and right.
    # The user wants ALL of it gone.  Fill every void inside these regions by fusing back
    # (region_box − plate).  Done BEFORE the rail grooves/holes are cut, so the wanted
    # rail features that fall inside a region (the Y457/392 groove + the Z160/Z280 rail
    # holes) are simply re-cut afterwards.  region_box spans EXACTLY the plate thickness
    # (XF..XB) so the fill adds no proud slab on either face.
    for (y0, y1, z0, z1) in ((360.0, 490.0,  85.0, 105.0),    # item 6: bottom cluster
                             (378.0, 406.0, 140.0, 170.0),    # item 7: lower-right pattern
                             (445.0, 472.0, 140.0, 170.0),    # item 7: lower-left pattern
                             (378.0, 406.0, 248.0, 300.0),    # item 8: upper-right pattern
                             (445.0, 472.0, 248.0, 300.0)):   # item 8: upper-left pattern
        reg = Part.makeBox(XB - XF, y1 - y0, z1 - z0, FreeCAD.Vector(XF, y0, z0))
        shape = shape.fuse(reg.cut(shape))
    try:
        shape = shape.removeSplitter()   # merge the fill seams BEFORE re-cutting rail
    except Exception:                    # features, else a re-drilled hole fragments
        pass

    # items 1-4: fill the old deep central slot (exact walls Y412.5-437.5, Z145-273.2
    # so the fused faces merge and leave no seam), then cut the new stacked feature.
    shape = shape.fuse(Part.makeBox(XB - XF, 25.0, 128.2, FreeCAD.Vector(XF, 412.5, 145.0)))
    shape = shape.cut(_xcut(412.5, 437.5, 270.0, 301.0))   # 1&3: rect outtake, open top, ~3 cm deep
    shape = shape.cut(_xcut(420.0, 430.0, 228.0, 270.0))   # 4: thin part (bolt thread)
    shape = shape.cut(_xcut(416.0, 434.0, 205.0, 228.0))   # 2&4: wider bolt-head outtake, below

    # item 5: rail grooves (BACK face, _P2_GROOVE_D deep), full rail length in Z.
    gw = _P2_RAIL_W + 1.0
    for yc in _P2_RAIL_YC:
        shape = shape.cut(Part.makeBox(_P2_GROOVE_D, gw, 200.0,
                                       FreeCAD.Vector(XB - _P2_GROOVE_D, yc - gw / 2.0, 100.0)))
    # item 6: rail mounting holes through the plate (Ø3.4, one per rail bolt).
    for yc in _P2_RAIL_YC:
        for rz in _P2_RAIL_Z:
            shape = shape.cut(Part.makeCylinder(1.7, XB - XF + 2,
                              FreeCAD.Vector(XF - 1, yc, rz), FreeCAD.Vector(1, 0, 0)))
    # merge coplanar faces left by the slot-fill fuse so it renders as solid plate
    # (no phantom rectangle seam) rather than showing the fused box's outline.
    try:
        shape = shape.removeSplitter()
    except Exception:
        pass
    return shape


def _add_p2of2_bolts(bolt_size: str = 'M3'):
    """
    p2of2 (the sliding plate) rides on the four MGN12H block carriages.

    render_improvements VI items 7 & 8: ALL of the p2of2→block bolts were removed —
    the lower row (Bolt_P2_*_140) in item 7 and the upper row (Bolt_P2_*_240) in item 8,
    together with their plate holes / "bolt-holder" recesses (filled in
    _build_p2of2_plate).  Kept as a no-op so the fastener call site stays uniform.
    """
    return


# Component-V stepper-plate feature positions (WORLD coords, as placed at
# x=137, y=126.5, z=305).  The central oval outtake is centred at Y=490.1; the
# 4 stepper slots sit symmetrically above/below it at these X/Y.  Shared by the
# plate builder (cuts the slots) and _add_stepper_holder_bolts (one bolt each).
_TSH_SLOT_X  = (234.75, 273.75)
_TSH_SLOT_Y  = (474.3, 505.9)        # 474.3 = mirror of 505.9 about the oval Y490.1
_TSH_SLOT_W  = 5.6                    # slot width Ø (matches the existing 2 slots)
_TSH_SLOT_HALFLEN = 9.75             # slot half-length in X (ends ±this from centre)
_TSH_FLANGE_X = 322.0                # X of the 5 flange-bar holes (bar spans X310.9-333.3)


def _build_stepper_plate(path):
    """Load the M40.a top-stepper plate STEP and apply the component-V fixes,
    returning the shape in WORLD coordinates (placement baked in):
      - remove the 6 small surrounding round holes near the slots (item 6);
      - add 2 more stepper slots below the central oval so there are 4 total,
        symmetric about the oval (item 5);
      - drill 5 holes in the flange bar (item 1: two outer clamp holes for
        component IV's top bolts; item 3: two gear-plate bolt holes + one
        central vertical-thread pass-through) (items 1 & 3).
    The central oval outtake (item 4) is left untouched."""
    ZC, ZT = 305.0, 311.0                       # plate bottom / top (world Z)
    sh = _read_shape(path)
    _tm = FreeCAD.Matrix(); _tm.move(FreeCAD.Vector(137.0, 490.0 - 363.5, 93.0 + 212.0))
    sh = sh.transformShape(_tm, True)           # bake placement into geometry

    def _zhole(cx, cy, d):
        return Part.makeCylinder(d / 2, ZT - ZC + 2, FreeCAD.Vector(cx, cy, ZC - 1))

    def _zplug(cx, cy, d):                       # solid disc that fills an existing hole
        return Part.makeCylinder(d / 2, ZT - ZC, FreeCAD.Vector(cx, cy, ZC))

    def _slot(cx, cy):                           # rounded X-slot cutter
        r, hl = _TSH_SLOT_W / 2, _TSH_SLOT_HALFLEN
        body = Part.makeBox(2 * hl, _TSH_SLOT_W, ZT - ZC + 2,
                            FreeCAD.Vector(cx - hl, cy - r, ZC - 1))
        return body.fuse([Part.makeCylinder(r, ZT - ZC + 2, FreeCAD.Vector(cx - hl, cy, ZC - 1)),
                          Part.makeCylinder(r, ZT - ZC + 2, FreeCAD.Vector(cx + hl, cy, ZC - 1))])

    # item 6: fill the small surrounding round holes (4× Ø3.6, 2× Ø5.6)
    for cx, cy, d in [(219.3, 474.6, 4.0), (289.3, 474.6, 4.0),
                      (219.3, 505.6, 4.0), (289.3, 505.6, 4.0),
                      (221.8, 511.5, 6.0), (286.8, 511.5, 6.0)]:
        sh = sh.fuse(_zplug(cx, cy, d))

    # item 5: add the lower two slots (the upper two, at Y505.9, come from the STEP)
    for cx in _TSH_SLOT_X:
        sh = sh.cut(_slot(cx, 474.3))

    # items 1 & 3: five holes in the flange bar
    FX = _TSH_FLANGE_X
    sh = sh.cut(_zhole(FX, 458.0, 5.5))          # item 1: clamp to IV (outer, M5)
    sh = sh.cut(_zhole(FX, 522.0, 5.5))          # item 1: clamp to IV (outer, M5)
    sh = sh.cut(_zhole(FX, 478.0, 3.4))          # item 3: gear-plate bolt (M3)
    sh = sh.cut(_zhole(FX, 502.0, 3.4))          # item 3: gear-plate bolt (M3)
    sh = sh.cut(_zhole(FX, 490.0, 10.0))         # item 3: vertical-thread pass-through
    return sh


def _add_stepper_holder_bolts(bolt_size: str = 'M5'):
    """
    Four stepper-mount bolts (item 7, M40.a), one through each of the plate's
    four slots, pointing −Z down into the stepper motor below.  Head sits on the
    plate top, shaft runs through the slot and into the stepper.  (Replaces the
    old two bolts, which floated off the plate.)
    """
    for wx in _TSH_SLOT_X:
        for wy in _TSH_SLOT_Y:
            gantry(explode_with(
                add_bolt(f"Bolt_TSH_{int(round(wx))}_{int(round(wy))}_{bolt_size}",
                         wx, wy, 316.0, axis='-z', size=bolt_size, shaft_l=28),
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


# Router-clamp placement (WORLD).  render_improvements VI item 2: the clamps mount
# flush AGAINST the plate's FRONT face (X156), not against the rails (now on the
# back) and not floating out in space.  The clamp's raw +X edge is at local +55, so
# _RC_X = 156 − 55 = 101 lands that edge exactly on the front face.  The two clamps
# are 30 mm (3 cm) further apart than before — the bottom one dropped.
_RC_X     = 101.0        # clamp centre X → back (high-X) edge seats on X156 (item 2)
_RC_Z_BOT = 130.0        # bottom clamp (was 160 — dropped 30 mm / 3 cm)
_RC_Z_TOP = 185.0        # top clamp


# Router-clamp plate-mount feature (render_improvements VI items 3/4/5).  The STEP
# already carries ONE X-through mount hole (Router_Clamp.Edge5, r3.25) at Y470.5 that
# bolts the clamp to the plate FRONT face; its mirror on the RIGHT side (near Edge1,
# Y375) is missing (items 4 & 5), as is a rectangular take-out to seat the bolt head
# (item 3).  Y379.5 = mirror of 470.5 about the clamp centre Y425.  Shared by the clamp
# builder (cuts hole + take-out) and _add_router_clamp_bolts (adds the bolts).
_RC_MOUNT_YR  = 425.0 - (470.5 - 425.0)   # 379.5 — the added RIGHT-side mount hole
_RC_MOUNT_YL  = 470.5                      # the STEP's existing LEFT-side mount hole
_RC_MOUNT_D   = 6.5                        # matches the STEP hole Edge5 (r3.25)
_RC_POCKET    = (5.0, 14.0, 14.0)          # take-out (X depth into slit face, Y, Z)
_RC_BORE_R    = 32.5                        # router bore radius (from the STEP)
_RC_BORE_Y0   = 433.0                       # STEP bore centre Y (off-centre by +8)
_RC_BORE_Y1   = 425.0                       # recentred bore Y (item 11) = clamp centre


def _build_router_clamp(path, wz):
    """Load a router-clamp STEP (M24.a/b) placed ON the front of the p2of2 plate,
    and add a SECOND saw slit opposite the existing one so the ring is cut into two
    halves (the router can be set in between).  Then add the plate-mount features
    (render_improvements VI items 3/4/5): mirror the STEP's X-through mount hole
    (Edge5 @ Y470.5) onto the missing right side (Y379.5) and cut a rectangular
    take-out in the clamp's FRONT face to seat that bolt's head.  Returns a WORLD-coord
    shape.  The STEP already carries one slit from its BACK edge to the bore; the
    second slit is mirrored to the FRONT edge at the X centre."""
    shape = Part.Shape(); shape.read(path)
    pl = FreeCAD.Placement(FreeCAD.Vector(_RC_X, 425.0, wz), FreeCAD.Rotation())
    shape = shape.transformShape(pl.Matrix, True)
    b = shape.BoundBox
    xc = (b.XMin + b.XMax) / 2.0
    xf, xb = b.XMin, b.XMax                        # clamp front (X46) / plate-side (X156)
    zc = wz

    # item 11: the STEP bore (router outtake) sits at Y433 — +8 mm off the clamp centre
    # Y425 ("to the left").  Recentre it in −Y.  Done while the clamp is still ONE solid:
    # fill the old bore with a BOX (item 12 — a box shares no cylinder face with the old
    # bore wall, so removeSplitter can erase that wall instead of leaving a seam arc that
    # a coincident cylinder fill would), then re-cut the bore 8 mm lower.
    _bf = _RC_BORE_R + 2.0
    shape = shape.fuse(Part.makeBox(2 * _bf, 2 * _bf, b.ZLength,   # exact thickness, no
                       FreeCAD.Vector(xc - _bf, _RC_BORE_Y0 - _bf, b.ZMin)))  # proud bumps
    try:
        shape = shape.removeSplitter()   # erase the old bore wall before re-cutting
    except Exception:
        pass
    shape = shape.cut(Part.makeCylinder(_RC_BORE_R, b.ZLength + 2,
                      FreeCAD.Vector(xc, _RC_BORE_Y1, b.ZMin - 1)))

    # Saw slit: FULL height (top→bottom) at the X centre so the ring is cut into two
    # fully-separate halves (front + plate-side) regardless of where the bore sits.
    shape = shape.cut(Part.makeBox(6.0, b.YLength + 1.0, b.ZLength + 2.0,
                                   FreeCAD.Vector(xc - 3.0, b.YMin - 0.5, b.ZMin - 1.0)))

    # items 4 & 5: the missing right-side X-through mount hole (mirror of Edge5).
    shape = shape.cut(Part.makeCylinder(
        _RC_MOUNT_D / 2.0, xb - xf + 2.0,
        FreeCAD.Vector(xf - 1.0, _RC_MOUNT_YR, zc), FreeCAD.Vector(1, 0, 0)))
    # items 3 & 10: the bolt take-outs sit in the PLATE-SIDE (high-X) half, at BOTH of
    # its slit-side corners (the two mount-bolt Y's).  xc+3 is that half's slit face; the
    # 14 mm-wide pocket reaches each Y end so it reads as a corner notch.
    pdx, pdy, pdz = _RC_POCKET
    for ym in (_RC_MOUNT_YR, _RC_MOUNT_YL):
        shape = shape.cut(Part.makeBox(
            pdx, pdy, pdz, FreeCAD.Vector(xc + 3.0, ym - pdy / 2.0, zc - pdz / 2.0)))
    try:
        shape = shape.removeSplitter()   # merge the bore-move crescent seam (Y433 arc)
    except Exception:
        pass
    return shape


def _add_router_clamp_bolts(bolt_size: str = 'M4'):
    """Cross-bolt that squeezes each split clamp's two halves together — one across the
    slit, above the bore, clear of it.  Runs in X across the slit gap; slides with p2of2.
    (render_improvements VI item 9 removed the second cross-bolt below the bore @Y385.)

    Also adds the plate-MOUNT bolts (render_improvements VI items 3/4/5): one M6 per
    X-through mount hole (Y379.5 + Y470.5), head at the clamp FRONT face, shaft +X
    through the clamp and into the plate front."""
    xf = _RC_X - 55.0                            # clamp front face (X46)
    for clamp_z in (_RC_Z_BOT, _RC_Z_TOP):
        for cy in (470,):            # single cross-bolt above the bore (item 9)
            gantry(z_slide(explode_with(
                add_bolt(f"Bolt_RC_{int(clamp_z)}_{cy}_{bolt_size}",
                         _RC_X - 7, cy, clamp_z,
                         axis='+x', size=bolt_size, shaft_l=28),
                dx=240)))
        # plate-mount bolts: head at the front face, shaft +X through into the plate
        for cy in (_RC_MOUNT_YR, _RC_MOUNT_YL):
            gantry(z_slide(explode_with(
                add_bolt(f"Bolt_RC_Mount_{int(clamp_z)}_{int(cy)}_M6",
                         xf, cy, clamp_z, axis='+x', size='M6', shaft_l=115),
                dx=240)))


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
    the p2of2 sliding plate, but the rail bolts themselves were missing.  With the
    rails moved to the BACK face (item 1), the head sits on the rail's outer (high
    X) face and the shaft runs −X through the rail and into p2of2 in front of it.
    Bolts slide with p2of2 (z_slide) and share each rail's explode offsets.
    """
    fs = fastener(bolt_size)
    rail_back_x = _P2_RAIL_X + _P2_RAIL_TX          # outer (high-X) face of the rail
    for side, rcy, expl_y in [("L", _P2_RAIL_YC[0], +40), ("R", _P2_RAIL_YC[1], -40)]:
        for rz in _P2_RAIL_Z:
            gantry(z_slide(explode_with(
                add_bolt(f"Bolt_RailZ_{side}_{int(rz)}_{bolt_size}",
                         rail_back_x + fs["head_h"], rcy, rz, axis='-x',
                         size=bolt_size, shaft_l=18),
                dy=expl_y, dx=130)))


def _add_frame_tie_rods(rod_size: str = 'M8'):
    """
    Complaint I-1/2/3 + recess follow-up: vertical M8 tie rods clamp the upper &
    lower beam rows to the eight posts (POST_X × POST_Y).  Hardware is RECESSED so
    the thread never protrudes past the bars: the head sits inside the lower beam
    (above z=-140) and the top washer + nut sink into the upper beam (below z=0),
    reached through the Ø16 wrench hole.  The washers don't fit through that hole,
    so they slide in from the beam end — modelled by exploding them along X toward
    the nearest open end while the rod + nut lift (dz).  Frame-static (no gantry).
    """
    for vx in POST_X:
        for vy in POST_Y:
            cx, cy, tag = vx + 15, vy + 15, f"{vx}_{vy}"
            wdx = -110 if cx < 450 else 110          # washers slide out the nearest end
            explode_with(add_bolt(f"Rod_Tie_{tag}_{rod_size}", cx, cy, -137,
                                  axis='+z', size=rod_size, shaft_l=128), dz=180)
            explode_with(add_washer(f"WasherB_Tie_{tag}_{rod_size}", cx, cy, -130,
                                    axis='+z', size=rod_size), dx=wdx)
            explode_with(add_washer(f"WasherT_Tie_{tag}_{rod_size}", cx, cy, -2.9,
                                    axis='+z', size=rod_size), dx=wdx)
            explode_with(add_nut(f"NutT_Tie_{tag}_{rod_size}", cx, cy, -7.2,
                                 axis='+z', size=rod_size), dz=180)


def _add_frame_side_rods(rod_size: str = 'M8'):
    """
    Complaint A.1-A.4 (rotated 90°): the four long horizontal tie rods run the
    length of the FRONT and BACK beams in Y (both rows) — not the Left/Right beams.
    Those beams carry no vertical rods, so the side rods sit on the beam centre-
    line with no crossing and no Y-offset.  A washer + nut are recessed just inside
    each end (reached through the Ø16 wrench holes); the head anchors the other end.
    Nothing protrudes past the beam ends.  Frame-static; lifts (dz) on explode.
    """
    for rsfx, bz in [("Lo", -140), ("Up", -30)]:
        rz = bz + 15
        for side, rx in [("Front", 15), ("Back", 885)]:
            tag = f"{rsfx}_{side}"
            explode_with(add_bolt(f"RodH_Tie_{tag}_{rod_size}", rx, 36, rz,
                                  axis='+y', size=rod_size, shaft_l=715), dz=200)
            explode_with(add_washer(f"WasherHA_Tie_{tag}_{rod_size}", rx, 43, rz,
                                    axis='+y', size=rod_size), dz=200)
            explode_with(add_washer(f"WasherHB_Tie_{tag}_{rod_size}", rx, 751, rz,
                                    axis='+y', size=rod_size), dz=200)
            explode_with(add_nut(f"NutH_Tie_{tag}_{rod_size}", rx, 757, rz,
                                 axis='+y', size=rod_size), dz=200)


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
    # Complaint I + follow-ups.  Hollow 2 mm-wall extrusions drilled with:
    #   (a) VERTICAL M8 tie-rod holes (Ø9) on the post centre-lines — the outer
    #       pair inset from the corners (POST_X) so the corners stay free;
    #   (b) HORIZONTAL M8 side-rod bores running the full length of the Front/Back
    #       beams in Y (open hollow ends; these beams carry no verticals, so there
    #       is no crossing and the rods sit dead-centre — no offset needed);
    #   (c) Ø16 wrench/socket-access holes over every recessed nut — the vertical
    #       nuts (top row, Left/Right beams); horizontal-rod ends via SIDE holes
    #       (axis Y) in the Left/Right beams, one near each corner (90deg from the
    #       top holes, at a different X, coaxial with the thread reaching it);
    #   (d) MGN12H rail mounting holes (Ø3.4) drilled in the rails themselves.
    POST_UX = tuple(vx + 15 for vx in POST_X)     # vertical-rod centre-lines (local X)
    RAIL_UX = (200, 350, 500, 650)                # rail-screw world-X
    HCORNER_UX = (15, 885)                        # local X of the horizontal-rod ends (corners)

    def _frame_row(sfx, z, vtop=False):
        tie = [{'axis': 'z', 'u': ux, 'v': 15, 'd': hole_d('M8')} for ux in POST_UX]
        # Horizontal side-rod wrench holes: on the SIDE of the long Left/Right beams
        # (axis Y, 90deg from the top vertical-rod holes), one near each corner,
        # coaxial with the horizontal thread end that reaches into that corner.
        side = [{'axis': 'y', 'u': ux, 'v': 15, 'd': 16} for ux in HCORNER_UX]
        lyh, ryh = list(tie) + side, list(tie) + side
        if vtop:                                   # vertical-nut access (top row only)
            vacc = [{'axis': 'z', 'u': ux, 'v': 15, 'd': 16, 'depth': 4} for ux in POST_UX]
            lyh += vacc; ryh += vacc
        explode_with(add_beam(f"Frame_{sfx}_Left_Y",  900, 30, 30,   0,   0, z, holes=lyh), dy=-120)
        explode_with(add_beam(f"Frame_{sfx}_Right_Y", 900, 30, 30,   0, 763, z, holes=ryh), dy=+120)
        explode_with(add_beam(f"Frame_{sfx}_Front_X",  30, 733, 30,   0,  30, z), dx=-120)
        explode_with(add_beam(f"Frame_{sfx}_Back_X",   30, 733, 30, 870,  30, z), dx=+120)

    _frame_row("Lo", -140)
    _frame_row("Up",  -30, vtop=True)

    for vx in POST_X:
        for vy in POST_Y:
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
    # Complaint II: the side plate had FOUR parts (body + back clip + 2 front clips)
    # but should have THREE.  Fixes applied here to the imported STEP geometry:
    #   1-3. the two outer front clips are fused into ONE U-bridge and thinned in Y
    #        from 20 mm to 10 mm;
    #   4.   the beam clamp (back clip) is rotated 90° so its U-outtake grips the beam.
    # (Item 5 — extend it into a taller trapezoid stiffener — follows once the clamp
    #  orientation is confirmed against the reference photo.)
    SP   = f"{METAL}/II_side_plates"
    BODY = f"{SP}/M20a_left_body/5_models_and_renders/source_rect_metal.step"
    BACK = f"{SP}/M20b_back_clip/5_models_and_renders/back_clip.step"
    LOF  = f"{SP}/M20cd_front_clips/5_models_and_renders/lower_front_clip.step"
    UPF  = f"{SP}/M20cd_front_clips/5_models_and_renders/upper_front_clip.step"

    # Tie thread: an M8 stud in X at the mid plate's Y (Y=-3) and world Z≈147 (≈
    # middle of the two upper gantry beams).  It runs in X through the front clamp's
    # U-floor AND the mid plate (whose hole is now bored in X too) — so the clamp is
    # seated to the plate's Y.  Clamp/plate shapes are in LOCAL coords (add_* adds
    # z=93), so world Z147 → local Z54.
    TIE_Y, TIE_ZW, TIE_ZL = -3.0, 147.0, 54.0

    def _xbore(shape, x0, x1, y, zl, d=9.0):
        return shape.cut(Part.makeCylinder(d / 2, x1 - x0,
                         FreeCAD.Vector(x0, y, zl), FreeCAD.Vector(1, 0, 0)))

    # Front-clamp seating + top thread.  The fused front clamp is seated COPLANAR
    # with the mid plate: its two STEP bolt holes (axis X, at Y20, Z143.5 & Z259.1)
    # are brought onto the plate's Y=-3 thread plane, like the beam clamp.  Then two
    # X studs run through it: the existing bottom tie rod (d) through the lower hole
    # and a NEW top thread (e) through the upper hole.  Seating = translate the clamp
    # by dY=-23 (holes 20 → -3) and dZ=+3.5 (lower hole 143.5 → the tie rod's Z147;
    # upper hole → 262.6).  Shapes are LOCAL (z=93 added at placement) so the top
    # thread's local Z is 262.6-93 = 169.6.
    CLAMP_DY, CLAMP_DZ    = -23.0, 3.5
    TOP_Y, TOP_ZW, TOP_ZL = TIE_Y, 262.6, 169.6

    # (a) main body ("mid plate") — two X bores through the plate's depth at Y=-3:
    #     the bottom tie thread at world Z147 (local Z54) and the top clamp thread at
    #     world Z262.6 (local Z169.6), so both X studs run through the plate.
    _body = _xbore(_read_shape(BODY), 78.0, 192.0, TIE_Y, TIE_ZL)
    _body = _xbore(_body, 78.0, 192.0, TOP_Y, TOP_ZL)
    gantry(explode_with(add_shape_obj("Side_Plate_Left", _body, z=93), dy=-90))
    gantry(explode_with(add_shape_obj("Side_Plate_Left_R", _body, z=93, mirror_y=396.5), dy=+90))

    # (b) two upper-beam clamps → ONE fused U-bridge, 10 mm Y, seated coplanar with
    #     the mid plate and fastened by the two X studs (d) bottom and (e) top.
    front = _thin_axis(_read_shape(LOF).fuse(_read_shape(UPF)), 'y', 10.0)
    # The fused clips leave a Z-gap between the two lobes (2 separate rectangles).
    # Fill that gap so they become ONE rectangle; the U-outtakes live inside the
    # lobes and are untouched by the gap fill.
    _lobes = sorted(front.Solids, key=lambda s: s.BoundBox.ZMin)
    if len(_lobes) >= 2:
        _fb = front.BoundBox
        _gz0 = _lobes[0].BoundBox.ZMax
        _gz1 = _lobes[-1].BoundBox.ZMin
        if _gz1 > _gz0:
            front = front.fuse(Part.makeBox(_fb.XLength, _fb.YLength, _gz1 - _gz0,
                                            FreeCAD.Vector(_fb.XMin, _fb.YMin, _gz0)))
    # Seat coplanar with the mid plate: shift (via placement) so the two STEP bolt
    # holes land on the Y=-3 thread plane, lower hole at the tie rod's Z147 (constants).
    # For the mirrored (_R) copy the Y shift flips sign (mirror about Y=396.5).
    gantry(explode_with(add_shape_obj("Side_Plate_Front_Clamp", front,
                        y=CLAMP_DY, z=93 + CLAMP_DZ), dy=-90))
    gantry(explode_with(add_shape_obj("Side_Plate_Front_Clamp_R", front,
                        y=-CLAMP_DY, z=93 + CLAMP_DZ, mirror_y=396.5), dy=+90))

    # (c) front U-fork clamp (U-outtake opening +X), seated at the plate's Y so its
    #     U-floor hole lines up with the plate's X bore for the tie thread
    _CX, _CY, _CZ = 25.0, 10.0, 72.0
    _cx0, _cy0, _cz0 = 54.0, TIE_Y - _CY / 2.0, 18.0
    _clamp = Part.makeBox(_CX, _CY, _CZ, FreeCAD.Vector(_cx0, _cy0, _cz0))
    _nd, _nh = 18.0, 32.0                            # notch depth (X), height (Z, fits 30 mm beam)
    _notch = Part.makeBox(_nd + 1, _CY + 2, _nh,
                          FreeCAD.Vector(_cx0 + _CX - _nd, _cy0 - 1, _cz0 + (_CZ - _nh) / 2.0))
    beam_clamp = _xbore(_clamp.cut(_notch), 50.0, 82.0, TIE_Y, TIE_ZL)
    gantry(explode_with(add_shape_obj("Side_Plate_Beam_Clamp", beam_clamp, z=93), dy=-90))
    gantry(explode_with(add_shape_obj("Side_Plate_Beam_Clamp_R", beam_clamp, z=93, mirror_y=396.5), dy=+90))

    # (d) the tie thread: M8 stud in X through the U-floor and the mid plate, with a
    #     washer + nut at each end
    for _nm, _ex, _ty in [("", -90.0, TIE_Y), ("_R", +90.0, 793.0 - TIE_Y)]:
        _rod = doc.addObject("Part::Feature", f"Side_Plate_TieRod{_nm}")
        _rod.Shape = Part.makeCylinder(4.0, 168.0, FreeCAD.Vector(36.0, _ty, TIE_ZW),
                                       FreeCAD.Vector(1, 0, 0))
        _color_queue.append((_rod.Name, COL_BOLT))
        gantry(explode_with(_rod, dy=_ex))
        gantry(explode_with(add_nut(f"Side_Plate_TieNa{_nm}",    38.0,  _ty, TIE_ZW, axis='+x', size='M8'), dy=_ex))
        gantry(explode_with(add_washer(f"Side_Plate_TieWa{_nm}", 45.0,  _ty, TIE_ZW, axis='+x', size='M8'), dy=_ex))
        gantry(explode_with(add_washer(f"Side_Plate_TieWb{_nm}", 195.0, _ty, TIE_ZW, axis='+x', size='M8'), dy=_ex))
        gantry(explode_with(add_nut(f"Side_Plate_TieNb{_nm}",    202.0, _ty, TIE_ZW, axis='+x', size='M8'), dy=_ex))

    # (e) top clamp thread: an M8 X stud through the mid plate's top bore (a) and the
    #     front clamp's UPPER hole — the analogue of the bottom tie rod (d) for the top
    #     of the unified clamp.  Washer + nut each end.
    for _nm, _ex, _ty in [("", -90.0, TOP_Y), ("_R", +90.0, 793.0 - TOP_Y)]:
        _rod = doc.addObject("Part::Feature", f"Side_Plate_TopRod{_nm}")
        _rod.Shape = Part.makeCylinder(4.0, 140.0, FreeCAD.Vector(70.0, _ty, TOP_ZW),
                                       FreeCAD.Vector(1, 0, 0))
        _color_queue.append((_rod.Name, COL_BOLT))
        gantry(explode_with(_rod, dy=_ex))
        gantry(explode_with(add_nut(f"Side_Plate_TopNa{_nm}",    72.0,  _ty, TOP_ZW, axis='+x', size='M8'), dy=_ex))
        gantry(explode_with(add_washer(f"Side_Plate_TopWa{_nm}", 79.0,  _ty, TOP_ZW, axis='+x', size='M8'), dy=_ex))
        gantry(explode_with(add_washer(f"Side_Plate_TopWb{_nm}", 201.0, _ty, TOP_ZW, axis='+x', size='M8'), dy=_ex))
        gantry(explode_with(add_nut(f"Side_Plate_TopNb{_nm}",    205.0, _ty, TOP_ZW, axis='+x', size='M8'), dy=_ex))

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
    # Rails bedded into their BACK-face grooves (item 1/5): rail low-X at _P2_RAIL_X.
    gantry(z_slide(explode_with(add_box("Rail_Z_Left",  _P2_RAIL_TX,_P2_RAIL_W,200, _P2_RAIL_X,451,100,COL_RAIL), dy=+40,dx=130)))
    gantry(z_slide(explode_with(add_box("Rail_Z_Right", _P2_RAIL_TX,_P2_RAIL_W,200, _P2_RAIL_X,386,100,COL_RAIL), dy=-40,dx=130)))

    # MGN12H blocks: fixed to p1of2 front face
    for blk_name, by, bz in [
        ("MGN12H_Block_LL", 444, 140),
        ("MGN12H_Block_LU", 444, 240),
        ("MGN12H_Block_RL", 379, 140),
        ("MGN12H_Block_RU", 379, 240),
    ]:
        gantry(explode_with(add_box(blk_name, 13, 26, 34, 143, by, bz, COL_BLOCK), dx=130))

    # p2of2 (M36.b): sliding plate.  Rebuilt by _build_p2of2_plate (VI plate items
    # 1-6) — the shape is already in world coords, so it is added at the origin.
    # Missing STEP falls back to a placeholder box so the assembly still animates.
    VI = f"{METAL}/VI_engine_plate_p2of2_and_router"
    P2 = (f"{VI}/M36b_vertical_plate"
          "/5_models_and_renders/engine_holder_vertical_plate_p2of2.step")
    if os.path.exists(P2):
        _p2obj = add_shape_obj("Engine_Holder_P2", _build_p2of2_plate(P2))
    else:
        _p2obj = add_step("Engine_Holder_P2", P2,
                          x=166, y=425, z=210, yaw=90, pitch=180, roll=-90,
                          fallback_box=(6, 145, 200))
    gantry(z_slide(explode_with(_p2obj, dx=190)))

    # Router clamps (M24.a bottom, M24.b top): rebuilt by _build_router_clamp — set
    # ON the front of the plate (not through it) and split into two halves.  Shapes
    # are in world coords, so added at the origin.
    _rcb = f"{VI}/M24a_router_clamp_bottom/5_models_and_renders/router_clamp.step"
    _rct = f"{VI}/M24b_router_clamp_top/5_models_and_renders/router_clamp.step"
    gantry(z_slide(explode_with(
        add_shape_obj("Router_Clamp_Bottom", _build_router_clamp(_rcb, _RC_Z_BOT)), dx=240)))
    gantry(z_slide(explode_with(
        add_shape_obj("Router_Clamp_Top", _build_router_clamp(_rct, _RC_Z_TOP)), dx=240)))

    # ── TOP STEPPER HOLDER (M40.a) ────────────────────────────────────────────
    # Loaded + fixed by _build_stepper_plate (V items 1,3,5,6); the shape is
    # already in world coords, so it is added at the origin (no extra placement).
    _tsh = _build_stepper_plate(
        f"{METAL}/V_z_axis_drive/M40a_top_stepper_holder"
        "/5_models_and_renders/engine_holder_top_plate.step")
    gantry(explode_with(add_shape_obj("Top_Stepper_Holder", _tsh), dz=70))

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
    # (removed _add_side_plate_clip_bolts(): those 4 Y bolts/side sat at X10-30 —
    #  where no clamp is any more — so they just floated in mid air.  The front
    #  clamp is now fastened by the two X studs (d)/(e) in the SIDE PLATES block.)
    _add_router_clamp_bolts()
    _add_frame_rail_bolts()      # I-7:   MGN12H frame-rail screws
    _add_gantry_rail_bolts()     # III-1/2: X-rail → gantry-beam screws
    _add_p2of2_rail_bolts()      # VI:    Z-rail → p2of2 mounting bolts
    _add_frame_tie_rods()        # I-1/2/3: vertical tie rods + washers + nuts (recessed)
    _add_frame_side_rods()       # A.1-A.4: 4 long horizontal tie rods + washers + nuts

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

def _place_reference_triad(gdoc, bb):
    """Resize + move the Axis_* triad (X=red, Y=green, Z=blue) and its labels to a
    corner just outside bounding box `bb`, world-oriented, and make it visible.

    The sub-component render calls this so every GIF carries an X/Y/Z reference
    that turns with the orbiting camera (the triad is world-fixed; as the camera
    sweeps, it shows the current viewing orientation).  Returns the triad's own
    BoundBox so the caller can widen the camera framing to include it.
    """
    L  = max(bb.XLength, bb.YLength, bb.ZLength) * 0.35
    AW = max(3.0, L * 0.08)
    # origin at the min corner, pushed out so the arrows point toward (not into)
    # the part without overlapping it
    ox = bb.XMin - 1.15 * L
    oy = bb.YMin - 1.15 * L
    oz = bb.ZMin
    COLS  = {"Axis_X": (0.95, 0.10, 0.05),
             "Axis_Y": (0.05, 0.85, 0.10),
             "Axis_Z": (0.05, 0.20, 0.95)}
    boxes = {
        "Axis_X": (Part.makeBox(L, AW, AW), FreeCAD.Vector(ox,          oy - AW / 2, oz - AW / 2)),
        "Axis_Y": (Part.makeBox(AW, L, AW), FreeCAD.Vector(ox - AW / 2, oy,          oz - AW / 2)),
        "Axis_Z": (Part.makeBox(AW, AW, L), FreeCAD.Vector(ox - AW / 2, oy - AW / 2, oz)),
    }
    for name, (shp, base) in boxes.items():
        o = doc.getObject(name)
        if o is None:
            continue
        o.Shape = shp
        o.Placement = FreeCAD.Placement(base, FreeCAD.Rotation())
        v = gdoc.getObject(name) if gdoc else None
        if v is not None:
            try:
                v.Visibility = True
                v.ShapeColor = COLS[name]
            except Exception:
                pass
    tips = {"X": FreeCAD.Vector(ox + L + AW, oy, oz),
            "Y": FreeCAD.Vector(ox, oy + L + AW, oz),
            "Z": FreeCAD.Vector(ox, oy, oz + L + AW)}
    for lbl, pos in tips.items():
        a = doc.getObject(f"AxisLabel_{lbl}")
        if a is not None:
            a.Position = pos
        v = gdoc.getObject(f"AxisLabel_{lbl}") if gdoc else None
        if v is not None:
            try:
                v.Visibility = True
                v.FontSize = max(20.0, L * 0.55)
            except Exception:
                pass
    return FreeCAD.BoundBox(ox - AW, oy - AW, oz - AW,
                            ox + L + 2 * AW, oy + L + 2 * AW, oz + L + 2 * AW)


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
    # The X/Y/Z reference triad (Axis_* + labels) is KEPT but resized/moved to this
    # sub-component (done below, once its bbox is known).  Exclude it from the bbox
    # math so it doesn't blow up the framing; hide it for now.
    axis_names = ["Axis_X", "Axis_Y", "Axis_Z",
                  "AxisLabel_X", "AxisLabel_Y", "AxisLabel_Z"]
    for ax in axis_names:
        v = gdoc.getObject(ax) if gdoc else None
        if v is not None:
            try: v.Visibility = False
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
                    and o.Name not in hidden_names
                    and o.Name not in axis_names]
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
    # Place the world-oriented reference triad at a corner of this sub-component
    # and widen the framing to include it.
    if visible_bbox is not None:
        try:
            tb = _place_reference_triad(gdoc, visible_bbox)
            vb = visible_bbox
            visible_bbox = FreeCAD.BoundBox(
                min(vb.XMin, tb.XMin), min(vb.YMin, tb.YMin), min(vb.ZMin, tb.ZMin),
                max(vb.XMax, tb.XMax), max(vb.YMax, tb.YMax), max(vb.ZMax, tb.ZMax))
        except Exception as _e:
            print(f"[sub {sc}] reference triad skipped: {_e}", flush=True)

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
