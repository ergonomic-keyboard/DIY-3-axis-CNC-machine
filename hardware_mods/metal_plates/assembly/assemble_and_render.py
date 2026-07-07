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

FREECAD_LIB = "/nix/store/k7487nfjqcild0rvq6nmsqp250c2lvbk-freecad-1.1.1/lib"
sys.path.insert(0, FREECAD_LIB)

import FreeCAD
import Mesh          # noqa: F401 – keep import so FreeCAD mesh module is loaded
import Part

# ── Paths ─────────────────────────────────────────────────────────────────────
REPO   = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
           os.path.abspath(__file__)))))
METAL  = os.path.join(REPO, "hardware_mods/metal_plates/examples")
OUT    = os.path.join(REPO, "hardware_mods/metal_plates/assembly")

FCSTD_PATH        = os.path.join(OUT, "cnc_assembly.FCStd")
GIF_PATH          = os.path.join(OUT, "cnc_assembly_gif.gif")
EXPLODE_GIF_PATH  = os.path.join(OUT, "cnc_assembly_explode_gif.gif")
STAGED_GIF_PATH   = os.path.join(OUT, "cnc_assembly_staged_gif.gif")

# ── Colors (R,G,B floats 0–1) ─────────────────────────────────────────────────
COL_EXTRUSION = (0.70, 0.72, 0.75)
COL_RAIL      = (0.82, 0.84, 0.86)
COL_METAL     = (0.55, 0.60, 0.65)
COL_BLOCK     = (0.40, 0.42, 0.45)
COL_BOLT      = (0.18, 0.18, 0.22)   # dark steel
COL_NUT       = (0.28, 0.24, 0.10)   # slightly warm / galvanised

# ── Mutable globals ───────────────────────────────────────────────────────────
doc: "FreeCAD.Document | None" = None
_color_queue: list[tuple[str, tuple]] = []
_gantry:    list[tuple[str, float]] = []   # (name, base_x)
_z_slider:  list[tuple[str, float]] = []   # (name, base_z)

# explode animation
_explode_offsets: dict[str, tuple]                  = {}
_explode_bases:   dict[str, "FreeCAD.Placement"]   = {}

# build-stage mapping  (1=frame, 2=side plates, 3=gantry beams, 4=Z-axis, 5=fasteners)
_STAGE: dict[str, int] = {}


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


def add_step(name, path, x=0., y=0., z=0.,
             yaw=0., pitch=0., roll=0., color=COL_METAL):
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
             shaft_d=5., shaft_l=20., head_d=9., head_h=4.,
             color=COL_BOLT):
    """Head base at (bx,by,bz); shaft extends in `axis` direction."""
    dv = _DIR[axis]
    head  = _cyl(head_d/2, head_h, bx, by, bz, axis)
    shaft = _cyl(shaft_d/2, shaft_l,
                 bx + dv[0]*head_h, by + dv[1]*head_h, bz + dv[2]*head_h,
                 axis)
    obj = doc.addObject("Part::Feature", name)
    obj.Shape = head.fuse(shaft)
    _color_queue.append((obj.Name, color))
    return obj


def add_nut(name, cx, cy, cz, axis='+z',
            af=8., thick=4., hole_d=5., color=COL_NUT):
    """Annular nut centred at (cx,cy,cz), axis along `axis`."""
    dv = _DIR[axis]
    r_out = af / math.sqrt(3)
    bx = cx - dv[0]*thick/2
    by = cy - dv[1]*thick/2
    bz = cz - dv[2]*thick/2
    outer = _cyl(r_out,    thick, bx, by, bz, axis)
    inner = _cyl(hole_d/2, thick, bx, by, bz, axis)
    obj = doc.addObject("Part::Feature", name)
    obj.Shape = outer.cut(inner)
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

