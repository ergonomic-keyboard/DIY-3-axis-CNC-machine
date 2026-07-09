# Metal-plate example folders

Each folder here holds one metal part in various stages of design (raw
screenshots → flattened image → measurements → traced outline → 3D models).
Folders are grouped by **sub-assembly page** (I–VI, matching
`docs/metal/01-…06-…md`), then named by their **M-code identifier** with a
short human-readable suffix.

## Naming convention

```
<Roman>_<subassembly>/<Mcode>_<short_name>/
```

- `<Roman>` is the sub-assembly number I–VI. Stage I (aluminium frame) has
  no metal-plate designs, so no `I_…` folder is present.
- `<Mcode>` is the canonical identifier used in the docs and in
  `assemble_and_render.py` object names (see `docs/metal/index.md` for the
  full table). Multi-letter suffixes (`a`, `b`, `c`, …) live inline
  without a dot: `M20a`, not `M20.a`.
- `<short_name>` is a lowercase snake_case hint at the physical part. Its
  only job is to save the reader a click.
- Sub-folders that are not yet productionised (no M-code) are prefixed
  with `_` so they sort to the bottom of their group.

Inside each part folder the numbered-stage convention holds:

```
0_raw_screenshots/     original photos of the plastic part
1_original_plastic_images/  cropped reference images
2_flattened_image/     rectified top-down view
3_measurements/        manually-annotated dimensions
4_outline/             traced 2D polygon
5_models_and_renders/  STEP / STL / plan PNG / build123d script
manual_design/         FreeCAD FCStd (versioned vN.FCStd)
```

## Layout

| Folder | M-code | Docs page | Notes |
|--------|--------|-----------|-------|
| `II_side_plates/M20a_left_body`              | M20.a | `docs/metal/02-…` | side plate left body |
| `II_side_plates/M20b_back_clip`              | M20.b | " | left back clip |
| `II_side_plates/M20cd_front_clips`           | M20.c + M20.d | " | shares a single scan; two build123d scripts + STEPs inside |
| `III_gantry/MX1_engine_sideways_belt_clamp`  | MX.1  | `docs/metal/03-…` | new part, no plastic equivalent |
| `IV_engine_plate_p1of2/M36a_vertical_plate`  | M36.a | `docs/metal/04-…` | gantry-fixed back plate |
| `V_z_axis_drive/M40a_top_stepper_holder`     | M40.a | `docs/metal/05-…` | Z-stepper mount |
| `V_z_axis_drive/_threaded_rod_clamper_experiment` | —  | " | WIP, no M-code yet |
| `VI_engine_plate_p2of2_and_router/M36b_vertical_plate`     | M36.b | `docs/metal/06-…` | sliding front plate |
| `VI_engine_plate_p2of2_and_router/M24a_router_clamp_bottom` | M24.a | " | router clamp lower half |
| `VI_engine_plate_p2of2_and_router/M24b_router_clamp_top`    | M24.b | " | router clamp upper half |
| `_legacy/P20_left_side_plate`                | —     | —            | pre-numbered-stage scan+render scripts; kept for provenance |
| `_reference_screenshots/*`                   | —     | —            | raw photos not yet turned into a part folder |

M29.a–d (right side plate) are **not** stored as separate folders — they are
produced by Y-mirroring M20.a–d at assembly time in
`hardware_mods/metal_plates/assembly/assemble_and_render.py`.

## Adding a new part

1. Pick or invent an M-code and add it to the table in `docs/metal/index.md`.
2. Create `<group>/<Mcode>_<short_name>/` and populate the numbered
   stage folders as you progress.
3. If the part gets a STEP export, wire it into `assemble_and_render.py`
   with the new path (and a `fallback_box=` for safety).
