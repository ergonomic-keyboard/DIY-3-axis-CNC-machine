# II. Side plates & Y-axis

Left and right gantry holders: metal side plates (M20/M29) with Y-axis geared stepper motors, HTD5M belt drives, and tensioners — all mounted on the aluminium frame.

## Components

| Code | Part | Qty | 3D object | Metal change |
|------|------|-----|-----------|--------------|
| M20.a | side plate left — body | 1 | `Side_Plate_Left` | **metal** replaces P20 |
| M20.b | side plate left — back clip | 1 | `Side_Plate_Back_Clip` | **metal** replaces P21 |
| M20.c | side plate left — lower front clip | 1 | `Side_Plate_Lower_Front_Clip` | **metal** replaces P22 |
| M20.d | side plate left — upper front clip | 1 | `Side_Plate_Upper_Front_Clip` | **metal** replaces P23 |
| M29.a | side plate right — body | 1 | `Side_Plate_Left_R` (Y-mirror) | **metal** replaces P29 |
| M29.b | side plate right — back clip | 1 | `Side_Plate_Back_Clip_R` | **metal** replaces P30 |
| M29.c | side plate right — lower front clip | 1 | `Side_Plate_Lower_Front_Clip_R` | **metal** replaces P31 |
| M29.d | side plate right — upper front clip | 1 | `Side_Plate_Upper_Front_Clip_R` | **metal** replaces P32 |
| O22  | MGN12H rail block (Y-axis, 2 per rail) | 4 | — | unchanged |
| E18  | Geared NEMA17 stepper motor (1:19, 8 mm shaft) | 2 | — | unchanged |
| O18  | HTD5M pulley 12T 8 mm bore 15 mm wide | 2 | — | unchanged |
| O17  | HTD5M belt 15 mm wide | ~2 m each | — | unchanged |
| O01  | 698zz bearing | 12 | — | unchanged |
| P16  | Idler block (3D-printed) | 3 | — | unchanged |
| P17  | Left belt tension slider (3D-printed) | 1 | — | unchanged |
| P18  | Left belt tensioner (3D-printed) | 1 | — | unchanged |
| P19  | Left fixed belt tensioner (3D-printed) | 1 | — | unchanged |
| P26  | Right belt tension slider (3D-printed) | 1 | — | unchanged |
| P27  | Right belt tensioner (3D-printed) | 2 | — | unchanged |
| P28  | Right fixed belt tensioner (3D-printed) | 2 | — | unchanged |
| P08  | End-stop mount ordinary (3D-printed) | 2 | — | unchanged |
| T01  | M5×140 mm threaded rod | 2 | `Rod_Beam_Lo`, `Rod_Beam_Up` | unchanged |
| S14  | M5×60 mm screw (top beam) | 2 | — | unchanged |
| S04  | M3×20 mm screw (side plate to blocks) | 16 | — | unchanged |
| S06  | M3×40 mm screw (motor to side plate) | 8 | — | unchanged |
| S12  | M5×20 mm screw (tensioners, end-stop mounts) | 12 | — | unchanged |
| S15  | M8×60 mm fully-threaded screw (idlers, tensioners) | 5 | — | unchanged |
| N02  | M5 nut | ~4 | `NutR_Beam_*` | unchanged |
| N03  | M8 nut | ~6 | — | unchanged |
| W03  | Washer 15×8.5×1.5 mm | 24 | — | unchanged |
| W04  | Washer 20×10×2 mm | 2 | — | unchanged |
| W05  | Washer 8×4×0.5 mm | 8 | — | unchanged |

## 3D view — stage 2

Stage 2 (frames 8–15) in the staged GIF: side plates and clips assembling onto the frame.

`cnc_assembly_staged_gif`
![Staged assembly — stage 2](../images/metal/cnc_assembly_staged_gif.gif)

> Per-stage sub-GIF (frames 8–15 only) planned — RR-04.
> Per-component rotating GIFs (M20.a–d) planned — RR-03.

## Component plan views

