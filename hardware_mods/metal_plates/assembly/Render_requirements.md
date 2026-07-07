# Render Requirements

## Metal part identifier mapping

Plastic parts that become metal assemblies, with new M-codes:

| M-code | Script object | File | Replaces | Human name |
|--------|--------------|------|----------|------------|
| M20.a | `Side_Plate_Left` | side_plate_left_metal.step | P20 | side plate left — main body |
| M20.b | `Side_Plate_Back_Clip` | back_clip.step | P21 | side plate left — back clip |
| M20.c | `Side_Plate_Lower_Front_Clip` | lower_front_clip.step | P22 | side plate left — lower front clip |
| M20.d | `Side_Plate_Upper_Front_Clip` | upper_front_clip.step | P23 | side plate left — upper front clip |
| M29.a | `Side_Plate_Left_R` | same as M20.a, Y-mirrored | P29 | side plate right — main body |
| M29.b | `Side_Plate_Back_Clip_R` | same as M20.b, Y-mirrored | P30 | side plate right — back clip |
| M29.c | `Side_Plate_Lower_Front_Clip_R` | same as M20.c, Y-mirrored | P31 | side plate right — lower front clip |
| M29.d | `Side_Plate_Upper_Front_Clip_R` | same as M20.d, Y-mirrored | P32 | side plate right — upper front clip |
| M36.a | `Engine_Holder_P1` | engine_holder_vertical_plate_p1of2.step | P07 (Z-face) | vertical plate p1of2 — gantry-fixed back plate |
| M36.b | `Engine_Holder_P2` | engine_holder_vertical_plate_p2of2.step | P36 | vertical plate p2of2 — sliding front plate |
| M40.a | `Top_Stepper_Holder` | engine_holder_top_plate.step | P40 | engine holder top plate — stepper motor holder |
| M24.a | `Router_Clamp_Bottom` | router_clamp_bottom.step | P24 (part) | router clamp bottom |
| M24.b | `Router_Clamp_Top` | router_clamp_top.step | P24 (part) | router clamp top |
| MX.1  | `Engine_Sideways_Belt_Clamp` | engine_sideways_belt_clamp.step | — (new) | engine sideways belt clamp |

Right-side parts (M29.*) use the same STEP files as M20.* counterparts, Y-mirrored in the assembly script.

---

## Website structure requirements

### RR-01 — Four-section navigation
Restructure mkdocs.yml nav into four top-level tab sections:
- **Plastic — Bill of materials**: BILLOFMATERIAL.md
- **Plastic — Instructions**: pages 01–12 (existing plastic build guide, unchanged)
- **Metal — Shopping**: shopping.md (BOM delta for metal mod)
- **Metal — Instructions**: docs/metal/01–05.md (new, see RR-02)

Enable `features: navigation.tabs` in MkDocs Material theme.

### RR-02 — Metal instruction pages (docs/metal/01–05.md)
One page per build section that has metal modifications. Structure per page:
1. **Metal components table**: M-code | Human name | Replaces | Script object | Status (plastic / metal)
2. **Section content**: same headings as plastic counterpart; for any step involving a replaced part, show plastic photo alongside metal image/GIF (see RR-03/RR-04).
3. For sections with no metal modification, note "same as plastic build" and link to plastic page.

Pages 06–12 unchanged; link to plastic pages from metal nav.

### RR-03 — Per-component 3D GIF (not yet rendered)
For each M-coded part, generate a standalone rotating 3D GIF (isolated component, white background, ~24 frames, 360° rotation around Z). Target path:
```
hardware_mods/metal_plates/assembly/component_gifs/<M-code>_<human_name>.gif
```
Shown next to the plastic build photo on metal instruction pages. Implementation: extend assemble_and_render.py with `--component-gifs` mode; load each STEP via FreeCADGui, render rotating GIF.

### RR-04 — Per-stage sub-assembly GIFs (not yet rendered)
Extract frame ranges from cnc_assembly_staged_gif.gif into per-page GIFs:
- `staged_stage1_frame.gif` — frames 0–7 (main frame, page 01)
- `staged_stage2_sideplates.gif` — frames 8–15 (side plates, page 02)
- `staged_stage3_gantry.gif` — frames 16–23 (gantry beams + X-rails, page 03)
- `staged_stage4_zaxis.gif` — frames 24–31 (Z-axis components, pages 03/04)
- `staged_stage5_fasteners.gif` — frames 32–47 (fasteners + final view)

Implementation: post-process staged GIF with ffmpeg to extract frame ranges, or render each stage separately with a modified `--staged-render` that renders one stage at a time.

### RR-05 — Metal shopping / BOM delta
Expand Metal — Shopping page with three tables:
- **Removed**: plastic parts no longer needed (P20–P23, P29–P32, P36, P40, P24)
- **Added**: metal plate stock + new fasteners specific to metal mod
- **Unchanged**: parts that carry over from plastic build

### RR-06 — Interim: use existing GIFs on metal pages
Until RR-03/RR-04 are rendered, embed on metal pages:
- `cnc_assembly_staged_gif.gif` — full staged build (all metal pages)
- `cnc_assembly_explode_gif.gif` — explode view (overview)
- Existing plan-view PNGs from each component's `5_models_and_renders/` folder

---

## Design change requirements (FreeCAD edits)

### RR-07 — Holes A and B in engine_holder_top_plate
Add two M5 alignment/bolt holes to the top cross-member of the T-bar:
- Hole A: centred above bolt hole between edges 51 and 49 on p1of2 top edge → world Y ≈ 351
- Hole B: centred above bolt hole between edges 59 and 57 on p1of2 top edge → world Y ≈ 388
Requires editing the FreeCAD source file for engine_holder_top_plate.

### RR-08 — engine_holder_top_plate oval cutout merge
Merge the two large oblong cutouts into a single athletics-track oval. Replace the three small oval slots on the +Y side with two longer slider slots along the merged oval. Requires FreeCAD design edit.

### RR-09 — Right side plate separate STEP
Currently M29.a–d are Y-mirrors of M20.a–d computed at render time. If a physically separate right-side design is made, add it as its own STEP and update the assembly script to use `add_step` instead of `add_step_mirror_y`.
