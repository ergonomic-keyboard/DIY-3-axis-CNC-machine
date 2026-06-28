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

## Commands

`<EX>` = your example folder (e.g.
`hardware_mods/metal_plates/examples/side_movement/P20_left_side_plate_p1of3`).
All commands run inside the project's nix-shell.

```sh
# 1. Flatten the photo + trace the outline (stages 2 + 5).
nix-shell hardware_mods/metal_plates/shell.nix --run \
  "python hardware_mods/metal_plates/rectify.py \
     --example <EX> --stl docs/stl_files/side_plates/left/LEFT_PLATE.stl"

# 2. Build STEP / STL / plan PNG / plastic overlay (stages 6–8).
nix-shell hardware_mods/metal_plates/shell.nix --run \
  "python hardware_mods/metal_plates/build_model.py --example <EX>"

# 3. (Optional) Interactive H/V + snap-to-plastic editor.
nix-shell hardware_mods/metal_plates/shell.nix --run \
  "python hardware_mods/metal_plates/align_outline.py --example <EX>"
```

Run any script with `--help` to see flags and interactive controls.

```sh
EX=hardware_mods/metal_plates/examples/mid_vertical_movement/engine_holder_vertical_p1of2
PHOTO="$EX/0_raw_screenshots/starting_point.png"
STL=docs/stl_files/router/CARRIAGE.stl
nix-shell hardware_mods/metal_plates/shell.nix --run \
  "python -u hardware_mods/metal_plates/rectify.py --example $EX --stl $STL --photo \"$PHOTO\""

```