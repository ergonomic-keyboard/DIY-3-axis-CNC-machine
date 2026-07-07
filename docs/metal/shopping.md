# Metal mod — shopping / BOM delta

This page lists what changes from the plastic build BOM. Start from the [plastic BOM](../BILLOFMATERIAL.md) and apply this delta.

## Parts removed (no longer needed)

| Code | Part | Qty saved |
|------|------|-----------|
| P20 | Left side plate (3D-printed) | 1 |
| P21 | Left side plate lower back clip (3D-printed) | 1 |
| P22 | Left side plate lower front clip (3D-printed) | 1 |
| P23 | Left side plate upper front clip (3D-printed) | 1 |
| P29 | Right side plate (3D-printed) | 1 |
| P30 | Right side plate lower back clip (3D-printed) | 1 |
| P31 | Right side plate lower front clip (3D-printed) | 1 |
| P32 | Right side plate upper front clip (3D-printed) | 1 |
| P36 | Vertical carriage slider (3D-printed) | 1 |
| P40 | Z-axis stepper motor mount (3D-printed) | 1 |
| P24 | Milling router bracket (3D-printed) | 1 |

## Parts added (metal mod only)

| M-code | Part | File | Qty | Notes |
|--------|------|------|-----|-------|
| M20.a | Side plate left — body | side_plate_left_metal.step | 1 | Aluminium plate, laser/waterjet cut |
| M20.b | Side plate left — back clip | back_clip.step | 1 | Aluminium plate |
| M20.c | Side plate left — lower front clip | lower_front_clip.step | 1 | Aluminium plate |
| M20.d | Side plate left — upper front clip | upper_front_clip.step | 1 | Aluminium plate |
| M29.a–d | Side plate right (all clips) | mirror of M20.a–d | 4 | Same DXF, mirrored when cutting |
| M36.a | Vertical plate p1of2 | engine_holder_vertical_plate_p1of2.step | 1 | Aluminium plate |
| M36.b | Vertical plate p2of2 | engine_holder_vertical_plate_p2of2.step | 1 | Aluminium plate |
| M40.a | Top stepper holder | engine_holder_top_plate.step | 1 | Aluminium plate |
| M24.a | Router clamp bottom | router_clamp_bottom.step | 1 | Aluminium plate |
| M24.b | Router clamp top | router_clamp_top.step | 1 | Aluminium plate |
| MX.1 | Sideways belt clamp | engine_sideways_belt_clamp.step | 1 | Aluminium plate, new part |
| — | M5 DIN 934 nut (outtake tab bolts, M36.a) | — | 4 | In addition to standard BOM nuts |
| — | M5×20 mm screw (outtake tab bolts) | S12 | 4 | In addition to standard BOM |
| — | M3×16 mm screw (block bolts into M36.a) | S03 | 16 | In addition to standard BOM |
| — | M3×20 mm screw (p2of2 to blocks) | S04 | 16 | In addition to standard BOM |
| — | M5×20 mm screw (M40.a to M36.a) | S12 | 2 | In addition to standard BOM |
| — | M4×40 mm screw (router clamps) | S11 | 4 | In addition to standard BOM |

## Parts unchanged

All other parts from the [plastic BOM](../BILLOFMATERIAL.md) carry over unchanged, including all electronics (E01–E30), off-the-shelf parts (O01–O27), all remaining 3D-printed parts (P01–P19, P24–P28, P33–P35, P37–P39), and all screws/nuts/washers/threaded rods not listed above.