def _add_p1of2_outtake_bolts():
    """
    p1of2 has four TAB EXTENSIONS that protrude beyond the plate's top and
    bottom edges.  Each tab captures one M5 DIN 934 nut (AF=8 mm).  The bolt
    comes from above (top tabs) or below (bottom tabs) — this is the 'weird way'
    the bolt/nut assembly sticks out of the plate edge.

    p1of2 world positions after placement (x=137, y=-35, z=93, yaw=90):
        world_Y  = local_X − 35
        world_Z  = local_Z + 93
        world_X  ≈ 140  (centre of 6 mm plate thickness)

    Tab centres (from nut_check image, local → world):
        TL  local_x≈372, local_z≈221  →  world y=337, z=314
        TR  local_x≈437, local_z≈221  →  world y=402, z=314
        BL  local_x≈372, local_z≈−12  →  world y=337, z=81
        BR  local_x≈437, local_z≈−12  →  world y=402, z=81
    """
    P1_X = 140          # world X centre of plate

    # Top tabs: head above, shaft pointing −Z through tab and into beam above
    for tag, wy in [("TL", 337), ("TR", 402)]:
        wz_nut  = 314
        wz_head = wz_nut + 14
        gantry(explode_with(
            add_bolt(f"Bolt_P1_Top_{tag}", P1_X, wy, wz_head,
                     axis='-z', shaft_d=5, shaft_l=22, head_d=9, head_h=4),
            dx=80))
        gantry(explode_with(
            add_nut(f"Nut_P1_Top_{tag}", P1_X, wy, wz_nut,
                    axis='+z', af=8, thick=4, hole_d=5),
            dx=80))

    # Bottom tabs: head below, shaft pointing +Z through tab and into beam below
    for tag, wy in [("BL", 337), ("BR", 402)]:
        wz_nut  = 81
        wz_head = wz_nut - 14
        gantry(explode_with(
            add_bolt(f"Bolt_P1_Bot_{tag}", P1_X, wy, wz_head,
                     axis='+z', shaft_d=5, shaft_l=22, head_d=9, head_h=4),
            dx=80))
        gantry(explode_with(
            add_nut(f"Nut_P1_Bot_{tag}", P1_X, wy, wz_nut,
                    axis='+z', af=8, thick=4, hole_d=5),
            dx=80))


def _add_mgn12h_block_bolts():
    """
    Each MGN12H block is 13 mm deep (X) × 26 mm wide (Y) × 34 mm tall (Z).
    Blocks are bolted FIXED to p1of2 back face at world X=143 (block X: 143→156).
    M3 hex-head bolts: head on outer block face (X≈159), shaft into p1of2.
    4 bolts per block at ±8 mm Y, ±10 mm Z from block centre.
    """
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
                add_bolt(f"BoltM3_Blk_{blk_y0}_{blk_z0}_{n}",
                         159, bc_y+dy, bc_z+dz,
                         axis='-x', shaft_d=3, shaft_l=20, head_d=5.5, head_h=3),
                dx=130))


def _add_p2of2_bolts():
    """
    p2of2 (the sliding plate) rides on the four MGN12H block carriages.
    M3 bolts through p2of2 front face into each carriage.
    Head on p2of2 front (X≈169), shaft in −X direction.
    These bolts travel with z_slide.
    """
    for blk_y0, blk_z0 in [
        (444, 140), (444, 240),
        (379, 140), (379, 240),
    ]:
        bc_y = blk_y0 + 13
        bc_z = blk_z0 + 17
        for n, (dy, dz) in enumerate([(+6,+8),(+6,-8),(-6,+8),(-6,-8)]):
            gantry(z_slide(explode_with(
                add_bolt(f"BoltM3_P2_{blk_y0}_{blk_z0}_{n}",
                         169, bc_y+dy, bc_z+dz,
                         axis='-x', shaft_d=3, shaft_l=14, head_d=5.5, head_h=3),
                dx=200)))


def _add_stepper_holder_bolts():
    """
    Top stepper holder bolts down into p1of2 via holes A and B.
    Hole A: local x≈386 → world y=351, z=303
    Hole B: local x≈423 → world y=388, z=303
    Bolt head at top of holder, shaft −Z into plate.
    """
    P1_X = 140
    wz_head = 320
    for tag, wy in [("A", 351), ("B", 388)]:
        gantry(explode_with(
            add_bolt(f"Bolt_TSH_{tag}", P1_X, wy, wz_head,
                     axis='-z', shaft_d=5, shaft_l=22, head_d=9, head_h=4),
            dz=70))


def _add_gantry_beam_rods(GZ_L, GZ_U):
    """
    Two M5 threaded rods run the full Y width (0→793) through the gantry
    beam stack, tying beams and side plates together.
    One rod per beam level (lower and upper).
    """
    for tag, rx, rz in [
        ("Lo", 85,  GZ_L + 15),
        ("Up", 123, GZ_U + 15),
    ]:
        # Rod: head (nut style) at left end (Y=−2), tip at Y=795
        gantry(explode_with(
            add_bolt(f"Rod_Beam_{tag}", rx, -2, rz,
                     axis='+y', shaft_d=5, shaft_l=797, head_d=9, head_h=4),
            dz=90))
        # Right-end nut
        gantry(explode_with(
            add_nut(f"NutR_Beam_{tag}", rx, 793, rz,
                    axis='+y', af=8, thick=4, hole_d=5),
            dz=90))


