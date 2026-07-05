## Coordinate system (script convention)

All positions below use the **assembly script's coordinate system** (`assemble_and_render.py`):

| Script axis | Machine direction         | Range       |
|-------------|---------------------------|-------------|
| X           | depth (front → back)      | 0 → 900 mm  |
| Y           | width (left → right)      | 0 → 793 mm  |
| Z           | vertical (down → up)      | −140 → ~310 mm at plate level |

Machine centre-line: Y = 396.5 mm.  
Script object names are in `code font`.

---

## Gantry

The **gantry** is the bridge assembly that travels along the machine depth (script X, 0→900 mm). It consists of three 803 mm aluminium extrusion beams running in Y (machine width), two MGN12 Y-axis rails on top, and the two side plates that ride on those Y-rails. Everything bolted to the gantry moves with it in X.

In the assembly script, any object wrapped in `gantry(…)` has its X position animated (travelling front-to-back). Objects additionally wrapped in `z_slide(…)` also travel vertically (in Z) independently of the gantry's X motion.

---

## Z-axis sub-assembly

### Parts involved

| Your name           | Script object name (`assemble_and_render.py`) | Physical part |
|---------------------|-----------------------------------------------|---------------|
| p1of2               | `Engine_Holder_P1`                            | `engine_holder_vertical_plate_p1of2` — static back plate, travels with gantry only |
| `left_rails_YZ`     | `Rail_Z_Left`                                 | Left MGN12 linear rail, runs in Z (vertical) |
| `right_rails_YZ`    | `Rail_Z_Right`                                | Right MGN12 linear rail, runs in Z (vertical) |
| `top_left_YZ`       | `MGN12H_Block_LU`                             | MGN12H carriage block, upper-left |
| `bottom_left_YZ`    | `MGN12H_Block_LL`                             | MGN12H carriage block, lower-left |
| `top_right_YZ`      | `MGN12H_Block_RU`                             | MGN12H carriage block, upper-right |
| `bottom_right_YZ`   | `MGN12H_Block_RL`                             | MGN12H carriage block, lower-right |
| p2of2               | `Engine_Holder_P2`                            | `engine_holder_vertical_plate_p2of2` — sliding plate, carries router |
| —                   | `Router_Clamp_Bottom/Top`                     | Router clamps, attached to p2of2 |

### Kinematics (desired)

- **p1of2**: moves with gantry in X only. Does **not** z-slide.
- **`top_left_YZ`, `bottom_left_YZ`, `top_right_YZ`, `bottom_right_YZ` (4 blocks)**: bolted **fixed** to p1of2 face — gantry only, do **not** z-slide.
- **`left_rails_YZ`, `right_rails_YZ`**: bolted to p2of2 top and bottom — slide in Z **and** move with gantry.
- **p2of2**: the sliding plate — gantry + z-slide. ✓ (already correct)
- **Router clamps**: fixed to p2of2 — gantry + z-slide. ✓ (already correct)

#### Bug in current script
The current code has it inverted: the 4 blocks z-slide and the rails do not.  
Fix: remove `z_slide()` from the 4 blocks; add `z_slide()` to both rails.

---

### p1of2 orientation (desired)

Plate stays in the YZ plane (face normal in ±X). The face with the motor/bearing hole should point toward **negative Y** (machine left). The MGN12H bolt groups must end up to the **left** (lower Y) of the bearing hole — which they are, given the hole layout on the plate.

**Implementation in script**: flip p1of2 180° around world Z, keeping physical centre at Y ≈ 397.  
Change `yaw` from `−90` to `+90`; adjust `place_y` accordingly so the plate body stays at the same world Y span.

---

### MGN12H block mounting constraints (from p1of2 design file)

The four blocks are bolted to p1of2 at these specific vertices/holes (Manual design v15):

| Block name       | Mounting vertices on p1of2       |
|------------------|----------------------------------|
| `top_left_YZ`    | 34, 33, 32, 35                   |
| `bottom_left_YZ` | 40, 43, 42, 41                   |
| `top_right_YZ`   | 37, 38, 39, 36                   |
| `bottom_right_YZ`| 47, 46, 45, 44                   |

These vertices define the bolt pattern for each block. The world XYZ position of each block in the assembly script is derived from wherever those vertices land after p1of2 is placed and oriented — not the other way around. If the p1of2 design changes, update the script positions to match the new vertex locations.

The rails (`left_rails_YZ` and `right_rails_YZ`) run vertically (Z direction) through the blocks; their Y position follows the block centre-lines.

---

### p2of2 orientation (desired)

`engine_holder_vertical_plate_p2of2` v6.FCStd.  
Desired assembly position: plate is vertical in the YZ plane (same orientation family as p1of2), centred at Y ≈ 370 (midpoint of the two rail centres: (337+402)/2), with its back face resting against the block fronts at X ≈ 124.

Current script: `yaw=90, pitch=90` → local_Z→worldX, local_X→worldY, local_Y→worldZ.  
Needed: rotate 90° CW around world Z from current orientation.  
Verify by inspecting the render — the plate must stand vertical in YZ with its long axis in Z.  
**Suggested placement**: `x=114, y=370, z=210`.

---

## Top stepper holder

**Part**: `top_stepper_holder/5_models_and_renders/engine_holder_top_plate.step`  
**Script object**: `Top_Stepper_Holder`

### Placement (assembly-script level)

The holder should be directly above `Engine_Holder_P1` (p1of2).  
After the p1of2 flip: p1of2 is centred at world X=137 (depth) and Y≈397 (width).  
Current script has `x=0` — this needs to increase to ≈137 so the stepper holder is above p1of2, not at the machine front face.  
The Y placement offset (currently `490 − 363.5 = 126.5`) may also need adjustment; exact value requires measuring the STEP file's local Y origin (segfaulting under current FreeCAD subprocess approach).

Alignment holes A and B must be added to the top cross-member of the T-bar:
- **Hole A**: centred above the bolt hole between edges 51 and 49 on p1of2's top edge.
- **Hole B**: centred above the bolt hole between edges 59 and 57 on p1of2's top edge.

These holes do not yet exist in the STEP file. The Y position of the top stepper holder in the script should be driven by aligning holes A and B over those edge-defined bolt holes on p1of2 — not by a hard-coded Y coordinate.

### Design-file changes required (out of scope for assembly script)

These require editing `engine_holder_top_plate` in FreeCAD:

1. **Add holes A and B** in the top cross-member of the T-bar, aligned with the bolt holes on p1of2's top edge (between edges 49/51 and 57/59).
2. **Merge the two large oblong cutouts** into a single athletics-track oval (two semicircles joined by two straight tangent lines).
3. **Replace the three small oval slots** on the positive-Y side of the T-body with **two longer slider slots** running along the side of the merged oval cutout.
