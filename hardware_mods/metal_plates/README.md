## TL;DR

Get data:
```sh
nix-shell hardware_mods/metal_plates/shell.nix --run "python hardware_mods/metal_plates/side_plate_left.py"
```
View:
```sh
nix-shell -p freecad --run "FreeCAD hardware_mods/metal_plates/side_plate_left_metal.step"
```
## Rotating the plane to be flat in view:
```sh
nix-shell hardware_mods/metal_plates/shell.nix --run "python hardware_mods/metal_plates/rectify.py \
  'docs/images/parts/metal/metal_img/side_movement/P20_left_side_plate_p1of3/Screenshot From 2026-06-27 00-22-10.png' \
  --pts 103,1 178,1 178,21 103,21"
```