def _add_side_plate_clip_bolts():
    """
    M5 bolts through the beam-blocker clips into the side plates (Y direction).
    Left clips: bolt head at Y≈−5, shaft going +Y into side plate.
    Right clips: mirrored.
    """
    for clip_x, clip_z, expl_y in [
        (30,  155, -60),   # left back clip
        (30,  180, -60),   # left back clip (second bolt)
        (10,  145, -60),   # left lower-front clip
        (10,  190, -60),   # left upper-front clip
    ]:
        gantry(explode_with(
            add_bolt(f"Bolt_LClip_{clip_x}_{clip_z}",
                     clip_x, -4, clip_z,
                     axis='+y', shaft_d=5, shaft_l=28, head_d=9, head_h=4),
            dy=expl_y))
        gantry(explode_with(
            add_nut(f"Nut_LClip_{clip_x}_{clip_z}",
                    clip_x, 20, clip_z,
                    axis='+y', af=8, thick=4, hole_d=5),
            dy=expl_y))
        # Mirror for right side
        gantry(explode_with(
            add_bolt(f"Bolt_RClip_{clip_x}_{clip_z}",
                     clip_x, 797, clip_z,
                     axis='-y', shaft_d=5, shaft_l=28, head_d=9, head_h=4),
            dy=-expl_y))
        gantry(explode_with(
            add_nut(f"Nut_RClip_{clip_x}_{clip_z}",
                    clip_x, 773, clip_z,
                    axis='+y', af=8, thick=4, hole_d=5),
            dy=-expl_y))