| Part | Plastic original | Metal replacement |
|------|-----------------|-------------------|
| M20.a — side plate body | ![left_plate](../images/3dprinted_parts/side_plates/left/left_plate.jpg) `left_plate` (P20) | ![M20a_plan](../images/metal/components/M20a_plan.png) `M20a_plan` |
| M20.b — back clip | ![left_plate_back_plate_back_clip](../images/3dprinted_parts/side_plates/left/left_plate_back_plate_back_clip.jpg) `left_plate_back_plate_back_clip` (P21) | ![M20b_plan](../images/metal/components/M20b_plan.png) `M20b_plan` |
| M20.c — lower front clip | ![left_plate_lower_front_clip](../images/3dprinted_parts/side_plates/left/left_plate_lower_front_clip.jpg) `left_plate_lower_front_clip` (P22) | ![M20c_plan](../images/metal/components/M20c_plan.png) `M20c_plan` |
| M20.d — upper front clip | ![left_plate_upper_front_clip](../images/3dprinted_parts/side_plates/left/left_plate_upper_front_clip.jpg) `left_plate_upper_front_clip` (P23) | ![M20d_plan](../images/metal/components/M20d_plan.png) `M20d_plan` |

`M20a_vs_plastic`
![M20a_vs_plastic](../images/metal/components/M20a_vs_plastic.png)

M29.a–d (right side) are Y-mirrors of M20.a–d — no separate design files.

## Side plates to upper frame

Slide the MGN12H blocks (**O22**) back onto the Y-rails, 2 per side. Be careful: small bearing balls fall out easily.

`assemble_side_plates_1`
![assemble_side_plates_1](../images/build/frame/assemble_side_plates_1.jpg)

`assemble_side_plates_2`
![assemble_side_plates_2](../images/build/frame/assemble_side_plates_2.jpg)

Attach **M20.a** (left) and **M29.a** (right) to the blocks using 16× M3×20 mm screws (**S04**), 8 per plate. Check orientation — motor hole faces inward.

`assemble_side_plates_3`
![assemble_side_plates_3](../images/build/frame/assemble_side_plates_3.jpg)

`assemble_side_plates_4`
![assemble_side_plates_4](../images/build/frame/assemble_side_plates_4.jpg)

`assemble_side_plates_5`
![assemble_side_plates_5](../images/build/frame/assemble_side_plates_5.jpg)

`assemble_side_plates_6`
![assemble_side_plates_6](../images/build/frame/assemble_side_plates_6.jpg)

`assemble_side_plates_7`
![assemble_side_plates_7](../images/build/frame/assemble_side_plates_7.jpg)

`assemble_side_plates_8`
![assemble_side_plates_8](../images/build/frame/assemble_side_plates_8.jpg)

## Y-axis motors, idlers and pulleys

Each idler: 1× idler block (**P16**), 2× M8×60 mm screw (**S15**), 6× 698zz bearing (**O01**), 8× washer (**W03**) — 2 closest to the idler block, 6 closest to the side plate. Attach with 2× M8 nut (**N03**). Bearings must spin freely.

`attach_side_plate_motors_1`
![attach_side_plate_motors_1](../images/build/frame/attach_side_plate_motors_1.jpg)

`attach_side_plate_motors_2`
![attach_side_plate_motors_2](../images/build/frame/attach_side_plate_motors_2.jpg)

`attach_side_plate_motors_3_0`
![attach_side_plate_motors_3_0](../images/build/frame/attach_side_plate_motors_3_0.jpg)

`attach_side_plate_motors_3_1`
![attach_side_plate_motors_3_1](../images/build/frame/attach_side_plate_motors_3_1.jpg)

`attach_side_plate_motors_3`
![attach_side_plate_motors_3](../images/build/frame/attach_side_plate_motors_3.jpg)

`attach_side_plate_motors_4`
![attach_side_plate_motors_4](../images/build/frame/attach_side_plate_motors_4.jpg)

`attach_side_plate_motors_5`
![attach_side_plate_motors_5](../images/build/frame/attach_side_plate_motors_5.jpg)

`attach_side_plate_motors_6`
![attach_side_plate_motors_6](../images/build/frame/attach_side_plate_motors_6.jpg)

`attach_side_plate_motors_7`
![attach_side_plate_motors_7](../images/build/frame/attach_side_plate_motors_7.jpg)

Remove the 4× M3 screws locking the gearbox to the motor body (save them — they are used later for the electronics boxes).

`attach_side_plate_motors_8`
![attach_side_plate_motors_8](../images/build/frame/attach_side_plate_motors_8.jpg)

`attach_side_plate_motors_9`
![attach_side_plate_motors_9](../images/build/frame/attach_side_plate_motors_9.jpg)

Insert the 2× geared stepper motors (**E18**) into the large holes on M20.a / M29.a, facing inward, cables toward the bridge beam side. Fix with 4× M3×40 mm screws (**S06**) and 4× washers (**W05**) per motor.

