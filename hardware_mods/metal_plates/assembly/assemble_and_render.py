#!/usr/bin/env python3
"""assemble_and_render.py — build the CNC FCStd assembly and render a GIF.

Coordinate system (same as STL/STEP origins):
  X  →  machine Y direction  (depth: front = 0, back = 900 mm)
  Y  →  machine X direction  (width: left outer = 0, right outer = 793 mm)
  Z  →  vertical             (Z=0 = plate attachment level;
                               frame lives below: Z = -140 → 0)

Origin (0,0,0): front-left corner of the frame at plate-attachment height.

Run from repo root:
    python hardware_mods/metal_plates/assembly/assemble_and_render.py
Outputs:
    hardware_mods/metal_plates/assembly/cnc_assembly.FCStd
    hardware_mods/metal_plates/assembly/cnc_assembly_gif.gif

The render phase is re-invoked as a subprocess with --render so that
FreeCADGui.showMainWindow() is called BEFORE any document is created,
avoiding the "doc created before GUI" crash.
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
import Mesh
import Part

# ── Paths ────────────────────────────────────────────────────────────────────
REPO   = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
           os.path.abspath(__file__)))))
METAL  = os.path.join(REPO, "hardware_mods/metal_plates/examples")
OUT    = os.path.join(REPO, "hardware_mods/metal_plates/assembly")

FCSTD_PATH = os.path.join(OUT, "cnc_assembly.FCStd")
GIF_PATH   = os.path.join(OUT, "cnc_assembly_gif.gif")

# ── Colors (R,G,B floats 0–1) ────────────────────────────────────────────────
COL_EXTRUSION = (0.70, 0.72, 0.75)
COL_RAIL      = (0.82, 0.84, 0.86)
COL_METAL     = (0.55, 0.60, 0.65)
COL_BLOCK     = (0.40, 0.42, 0.45)   # MGN12H blocks — slightly darker

# ── Mutable globals populated by _build_assembly() ───────────────────────────
doc: "FreeCAD.Document | None" = None
_color_queue: list[tuple[str, tuple]] = []
_gantry:    list[tuple[str, float]] = []   # (name, base_x) — Y-axis travel
_z_slider:  list[tuple[str, float]] = []   # (name, base_z) — Z-axis travel


# ── Geometry helpers ──────────────────────────────────────────────────────────

def _place(obj, x: float, y: float, z: float,
           yaw: float = 0, pitch: float = 0, roll: float = 0) -> None:
    obj.Placement = FreeCAD.Placement(
        FreeCAD.Vector(x, y, z),
        FreeCAD.Rotation(yaw, pitch, roll),
    )


def add_box(name: str, lx, ly, lz, x, y, z,
            color=COL_EXTRUSION) -> "FreeCAD.DocumentObject":
    shape = Part.makeBox(lx, ly, lz, FreeCAD.Vector(0, 0, 0))
    obj = doc.addObject("Part::Feature", name)
    obj.Shape = shape
    _place(obj, x, y, z)
    _color_queue.append((obj.Name, color))
    return obj


def add_step(name: str, path: str,
             x=0.0, y=0.0, z=0.0,
             yaw=0.0, pitch=0.0, roll=0.0,
             color=COL_METAL) -> "FreeCAD.DocumentObject":
    shape = Part.Shape()
    shape.read(path)
    obj = doc.addObject("Part::Feature", name)
    obj.Shape = shape
    _place(obj, x, y, z, yaw, pitch, roll)
    _color_queue.append((obj.Name, color))
    return obj


def add_step_mirror_y(name: str, path: str,
                      x=0.0, y=0.0, z=0.0,
                      yaw=0.0, pitch=0.0, roll=0.0,
                      mirror_at_y: float = 396.5,
                      color=COL_METAL) -> "FreeCAD.DocumentObject":
    """Load a STEP and mirror it across the plane Y = mirror_at_y."""
    shape = Part.Shape()
    shape.read(path)
    shape_m = shape.mirror(
        FreeCAD.Vector(0, mirror_at_y, 0),
        FreeCAD.Vector(0, 1, 0),
    )
    obj = doc.addObject("Part::Feature", name)
    obj.Shape = shape_m
    _place(obj, x, y, z, yaw, pitch, roll)
    _color_queue.append((obj.Name, color))
    return obj


def gantry(obj) -> "FreeCAD.DocumentObject":
    """Mark object as part of the Y-travelling gantry."""
    _gantry.append((obj.Name, obj.Placement.Base.x))
    return obj


def z_slide(obj) -> "FreeCAD.DocumentObject":
    """Mark object as part of the Z-travelling slider."""
    _z_slider.append((obj.Name, obj.Placement.Base.z))
    return obj


def set_gantry_x(delta: float) -> None:
    for name, base_x in _gantry:
        o = doc.getObject(name)
        if o is None:
            continue
        pl = o.Placement
        o.Placement = FreeCAD.Placement(
            FreeCAD.Vector(base_x + delta, pl.Base.y, pl.Base.z),
            pl.Rotation,
        )


def set_slider_z(delta: float) -> None:
    for name, base_z in _z_slider:
        o = doc.getObject(name)
        if o is None:
            continue
        pl = o.Placement
        o.Placement = FreeCAD.Placement(
            FreeCAD.Vector(pl.Base.x, pl.Base.y, base_z + delta),
            pl.Rotation,
        )


# ── Assembly builder (called in both phases) ──────────────────────────────────

def _build_assembly(document: "FreeCAD.Document") -> None:
    """Populate `document` with the full CNC geometry."""
    global doc
    doc = document
    _color_queue.clear()
    _gantry.clear()
    _z_slider.clear()

    # ── FRAME ─────────────────────────────────────────────────────────────────
    # Left  Y-rail: Y=0..30    Right Y-rail: Y=763..793
    # Cross-members: Y=30..763 (inner-face gap = 733 mm)
    def _frame_row(suffix: str, z: float) -> None:
        add_box(f"Frame_{suffix}_Left_Y",   900,  30, 30,   0,   0, z)
        add_box(f"Frame_{suffix}_Right_Y",  900,  30, 30,   0, 763, z)
        add_box(f"Frame_{suffix}_Front_X",   30, 733, 30,   0,  30, z)
        add_box(f"Frame_{suffix}_Back_X",    30, 733, 30, 870,  30, z)

    _frame_row("Lo", -140)
    _frame_row("Up",  -30)

    for vx, vy in [(0, 0), (0, 763), (870, 0), (870, 763),
                   (285, 0), (285, 763), (585, 0), (585, 763)]:
        add_box(f"Frame_Vert_{vx}_{vy}", 30, 30, 80, vx, vy, -110)

    add_box("Rail_Y_Left",  600, 9, 7, 150,  -9, -7, COL_RAIL)
    add_box("Rail_Y_Right", 600, 9, 7, 150, 793, -7, COL_RAIL)

    # ── AXIS INDICATOR (3-D, frame-fixed) ─────────────────────────────────────
    # Origin: front-right corner of frame at (X=0, Y=793, Z=0).
    # The vertical column Frame_Vert_0_763 is the post between the two beams.
    # Z (blue) → up, X (red) → machine depth, Y (green) → machine width inward.
    AL, AW = 160, 18   # rod length and cross-section (mm)
    OX, OY, OZ = 0, 793, 0
    add_box("Axis_Z", AW, AW, AL,
            OX - AW/2, OY - AW/2, OZ,
            color=(0.05, 0.20, 0.95))   # blue — up
    add_box("Axis_X", AL, AW, AW,
            OX, OY - AW/2, OZ - AW/2,
            color=(0.95, 0.10, 0.05))   # red — depth (into machine)
    add_box("Axis_Y", AW, AL, AW,
            OX - AW/2, OY - AL, OZ - AW/2,
            color=(0.05, 0.85, 0.10))   # green — width (toward machine centre)

    # ── GANTRY ────────────────────────────────────────────────────────────────
    # Three 803 mm beams running in Y (machine-X direction)
    GZ_U, GZ_U2, GZ_L = 148, 118, 78
    GX = 107   # X of front upper beam; gantry centre ≈ X=137

    gantry(add_box("Gantry_Beam_Upper1", 30, 803, 30, GX,      -10, GZ_U))
    gantry(add_box("Gantry_Beam_Upper2", 30, 803, 30, GX + 30, -10, GZ_U2))
    gantry(add_box("Gantry_Beam_Lower",  30, 803, 30, GX - 30, -10, GZ_L))

    gantry(add_box("Rail_X_Upper", 9, 600, 7, GX + 21,      110, GZ_U  + 30, COL_RAIL))
    gantry(add_box("Rail_X_Lower", 9, 600, 7, GX + 30 + 21, 110, GZ_U2 + 30, COL_RAIL))

    # ── LEFT SIDE PLATE (metal) ───────────────────────────────────────────────
    # Left plate + clips placed at (0,0,93); their STEP coords are world coords.
    SP = f"{METAL}/side_movement"
    gantry(add_step("Side_Plate_Left",
        f"{SP}/P20_left_side_plate/side_plate_left_metal.step",
        x=0, y=0, z=93))
    gantry(add_step("Side_Plate_Back_Clip",
        f"{SP}/P20_left_side_plate_p2of3/5_models_and_renders/back_clip.step",
        x=0, y=0, z=93))
    gantry(add_step("Side_Plate_Lower_Front_Clip",
        f"{SP}/P20_left_side_plate_p3of3/5_models_and_renders/lower_front_clip.step",
        x=0, y=0, z=93))
    gantry(add_step("Side_Plate_Upper_Front_Clip",
        f"{SP}/P20_left_side_plate_p3of3/5_models_and_renders/upper_front_clip.step",
        x=0, y=0, z=93))

    # ── RIGHT SIDE PLATE (mirrored left, metal) ───────────────────────────────
    # Mirrored across Y = 793/2 = 396.5.  Same (0,0,93) placement as left side.
    gantry(add_step_mirror_y("Side_Plate_Right",
        f"{SP}/P20_left_side_plate/side_plate_left_metal.step",
        x=0, y=0, z=93))
    gantry(add_step_mirror_y("Side_Plate_Right_Back_Clip",
        f"{SP}/P20_left_side_plate_p2of3/5_models_and_renders/back_clip.step",
        x=0, y=0, z=93))
    gantry(add_step_mirror_y("Side_Plate_Right_Lower_Front_Clip",
        f"{SP}/P20_left_side_plate_p3of3/5_models_and_renders/lower_front_clip.step",
        x=0, y=0, z=93))
    gantry(add_step_mirror_y("Side_Plate_Right_Upper_Front_Clip",
        f"{SP}/P20_left_side_plate_p3of3/5_models_and_renders/upper_front_clip.step",
        x=0, y=0, z=93))

    # ── Z-AXIS ASSEMBLY ───────────────────────────────────────────────────────
    # p1of2: static back plate, face pointing in X direction.
    # Original STEP local coords: X=358.5..506 (width 147.5mm), Y=-6..0 (6mm
    # thick), Z=-5.5..212.8 (218mm tall).
    # With yaw=-90: local_X→world -Y, local_Y→world X, local_Z→world Z.
    #   tx=137  → face at world X=137 (front face of gantry)
    #   ty=829  → plate width centred at world Y=829-432=397 (gantry centre)
    #   tz=93   → same attachment level as side plates
    MV = f"{METAL}/mid_vertical_movement"
    gantry(add_step("Engine_Holder_P1",
        f"{MV}/engine_holder_vertical_plate_p1of2"
        "/5_models_and_renders/starting_point_rect_metal.step",
        x=137, y=829, z=93, yaw=-90))

    # Two MGN12 rails (fixed to p1of2 face), running vertically (Z).
    # Rail cross-section: 8mm deep (X) × 12mm wide (Y), length 200mm.
    # Rails sit on p1of2 face (X=137), columns at Y=354 and Y=428.
    gantry(add_box("Rail_Z_Left",  8, 12, 200, 137, 354, 100, COL_RAIL))
    gantry(add_box("Rail_Z_Right", 8, 12, 200, 137, 428, 100, COL_RAIL))

    # p2of2: sliding plate, carries the router clamps.
    # Local STEP coords (flat): X=-75..75 (150mm), Y=-130..90 (220mm), Z=0..10.
    # Rotation yaw=90, pitch=90 → local_Z→worldX, local_X→worldY, local_Y→worldZ.
    #   tx=150 → plate back at X=150 (resting on blocks), face at X=160
    #   ty=397 → centred at gantry centre Y=397
    #   tz=210 → Z range = 210+(-130..90) = 80..300, centre≈190
    P2 = (f"{MV}/engine_holder_vertical_plate_p2of2"
          "/5_models_and_renders/engine_holder_vertical_plate_p2of2.step")
    gantry(z_slide(add_step("Engine_Holder_P2", P2,
        x=150, y=397, z=210, yaw=90, pitch=90)))

    # Four MGN12H blocks (fixed to p2of2, slide on the rails).
    # Block: 13mm deep (X) × 26mm wide (Y) × 34mm tall (Z).
    # Two blocks per rail, one at lower Z and one at upper Z.
    for blk_name, by, bz in [
        ("MGN12H_Block_LL", 347, 140),
        ("MGN12H_Block_LU", 347, 240),
        ("MGN12H_Block_RL", 421, 140),
        ("MGN12H_Block_RU", 421, 240),
    ]:
        gantry(z_slide(add_box(blk_name, 13, 26, 34, 137, by, bz, COL_BLOCK)))

    # Router clamps (fixed to p2of2, metal).
    # Centred at Y=397, face at X≈160; Z positions relative to p2of2 centre.
    gantry(z_slide(add_step("Router_Clamp_Bottom",
        f"{MV}/router_clamp_bottom/5_models_and_renders/router_clamp.step",
        x=160, y=397, z=160)))
    gantry(z_slide(add_step("Router_Clamp_Top",
        f"{MV}/router_clamp_top/5_models_and_renders/router_clamp.step",
        x=160, y=397, z=185)))

    # ── TOP STEPPER HOLDER (metal) ────────────────────────────────────────────
    gantry(add_step("Top_Stepper_Holder",
        f"{MV}/top_stepper_holder"
        "/5_models_and_renders/engine_holder_top_plate.step",
        x=0, y=490 - 363.5, z=93 + 212))

    # ── ENGINE SIDEWAYS BELT CLAMP (metal) ────────────────────────────────────
    gantry(add_step("Engine_Sideways_Belt_Clamp",
        f"{METAL}/mid_horizontal_movement/engine_sideways_belt_clamp"
        "/5_models_and_renders/engine_sideways_belt_clamp.step",
        x=137, y=-10, z=93 + 50))

    doc.recompute()


# ── XYZ axis overlay ──────────────────────────────────────────────────────────

def _rotate_frame(png_path: str) -> None:
    """Rotate rendered frame 90° clockwise (960×600 → 600×960 portrait)."""
    import sys as _sys
    _venv_sp = os.path.join(REPO, ".venv/lib/python3.13/site-packages")
    if _venv_sp not in _sys.path:
        _sys.path.insert(0, _venv_sp)
    try:
        from PIL import Image
    except ImportError:
        return
    img = Image.open(png_path)
    img.rotate(-90, expand=True).save(png_path)


# ── Render inner (runs inside Xvfb subprocess) ────────────────────────────────

def _render_inner() -> None:
    import FreeCADGui

    W, H   = 960, 600   # FreeCAD render size; PIL then rotates 90° CW → 600×960
    FRAMES = 48
    FPS    = 6          # half speed

    # Gantry (Y-axis) travel: X offset from natural position
    X_FRONT, X_BACK = 13.0, 517.0

    # Z-slider travel: Z offset from resting position (±80 mm, 160 mm total)
    Z_BOT, Z_TOP = -80.0, 80.0

    def _gantry_travel(i: int) -> float:
        half = FRAMES // 2
        if i < half:
            return X_FRONT + (X_BACK - X_FRONT) * i / (half - 1)
        return X_BACK - (X_BACK - X_FRONT) * (i - half) / (half - 1)

    def _slider_travel(i: int) -> float:
        # Quarter-period offset so Z goes up while gantry moves forward
        phase = (i + FRAMES // 4) % FRAMES
        half  = FRAMES // 2
        if phase < half:
            return Z_BOT + (Z_TOP - Z_BOT) * phase / (half - 1)
        return Z_TOP - (Z_TOP - Z_BOT) * (phase - half) / (half - 1)

    # 1. GUI init FIRST
    print("[render] Starting FreeCADGui ...", flush=True)
    FreeCADGui.showMainWindow()
    time.sleep(1.0)
    print("[render] showMainWindow OK", flush=True)

    # 2. Build assembly with GUI active
    print("[render] Building assembly ...", flush=True)
    document = FreeCAD.newDocument("CNC_Assembly")
    _build_assembly(document)
    print("[render] Assembly built", flush=True)
    time.sleep(0.5)

    # 3. Apply colours
    gdoc = FreeCADGui.getDocument(doc.Name)
    if gdoc is None:
        FreeCADGui.setActiveDocument(doc.Name)
        time.sleep(0.2)
        gdoc = FreeCADGui.getDocument(doc.Name)

    if gdoc is not None:
        for obj_name, rgb in _color_queue:
            vobj = gdoc.getObject(obj_name)
            if vobj is None:
                continue
            try:
                vobj.ShapeColor = rgb
            except Exception:
                pass
            try:
                vobj.LineColor = (0.15, 0.15, 0.15)
            except Exception:
                pass
    else:
        print("[render] WARNING: could not get GUI document — colours skipped", flush=True)

    # 4. Get 3-D viewport
    view = None
    for _attempt in range(5):
        try:
            view = FreeCADGui.ActiveDocument.ActiveView
            if view is not None:
                break
        except Exception:
            pass
        time.sleep(0.5)

    if view is None:
        print("[render] ERROR: no active 3-D view — aborting", flush=True)
        return

    try:
        view.setCameraType("Perspective")
    except Exception:
        pass

    ELEV    = math.radians(35)
    cos_e   = math.cos(ELEV)
    sin_e   = math.sin(ELEV)
    START_A = math.radians(210)
    SWEEP   = math.radians(45)

    def _frame_theta(frame: int) -> float:
        t = frame / FRAMES
        if t < 0.25:
            frac =  t / 0.25
        elif t < 0.75:
            frac =  1 - 2 * (t - 0.25) / 0.5
        else:
            frac = -1 + (t - 0.75) / 0.25
        return START_A + frac * SWEEP

    def _set_camera(frame: int) -> None:
        theta = _frame_theta(frame)
        dx =  cos_e * math.cos(theta)
        dy =  cos_e * math.sin(theta)
        dz = -sin_e
        try:
            view.setViewDirection((dx, dy, dz))
            view.fitAll()
        except Exception:
            pass

    _set_camera(0)
    doc.recompute()
    time.sleep(0.3)
    print("[render] Camera ready", flush=True)

    # 5. Render frames
    frame_paths: list[str] = []
    tmpdir = tempfile.mkdtemp(prefix="cnc_gif_")

    for i in range(FRAMES):
        delta_x = _gantry_travel(i)
        delta_z = _slider_travel(i)
        set_gantry_x(delta_x)
        set_slider_z(delta_z)
        doc.recompute()

        _set_camera(i)

        png = os.path.join(tmpdir, f"frame_{i:03d}.png")
        view.saveImage(png, W, H, "White")
        _rotate_frame(png)   # 90° CW → 600×960 portrait
        frame_paths.append(png)
        print(f"  frame {i+1:02d}/{FRAMES}  gantry_x={delta_x:5.0f}  z={delta_z:+5.0f} → {png}",
              flush=True)

    # 6. Assemble GIF with ffmpeg
    # Frames are 600×960 (portrait) after PIL rotation; skip scaling.
    concat = os.path.join(tmpdir, "frames.txt")
    duration = 1.0 / FPS
    with open(concat, "w") as f:
        for p in frame_paths:
            f.write(f"file '{p}'\n")
            f.write(f"duration {duration:.4f}\n")

    subprocess.run([
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", concat,
        "-vf", "split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse",
        "-loop", "0",
        GIF_PATH,
    ], check=True)

    print(f"[render] GIF saved → {GIF_PATH}", flush=True)


# ── Entry point ───────────────────────────────────────────────────────────────

def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--render", action="store_true",
                        help="(internal) run render phase inside Xvfb")
    args = parser.parse_args()

    if args.render:
        _render_inner()
        return

    # ── Phase 1: build & save FCStd (no GUI needed) ──────────────────────────
    print("[assemble] Building geometry ...", flush=True)
    document = FreeCAD.newDocument("CNC_Assembly")
    _build_assembly(document)
    document.saveAs(FCSTD_PATH)
    print(f"[assemble] Saved → {FCSTD_PATH}", flush=True)

    # ── Phase 2: render GIF inside a fresh Xvfb subprocess ───────────────────
    display = ":98"
    print(f"[assemble] Starting Xvfb on {display} ...", flush=True)
    xvfb = subprocess.Popen(
        ["Xvfb", display, "-screen", "0", "1280x720x24"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    time.sleep(1.5)

    env = dict(os.environ, DISPLAY=display)
    try:
        result = subprocess.run(
            [sys.executable, os.path.abspath(__file__), "--render"],
            env=env,
            check=False,
        )
        if result.returncode != 0:
            print(f"[assemble] Render subprocess exited with code {result.returncode}",
                  flush=True)
            sys.exit(result.returncode)
    finally:
        xvfb.terminate()
        xvfb.wait()

    print(f"[assemble] All done!  GIF → {GIF_PATH}", flush=True)


if __name__ == "__main__":
    _main()