def _add_router_clamp_bolts():
    """M4 bolts clamping the router inside the clamp pair (running in Y)."""
    for clamp_z, expl_x in [(160, 240), (195, 240)]:
        for n, cy in enumerate([415, 435]):
            gantry(z_slide(explode_with(
                add_bolt(f"Bolt_RC_{clamp_z}_{n}",
                         165, cy, clamp_z,
                         axis='+x', shaft_d=4, shaft_l=20, head_d=7, head_h=3.5),
                dx=expl_x)))


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
    def _frame_row(sfx, z):
        explode_with(add_box(f"Frame_{sfx}_Left_Y",   900, 30, 30,   0,   0, z), dy=-120)
        explode_with(add_box(f"Frame_{sfx}_Right_Y",  900, 30, 30,   0, 763, z), dy=+120)
        explode_with(add_box(f"Frame_{sfx}_Front_X",   30,733, 30,   0,  30, z), dx=-120)
        explode_with(add_box(f"Frame_{sfx}_Back_X",    30,733, 30, 870,  30, z), dx=+120)

    _frame_row("Lo", -140)
    _frame_row("Up",  -30)

    for vx, vy in [(0,0),(0,763),(870,0),(870,763),
                   (285,0),(285,763),(585,0),(585,763)]:
        explode_with(add_box(f"Frame_Vert_{vx}_{vy}", 30, 30, 80, vx, vy, -110), dz=-120)

    explode_with(add_box("Rail_Y_Left",  600, 9, 7, 150,  -9, -7, COL_RAIL), dy=-80)
    explode_with(add_box("Rail_Y_Right", 600, 9, 7, 150, 793, -7, COL_RAIL), dy=+80)

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

    gantry(explode_with(add_box("Gantry_Beam_Upper1", 30, 803, 30, GX,      -10, GZ_U),  dz=100))
    gantry(explode_with(add_box("Gantry_Beam_Upper2", 30, 803, 30, GX+30,   -10, GZ_U2), dz=100))
    gantry(explode_with(add_box("Gantry_Beam_Lower",  30, 803, 30, GX-30,   -10, GZ_L),  dz=100))
    gantry(explode_with(add_box("Rail_X_Upper", 9, 600, 7, GX+21,      110, GZ_U +30, COL_RAIL), dz=100))
    gantry(explode_with(add_box("Rail_X_Lower", 9, 600, 7, GX+30+21,   110, GZ_U2+30, COL_RAIL), dz=100))

    # ── SIDE PLATES ───────────────────────────────────────────────────────────
    SP = f"{METAL}/side_movement"
    _sp_files = [
        ("Side_Plate_Left",              f"{SP}/P20_left_side_plate/side_plate_left_metal.step"),
        ("Side_Plate_Back_Clip",         f"{SP}/P20_left_side_plate_p2of3/5_models_and_renders/back_clip.step"),
        ("Side_Plate_Lower_Front_Clip",  f"{SP}/P20_left_side_plate_p3of3/5_models_and_renders/lower_front_clip.step"),
        ("Side_Plate_Upper_Front_Clip",  f"{SP}/P20_left_side_plate_p3of3/5_models_and_renders/upper_front_clip.step"),
    ]
    for nm, path in _sp_files:
        gantry(explode_with(add_step(nm, path, x=0, y=0, z=93),       dy=-90))
        gantry(explode_with(add_step_mirror_y(nm+"_R", path, x=0, y=0, z=93), dy=+90))

    # ── Z-AXIS ────────────────────────────────────────────────────────────────
    MV = f"{METAL}/mid_vertical_movement"

    # p1of2: gantry-fixed back plate
    gantry(explode_with(
        add_step("Engine_Holder_P1",
            f"{MV}/engine_holder_vertical_plate_p1of2"
            "/5_models_and_renders/starting_point_rect_metal.step",
            x=137, y=-35, z=93, yaw=90),
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

    # p2of2: sliding plate
    P2 = (f"{MV}/engine_holder_vertical_plate_p2of2"
          "/5_models_and_renders/engine_holder_vertical_plate_p2of2.step")
    gantry(z_slide(explode_with(
        add_step("Engine_Holder_P2", P2,
                 x=166, y=425, z=210, yaw=90, pitch=180, roll=-90),
        dx=190)))

    # Router clamps
    gantry(z_slide(explode_with(
        add_step("Router_Clamp_Bottom",
            f"{MV}/router_clamp_bottom/5_models_and_renders/router_clamp.step",
            x=170, y=425, z=160),
        dx=240)))
    gantry(z_slide(explode_with(
        add_step("Router_Clamp_Top",
            f"{MV}/router_clamp_top/5_models_and_renders/router_clamp.step",
            x=170, y=425, z=185),
        dx=240)))

    # ── TOP STEPPER HOLDER ────────────────────────────────────────────────────
    gantry(explode_with(
        add_step("Top_Stepper_Holder",
            f"{MV}/top_stepper_holder/5_models_and_renders/engine_holder_top_plate.step",
            x=137, y=490-363.5, z=93+212),
        dz=70))

    # ── ENGINE SIDEWAYS BELT CLAMP ────────────────────────────────────────────
    gantry(explode_with(
        add_step("Engine_Sideways_Belt_Clamp",
            f"{METAL}/mid_horizontal_movement/engine_sideways_belt_clamp"
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

    doc.recompute()


# ── Image post-processing (axis labels) ───────────────────────────────────────

def _rotate_frame(png_path):
    """Rotate 90° CW and draw X/Y/Z labels next to the coloured axis rods."""
    import sys as _sys
    _venv_sp = os.path.join(REPO, ".venv/lib/python3.13/site-packages")
    if _venv_sp not in _sys.path:
        _sys.path.insert(0, _venv_sp)
    try:
        from PIL import Image, ImageDraw, ImageChops, ImageFont
    except ImportError:
        return

    img = Image.open(png_path).rotate(-90, expand=True).convert("RGB")
    r_ch, g_ch, b_ch = img.split()
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype(
            "/run/current-system/sw/share/fonts/truetype/DejaVuSans-Bold.ttf", 36)
    except Exception:
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


def _set_camera(view, frame, total_frames):
    ELEV = math.radians(35)
    theta = _camera_theta(frame, total_frames)
    ce = math.cos(ELEV)
    try:
        view.setViewDirection((ce*math.cos(theta), ce*math.sin(theta), -math.sin(ELEV)))
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
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat,
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
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat,
        "-vf", "split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse",
        "-loop", "0", STAGED_GIF_PATH,
    ], check=True)
    print(f"[staged] GIF saved → {STAGED_GIF_PATH}", flush=True)


# ── Entry point ───────────────────────────────────────────────────────────────

def _main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--render",         action="store_true")
    parser.add_argument("--explode-render", action="store_true")
    parser.add_argument("--staged-render",  action="store_true")
    parser.add_argument("--explode",        action="store_true",
                        help="skip kinematic GIF, produce explode + staged GIFs only")
    args = parser.parse_args()

    if args.render:
        _render_inner(); return
    if args.explode_render:
        _render_explode_inner(); return
    if args.staged_render:
        _render_staged_inner(); return

    # Phase 1: build & save FCStd (no GUI)
    print("[assemble] Building geometry ...", flush=True)
    doc_obj = FreeCAD.newDocument("CNC_Assembly")
    _build_assembly(doc_obj)
    doc_obj.saveAs(FCSTD_PATH)
    print(f"[assemble] Saved → {FCSTD_PATH}", flush=True)

    # Phase 2: render GIFs inside Xvfb subprocesses
    display = ":98"
    print(f"[assemble] Starting Xvfb on {display} ...", flush=True)
    xvfb = subprocess.Popen(["Xvfb", display, "-screen", "0", "1280x720x24"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)
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
    finally:
        xvfb.terminate(); xvfb.wait()

    print(f"[assemble] Done!\n"
          f"  Kinematic → {GIF_PATH}\n"
          f"  Explode   → {EXPLODE_GIF_PATH}\n"
          f"  Staged    → {STAGED_GIF_PATH}",
          flush=True)


if __name__ == "__main__":
    _main()
