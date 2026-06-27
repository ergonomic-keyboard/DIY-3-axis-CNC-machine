# Metal plates

Aluminium versions of the plastic 3D-printed parts, generated with
[`build123d`](https://build123d.readthedocs.io/) using hole positions
recovered from the plastic STLs and silhouettes traced from the build
video screenshots.

## Structure
The structure that the design of the metal components follows is shown in /home/a8/git/personal/DIY-3-axis-CNC-machine/hardware_mods/metal_plates/examples/side_movement/P20_left_side_plate_p1of3

the components are structured in:
/home/a8/git/personal/DIY-3-axis-CNC-machine/hardware_mods/metal_plates/examples

## Procedure
and for each component, 
0. I will start with a raw screenshot,
1. The original splastic images are used as a reference.
2.a The image will be flattened by opening a python command 
2.b and selecting 4 points on the image of which the coordinates are known (from the accompanying dril holes of the `.stl` files of the plastic parts (the holes stay the same just the outline/form changes)).
2.c You provide me with the description of those 4 coordinates so I know where to click.
3. You pit out the flattened image into 2_flattened_image
4. I will do some measurements on that flattened image, and store the printscreens of each of those into: 3_measurements.
5. Then I will use the 2_flattened image to draw the outline geometry of that aluminium part. Once I press quite you will store the output of that outline into 4_outline.
6.a I will then ask you to use the 3_measurements and 4_outline to generate a 3d model of the aluminum part including the holes, 
6.b and you will create a render in the form of an as an image, 
6.c and you will allow me to inspect the model in a 3d viewer. 
6.d Additionally you parameterise all the geometries (e.g. angles length sides) so I can easily modify them (and regenerate the model). 
6.e You shall use build123d to generate the model.

7. You shall throw a warning if the hole positions or sizes are modified w.r.t. the plastic stl position. 

8. Ideally you show the transparent overlay of the plastic part mapped on the exactly the same position based on the hole positions so I can easily verify the parts align well/are compatible.

## Layout

```
hardware_mods/metal_plates/
  shell.nix              Nix shell with all build123d + Qt deps
  extract_holes.py       reusable: STL → holes.json
  inspect_stl.py         reusable: bbox + orientation diagnostics
  rectify.py             reusable: rectify perspective + measure distances
  examples/              build-video screenshots, by mechanism / part
  parts/                 design files, mirroring examples/
    side_movement/
      P20_left_side_plate/
        side_plate_left.md            brief
        side_plate_left.py            build123d model
        holes.json                    extracted from LEFT_PLATE.stl
        side_plate_left_metal.{step,stl}
        side_plate_left_metal_plan.png
        render_plan.py                2D plan view renderer
        scan_upper.py                 (diagnostic kept for reference)
```

## Build the left side plate

```sh
nix-shell hardware_mods/metal_plates/shell.nix --run \
  "python hardware_mods/metal_plates/parts/side_movement/P20_left_side_plate/side_plate_left.py"
```

Render the 2D plan view PNG:

```sh
nix-shell hardware_mods/metal_plates/shell.nix --run \
  "python hardware_mods/metal_plates/parts/side_movement/P20_left_side_plate/render_plan.py"
```

View the 3D STEP:

```sh
nix-shell -p f3d --run \
  "f3d hardware_mods/metal_plates/parts/side_movement/P20_left_side_plate/side_plate_left_metal.step"
# or
nix-shell -p freecad --run \
  "FreeCAD hardware_mods/metal_plates/parts/side_movement/P20_left_side_plate/side_plate_left_metal.step"
```

## Extract holes for a new part

```sh
nix-shell hardware_mods/metal_plates/shell.nix --run \
  "python hardware_mods/metal_plates/extract_holes.py \
     docs/stl_files/side_plates/right/RIGHT_PLATE.stl \
     --out hardware_mods/metal_plates/parts/side_movement/P20_right_side_plate/holes.json"
```

## Inspect an STL (bbox, orientation, face histograms)

```sh
nix-shell hardware_mods/metal_plates/shell.nix --run \
  "python hardware_mods/metal_plates/inspect_stl.py \
     docs/stl_files/side_plates/right/RIGHT_PLATE.stl"
```

## Rectify a photo + measure distances

```sh
nix-shell hardware_mods/metal_plates/shell.nix --run \
  "python hardware_mods/metal_plates/rectify.py \
     'hardware_mods/metal_plates/examples/side_movement/P20_left_side_plate_p1of3/Screenshot From 2026-06-27 00-22-10.png' \
     --pts 103,1 178,1 178,21 103,21"
```

Click 4 known points in the photo (in the same order as `--pts`), then
click any two points in the rectified window to read the real-world
distance in mm. Pass `--bounds X_MIN X_MAX Z_MIN Z_MAX` to restrict the
output canvas to a specific region; `--max-px` caps the canvas size to
guard against wild perspectives.