`attach_side_plate_motors_10`
![attach_side_plate_motors_10](../images/build/frame/attach_side_plate_motors_10.jpg)

`attach_side_plate_motors_11`
![attach_side_plate_motors_11](../images/build/frame/attach_side_plate_motors_11.jpg)

`attach_side_plate_motors_12`
![attach_side_plate_motors_12](../images/build/frame/attach_side_plate_motors_12.jpg)

`attach_side_plate_motors_13`
![attach_side_plate_motors_13](../images/build/frame/attach_side_plate_motors_13.jpg)

`attach_side_plate_motors_14`
![attach_side_plate_motors_14](../images/build/frame/attach_side_plate_motors_14.jpg)

Attach 1× HTD5M pulley (**O18**) to each motor shaft with set screws.

`attach_side_plate_motors_15`
![attach_side_plate_motors_15](../images/build/frame/attach_side_plate_motors_15.jpg)

`attach_side_plate_motors_16`
![attach_side_plate_motors_16](../images/build/frame/attach_side_plate_motors_16.jpg)

`attach_side_plate_motors_17`
![attach_side_plate_motors_17](../images/build/frame/attach_side_plate_motors_17.jpg)

`attach_side_plate_motors_18`
![attach_side_plate_motors_18](../images/build/frame/attach_side_plate_motors_18.jpg)

## Y-axis belt tensioners and end-stop mounts

Attach 2× fixed belt tensioners (**P19**, **P28**) to the longer upper frame profiles using 4× M5×20 mm screws (**S12**). Orient so the belt opening faces the rail direction. Centre-punch, drill 4 mm, tap M5.

`attach_tensioners_and_belts_12`
![attach_tensioners_and_belts_12](../images/build/frame/attach_tensioners_and_belts_12.jpg)

`attach_tensioners_and_belts_13`
![attach_tensioners_and_belts_13](../images/build/frame/attach_tensioners_and_belts_13.jpg)

`attach_tensioners_and_belts_14`
![attach_tensioners_and_belts_14](../images/build/frame/attach_tensioners_and_belts_14.jpg)

`attach_tensioners_and_belts_15`
![attach_tensioners_and_belts_15](../images/build/frame/attach_tensioners_and_belts_15.jpg)

`attach_tensioners_and_belts_16`
![attach_tensioners_and_belts_16](../images/build/frame/attach_tensioners_and_belts_16.jpg)

`attach_tensioners_and_belts_17`
![attach_tensioners_and_belts_17](../images/build/frame/attach_tensioners_and_belts_17.jpg)

`attach_tensioners_and_belts_18`
![attach_tensioners_and_belts_18](../images/build/frame/attach_tensioners_and_belts_18.jpg)

Attach 2× belt tension sliders (**P17**, **P26**) on the opposite side of the fixed tensioners. Use a 100 mm spacer to align them identically on both sides. Belt tension slider openings face outward.

`attach_tensioners_and_belts_19`
![attach_tensioners_and_belts_19](../images/build/frame/attach_tensioners_and_belts_19.jpg)

`attach_tensioners_and_belts_20`
![attach_tensioners_and_belts_20](../images/build/frame/attach_tensioners_and_belts_20.jpg)

`attach_tensioners_and_belts_21`
![attach_tensioners_and_belts_21](../images/build/frame/attach_tensioners_and_belts_21.jpg)

`attach_tensioners_and_belts_22`
![attach_tensioners_and_belts_22](../images/build/frame/attach_tensioners_and_belts_22.jpg)

`attach_tensioners_and_belts_23`
![attach_tensioners_and_belts_23](../images/build/frame/attach_tensioners_and_belts_23.jpg)

`attach_tensioners_and_belts_24`
![attach_tensioners_and_belts_24](../images/build/frame/attach_tensioners_and_belts_24.jpg)

`attach_tensioners_and_belts_25`
![attach_tensioners_and_belts_25](../images/build/frame/attach_tensioners_and_belts_25.jpg)

`attach_tensioners_and_belts_26`
![attach_tensioners_and_belts_26](../images/build/frame/attach_tensioners_and_belts_26.jpg)

`attach_tensioners_and_belts_27`
![attach_tensioners_and_belts_27](../images/build/frame/attach_tensioners_and_belts_27.jpg)

Attach 2× end-stop mounts (**P08**) beside the belt tension sliders, facing outward aligned with the rails. Same drill and tap (4 mm / M5).

