# P20 left side plate (part 1 of 3) — handover

Reverse-engineering the left side plate of the side-movement (X-axis)
assembly into a flat aluminium plate, working from build-video screenshots
and the original plastic prototype photos.

## Goal

Produce a parametric build123d model whose silhouette matches the metal
plate visible in the video. **Outline only at this stage** — holes are not
included yet.

## Folder layout (numbered-stage workflow)

| Stage | What lives here |
| --- | --- |
| `0_raw_screenshots/` | Untouched video frames. |
| `1_original_plastic_images/` | Photos of the original red 3D-printed plastic prototype (`left_plate.jpg`) and the grid overlay used while planning. |
| `2_flattened_image/` | Perspective-corrected screenshot (`Screenshot From 2026-06-27 15-29-35.png`), the traced polygon JSON/PNG, and the raw `measurements` log from `rectify.py` (25 unlabeled distance measurements). |
| `3_measurements/` | Annotated measurement drawings (`outline.png`). |
| `4_outline/` | `plate_outline.py` — the parametric build123d script. |
| `5_models_and_renders/` | Generated `.step` / `.stl` outputs. Safe to delete and regenerate. |

## Current state

- Polygon outline traced over the flattened screenshot using
  `hardware_mods/metal_plates/trace_polygon.py` → 25 vertices (last duplicates the first; effectively 24).
- Nearly-H / nearly-V edges snapped to perfect H/V; four intentional
  chamfers preserved (bottom-left, big upper-left, tab-side, bottom-right).
- Two U-shaped cross-bar notches modelled; their height is driven by a single
  parameter `BAR_PROFILE` (default 30 mm) on the assumption that both
  notches accept the same horizontal steel bar.
- Pixel→mm scale derived from the bar profile assumption: ~4.43 px/mm.
  At this scale the plate comes out **109.4 mm wide × 194.8 mm tall × 6.0 mm thick**.
- STEP and STL exported into `5_models_and_renders/`.

## How to (re)build the model

```
nix-shell hardware_mods/metal_plates/shell.nix --run \
  "python hardware_mods/metal_plates/examples/side_movement/\
P20_left_side_plate_p1of3/4_outline/plate_outline.py"
```

Edit any parameter in the constants block at the top of
`4_outline/plate_outline.py` and re-run. Every value is independent; vertex
numbers in the `OUTLINE` list map to V1..V24 in the polygon JSON.

## What is *not* done yet

- **Hole positions** — the user deferred this; only the outline is in.
  The existing production model at
  `hardware_mods/metal_plates/examples/side_movement/P20_left_side_plate/`
  derives holes from `holes.json` (extracted from the plastic STL) — that
  pipeline can be reused or adapted.
- **Dimension calibration vs. real measurements** — the 25 distances in
  `2_flattened_image/measurements` are unlabeled. They need to be mapped
  to specific edges/features (e.g. via the annotation in
  `3_measurements/outline.png`) and the parameter defaults updated.
- **Plate thickness** — `PLATE_THICKNESS = 6.0 mm` is a placeholder.
- **Visual preview** — no 2D plan renderer here yet; the existing
  `examples/side_movement/P20_left_side_plate/render_plan.py` is a good
  template if one is wanted.

## Related tools in the repo

- `hardware_mods/metal_plates/rectify.py` — perspective-correct a photo
  via 4 known points, then click-to-measure in mm.
- `hardware_mods/metal_plates/trace_polygon.py` — open an image and
  click to define a closed polygon; saves vertices to JSON.
- `hardware_mods/metal_plates/extract_holes.py` — pull hole positions from
  an STL of the plastic prototype.
- `hardware_mods/metal_plates/examples/side_movement/P20_left_side_plate/`
  — older "production" model of this part (different silhouette, includes
  holes). Useful reference but its OUTLINE is not the one in this example.

## Conventions worth keeping

- New build123d scripts for any plate example go in that example's
  `4_outline/` directory; outputs go to its `5_models_and_renders/`.
- The promoted, finished version of a plate sits alongside its WIP
  example folders as `examples/<group>/<plate>/` (no `_pXofN` suffix) —
  the suffix-less folder holds the build script + final STEP/STL/plan.
- Git: this repo uses the "Optimist Prime" identity for AI-authored
  commits; never the user's [redacted] work email.
