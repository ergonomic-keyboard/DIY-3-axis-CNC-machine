#!/usr/bin/env python3
"""assemble_and_render.py — build the CNC FCStd assembly and render a GIF.

Coordinate system (same as STL/STEP origins):
  X  →  machine Y direction  (depth: front = 0, back = 900 mm)
  Y  →  machine X direction  (width: left outer = -10, right outer = 793 mm)
  Z  →  vertical             (Z=0 = plate attachment level;
                               frame lives below: Z = -140 → 0)

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
PLAST  = os.path.join(REPO, "docs/stl_files")
OUT    = os.path.join(REPO, "hardware_mods/metal_plates/assembly")

FCSTD_PATH = os.path.join(OUT, "cnc_assembly.FCStd")
GIF_PATH   = os.path.join(OUT, "cnc_assembly_gif.gif")

# ── Colors (R,G,B floats 0–1) ────────────────────────────────────────────────
COL_EXTRUSION = (0.70, 0.72, 0.75)
COL_RAIL      = (0.82, 0.84, 0.86)
COL_METAL     = (0.55, 0.60, 0.65)
COL_PLASTIC   = (0.12, 0.45, 0.12)

# ── Mutable globals populated by _build_assembly() ───────────────────────────
doc: "FreeCAD.Document | None" = None
_color_queue: list[tuple[str, tuple]] = []
_gantry: list[tuple[str, float]] = []


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


def add_stl(name: str, path: str,
            x=0.0, y=0.0, z=0.0,
            color=COL_PLASTIC) -> "FreeCAD.DocumentObject":
    m = Mesh.Mesh(path)
    obj = doc.addObject("Mesh::Feature", name)
    obj.Mesh = m
    _place(obj, x, y, z)
    _color_queue.append((obj.Name, color))
    return obj


def gantry(obj) -> "FreeCAD.DocumentObject":
    _gantry.append((obj.Name, obj.Placement.Base.x))
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


# ── Assembly builder (called in both phases) ──────────────────────────────────

def _build_assembly(document: "FreeCAD.Document") -> None:
    """Populate `document` with the full CNC geometry."""
    global doc
    doc = document
    _color_queue.clear()
    _gantry.clear()

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

    # ── GANTRY ────────────────────────────────────────────────────────────────
    # Three 803 mm beams running in Y (machine-X direction)
    GZ_U, GZ_U2, GZ_L = 148, 118, 78
    GX = 107   # X of front upper beam; gantry centre ≈ X=137

    gantry(add_box("Gantry_Beam_Upper1", 30, 803, 30, GX,      -10, GZ_U))
    gantry(add_box("Gantry_Beam_Upper2", 30, 803, 30, GX + 30, -10, GZ_U2))
    gantry(add_box("Gantry_Beam_Lower",  30, 803, 30, GX - 30, -10, GZ_L))

    gantry(add_box("Rail_X_Upper", 9, 600, 7, GX + 21,      110, GZ_U  + 30, COL_RAIL))
    gantry(add_box("Rail_X_Lower", 9, 600, 7, GX + 30 + 21, 110, GZ_U2 + 30, COL_RAIL))

    # Left side-plate (metal, P20)
    gantry(add_step("Side_Plate_Left",
        f"{METAL}/side_movement/P20_left_side_plate/side_plate_left_metal.step",
        x=0, y=0, z=93))

    gantry(add_step("Side_Plate_Back_Clip",
        f"{METAL}/side_movement/P20_left_side_plate_p2of3/5_models_and_renders/back_clip.step",
        x=0, y=0, z=93))

    gantry(add_step("Side_Plate_Lower_Front_Clip",
        f"{METAL}/side_movement/P20_left_side_plate_p3of3/5_models_and_renders/lower_front_clip.step",
        x=0, y=0, z=93))

    gantry(add_step("Side_Plate_Upper_Front_Clip",
        f"{METAL}/side_movement/P20_left_side_plate_p3of3/5_models_and_renders/upper_front_clip.step",
        x=0, y=0, z=93))

    # Right side-plate (plastic, still P29)
    gantry(add_stl("Side_Plate_Right",
        f"{PLAST}/side_plates/right/RIGHT_PLATE.stl",
        x=0, y=0, z=93))

    # Carriage (plastic, P07)
    gantry(add_stl("Carriage",
        f"{PLAST}/router/CARRIAGE.stl",
        x=137 - 239, y=411.5 - 428.5, z=93))

    # Z-axis motor plate (metal, engine_holder_vertical_plate p1of2)
    gantry(add_step("Engine_Holder_Plate_P1",
        f"{METAL}/mid_vertical_movement/engine_holder_vertical_plate_p1of2"
        "/5_models_and_renders/starting_point_rect_metal.step",
        x=137 - (358 + 506) / 2, y=490, z=93))

    # Top stepper holder (metal)
    gantry(add_step("Top_Stepper_Holder",
        f"{METAL}/mid_vertical_movement/top_stepper_holder"
        "/5_models_and_renders/engine_holder_top_plate.step",
        x=0, y=490 - 363.5, z=93 + 212))

    # Router clamps (metal, bottom and top)
    gantry(add_step("Router_Clamp_Bottom",
        f"{METAL}/mid_vertical_movement/router_clamp_bottom"
        "/5_models_and_renders/router_clamp.step",
        x=137, y=411.5, z=93 - 30))

    gantry(add_step("Router_Clamp_Top",
        f"{METAL}/mid_vertical_movement/router_clamp_top"
        "/5_models_and_renders/router_clamp.step",
        x=137, y=411.5, z=93 - 18))

    # Vertical slider (plastic, P36)
    gantry(add_stl("Vertical_Slider",
        f"{PLAST}/router/VERTICAL_SLIDER.stl",
        x=137 - 251.5, y=411.5 - 138.5, z=93))

    # Router bracket (plastic, P24)
    gantry(add_stl("Router_Bracket",
        f"{PLAST}/router/ROUTER_BRACKET.stl",
        x=137 - 324, y=411.5 - 138.5, z=93))

    # Engine sideways belt clamp (metal)
    gantry(add_step("Engine_Sideways_Belt_Clamp",
        f"{METAL}/mid_horizontal_movement/engine_sideways_belt_clamp"
        "/5_models_and_renders/engine_sideways_belt_clamp.step",
        x=137, y=-10, z=93 + 50))

    doc.recompute()


# ── Render inner (runs inside Xvfb subprocess) ────────────────────────────────

def _render_inner() -> None:
    import FreeCADGui

    W, H   = 960, 600
    FRAMES = 48
    FPS    = 12

    # Gantry travel: X offset from natural position
    X_FRONT, X_BACK = 13.0, 517.0

    def _travel(i: int) -> float:
        half = FRAMES // 2
        if i < half:
            return X_FRONT + (X_BACK - X_FRONT) * i / (half - 1)
        return X_BACK - (X_BACK - X_FRONT) * (i - half) / (half - 1)

    # 1. GUI init FIRST — DISPLAY is already set by our parent process
    print("[render] Starting FreeCADGui ...", flush=True)
    FreeCADGui.showMainWindow()
    time.sleep(1.0)
    print("[render] showMainWindow OK", flush=True)

    # 2. Build assembly with GUI active → view is created automatically
    print("[render] Building assembly ...", flush=True)
    document = FreeCAD.newDocument("CNC_Assembly")
    _build_assembly(document)
    print("[render] Assembly built", flush=True)
    time.sleep(0.5)

    # 3. Apply colours via the GUI document wrapper
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

    # 4. Get the 3-D viewport
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
        print("[render] ERROR: no active 3-D view available — aborting render", flush=True)
        return

    # Set perspective camera for better depth perception
    try:
        view.setCameraType("Perspective")
    except Exception:
        pass

    # Camera: sweep ±45° around a fixed front-left-above angle.
    # setViewDirection changes only the camera's pointing direction; the camera
    # position is then re-fitted each frame so the machine stays centred.
    # viewDir = (cos θ · cos φ, sin θ · cos φ, −sin φ)  (pointing INTO scene)
    ELEV    = math.radians(35)       # camera elevation above XY plane
    cos_e   = math.cos(ELEV)
    sin_e   = math.sin(ELEV)
    # Start angle (°): ~210° puts camera at front-left-above, showing the
    # gantry, the frame depth, and the carriage assembly together.
    START_A = math.radians(210)
    SWEEP   = math.radians(45)       # ±45° arc (90° total sweep)

    def _set_camera(frame: int) -> None:
        # Oscillate: 0→+45° then +45°→-45° then -45°→0°  (triangle wave)
        t = frame / FRAMES            # 0..1
        if t < 0.25:
            frac =  t / 0.25          # 0→1
        elif t < 0.75:
            frac =  1 - 2 * (t - 0.25) / 0.5   # 1→-1
        else:
            frac = -1 + (t - 0.75) / 0.25       # -1→0
        theta = START_A + frac * SWEEP
        dx =  cos_e * math.cos(theta)
        dy =  cos_e * math.sin(theta)
        dz = -sin_e
        try:
            view.setViewDirection((dx, dy, dz))
            view.fitAll()
        except Exception:
            pass

    # Initialise camera
    _set_camera(0)
    doc.recompute()
    time.sleep(0.3)
    print("[render] Camera ready", flush=True)

    # 5. Render frames
    frame_paths: list[str] = []
    tmpdir = tempfile.mkdtemp(prefix="cnc_gif_")

    for i in range(FRAMES):
        delta_x = _travel(i)
        set_gantry_x(delta_x)
        doc.recompute()

        _set_camera(i)

        png = os.path.join(tmpdir, f"frame_{i:03d}.png")
        view.saveImage(png, W, H, "White")
        frame_paths.append(png)
        print(f"  frame {i+1:02d}/{FRAMES}  delta_x={delta_x:5.0f} mm  → {png}", flush=True)

    # 6. Assemble GIF with ffmpeg
    concat = os.path.join(tmpdir, "frames.txt")
    duration = 1.0 / FPS
    with open(concat, "w") as f:
        for p in frame_paths:
            f.write(f"file '{p}'\n")
            f.write(f"duration {duration:.4f}\n")

    subprocess.run([
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", concat,
        "-vf", (
            "scale=960:-1:flags=lanczos,"
            "split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse"
        ),
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
            print(f"[assemble] Render subprocess exited with code {result.returncode}", flush=True)
            sys.exit(result.returncode)
    finally:
        xvfb.terminate()
        xvfb.wait()

    print(f"[assemble] All done!  GIF → {GIF_PATH}", flush=True)


if __name__ == "__main__":
    _main()