`attach_tensioners_and_belts_1`
![attach_tensioners_and_belts_1](../images/build/frame/attach_tensioners_and_belts_1.jpg)

`attach_tensioners_and_belts_2`
![attach_tensioners_and_belts_2](../images/build/frame/attach_tensioners_and_belts_2.jpg)

`attach_tensioners_and_belts_3`
![attach_tensioners_and_belts_3](../images/build/frame/attach_tensioners_and_belts_3.jpg)

`attach_tensioners_and_belts_4`
![attach_tensioners_and_belts_4](../images/build/frame/attach_tensioners_and_belts_4.jpg)

`attach_tensioners_and_belts_5`
![attach_tensioners_and_belts_5](../images/build/frame/attach_tensioners_and_belts_5.jpg)

`attach_tensioners_and_belts_6`
![attach_tensioners_and_belts_6](../images/build/frame/attach_tensioners_and_belts_6.jpg)

`attach_tensioners_and_belts_7`
![attach_tensioners_and_belts_7](../images/build/frame/attach_tensioners_and_belts_7.jpg)

`attach_tensioners_and_belts_8`
![attach_tensioners_and_belts_8](../images/build/frame/attach_tensioners_and_belts_8.jpg)

`attach_tensioners_and_belts_9`
![attach_tensioners_and_belts_9](../images/build/frame/attach_tensioners_and_belts_9.jpg)

`attach_tensioners_and_belts_10`
![attach_tensioners_and_belts_10](../images/build/frame/attach_tensioners_and_belts_10.jpg)

`attach_tensioners_and_belts_11`
![attach_tensioners_and_belts_11](../images/build/frame/attach_tensioners_and_belts_11.jpg)

Loosely attach the belt tensioners (**P18**, **P27**) to the sliders with 2× M8×60 mm screws (**S15**), M8 nuts (**N03**), and washers (**W04**).

`attach_tensioners_and_belts_28`
![attach_tensioners_and_belts_28](../images/build/frame/attach_tensioners_and_belts_28.jpg)

`attach_tensioners_and_belts_29`
![attach_tensioners_and_belts_29](../images/build/frame/attach_tensioners_and_belts_29.jpg)

## Y-axis HTD5M belts

Insert the HTD5M belt (**O17**) into the fixed tensioner with a flat screwdriver. Thread it below the first idler, around the pulley, below the second idler, then to the belt tensioner. Cut to length, insert the loose end into the tensioner, and tighten the M8 nut to tension. Belt should be firm but not over-tight.

`attach_tensioners_and_belts_30`
![attach_tensioners_and_belts_30](../images/build/frame/attach_tensioners_and_belts_30.jpg)

`attach_tensioners_and_belts_31`
![attach_tensioners_and_belts_31](../images/build/frame/attach_tensioners_and_belts_31.jpg)

`attach_tensioners_and_belts_32`
![attach_tensioners_and_belts_32](../images/build/frame/attach_tensioners_and_belts_32.jpg)

`attach_tensioners_and_belts_33`
![attach_tensioners_and_belts_33](../images/build/frame/attach_tensioners_and_belts_33.jpg)

`attach_tensioners_and_belts_34`
![attach_tensioners_and_belts_34](../images/build/frame/attach_tensioners_and_belts_34.jpg)

`attach_tensioners_and_belts_35`
![attach_tensioners_and_belts_35](../images/build/frame/attach_tensioners_and_belts_35.jpg)

`attach_tensioners_and_belts_36`
![attach_tensioners_and_belts_36](../images/build/frame/attach_tensioners_and_belts_36.jpg)

`attach_tensioners_and_belts_37`
![attach_tensioners_and_belts_37](../images/build/frame/attach_tensioners_and_belts_37.jpg)

`attach_tensioners_and_belts_38`
![attach_tensioners_and_belts_38](../images/build/frame/attach_tensioners_and_belts_38.jpg)

`attach_tensioners_and_belts_39`
![attach_tensioners_and_belts_39](../images/build/frame/attach_tensioners_and_belts_39.jpg)

`attach_tensioners_and_belts_40`
![attach_tensioners_and_belts_40](../images/build/frame/attach_tensioners_and_belts_40.jpg)

`attach_tensioners_and_belts_41`
![attach_tensioners_and_belts_41](../images/build/frame/attach_tensioners_and_belts_41.jpg)

Repeat for the other side.

---

*Next: [III. Gantry & X-axis](03-gantry.md)*
