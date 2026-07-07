# Metal mod — overview

This section documents the metal plate modifications to the DIY CNC machine. The metal mod replaces key 3D-printed structural parts with laser-cut or waterjet-cut aluminium plates, improving rigidity and longevity.

![Staged assembly](../images/metal/cnc_assembly_staged_gif.gif)

## What changes

| Plastic part | M-code | Metal replacement | Human name |
|---|---|---|---|
| P20 | M20.a | side_plate_left_metal | Side plate left — body |
| P21 | M20.b | back_clip | Side plate left — back clip |
| P22 | M20.c | lower_front_clip | Side plate left — lower front clip |
| P23 | M20.d | upper_front_clip | Side plate left — upper front clip |
| P29 | M29.a | side_plate_right_metal (Y-mirror of M20.a) | Side plate right — body |
| P30 | M29.b | back_clip (Y-mirror of M20.b) | Side plate right — back clip |
| P31 | M29.c | lower_front_clip (Y-mirror of M20.c) | Side plate right — lower front clip |
| P32 | M29.d | upper_front_clip (Y-mirror of M20.d) | Side plate right — upper front clip |
| P07 (Z-face) | M36.a | engine_holder_vertical_plate_p1of2 | Vertical plate p1of2 — gantry-fixed back plate |
| P36 | M36.b | engine_holder_vertical_plate_p2of2 | Vertical plate p2of2 — sliding front plate |
| P40 | M40.a | engine_holder_top_plate | Top stepper holder — Z motor mount |
| P24 | M24.a | router_clamp_bottom | Router clamp — bottom half |
| P24 | M24.b | router_clamp_top | Router clamp — top half |
| — (new) | MX.1 | engine_sideways_belt_clamp | Sideways belt clamp |

## 3D assembly

The animated GIFs below show the full machine. Per-component and per-stage GIFs are planned (see Render_requirements.md RR-03/RR-04).

| Animation | Description |
|---|---|
| ![Staged](../images/metal/cnc_assembly_staged_gif.gif) | Staged assembly — 5 build stages |
| ![Explode](../images/metal/cnc_assembly_explode_gif.gif) | Explode / re-assemble |
| ![Kinematic](../images/metal/cnc_assembly_gif.gif) | Kinematic — gantry travel + Z-slider |

## Build pages

Follow the same sequence as the plastic build. Where a plastic part is replaced by a metal equivalent, the M-code is shown and a plan-view image of the metal part is included.

- [Main frame](01-main-frame.md) — frame unchanged from plastic build
- [Y-axis](02-y-axis.md) — side plates M20.a–d / M29.a–d replace P20–P23, P29–P32
- [X-axis and Z-axis](03-x-axis-and-z-axis.md) — Z-axis plates M36.a/b, M40.a, M24.a/b, MX.1
- [Stepper motors and end-stops](04-stepper-motors-and-end-stops.md) — unchanged
- [Router](05-router.md) — router clamps M24.a/b instead of P24
