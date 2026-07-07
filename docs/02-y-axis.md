# Y-axis

## Components

| Code | Part | Qty | 3D assembly object |
|------|------|-----|--------------------|
| P20  | Left side plate | 1 | `Side_Plate_Left` |
| P21  | Left side plate lower back clip | 1 | `Side_Plate_Back_Clip` |
| P22  | Left side plate lower front clip | 1 | `Side_Plate_Lower_Front_Clip` |
| P23  | Left side plate upper front clip | 1 | `Side_Plate_Upper_Front_Clip` |
| P29  | Right side plate | 1 | `Side_Plate_Left_R` (mirrored) |
| P30  | Right side plate lower back clip | 1 | `Side_Plate_Back_Clip_R` (mirrored) |
| P31  | Right side plate lower front clip | 1 | `Side_Plate_Lower_Front_Clip_R` (mirrored) |
| P32  | Right side plate upper front clip | 1 | `Side_Plate_Upper_Front_Clip_R` (mirrored) |
| O22  | MGN12H linear rail block | 4 | — (Y-axis, ride the frame rails) |
| E18  | Geared NEMA17 stepper motor (1:19, 8 mm shaft) | 2 | — |
| O18  | HTD5M pulley 12T 8 mm bore 15 mm wide | 2 | — |
| O17  | HTD5M belt 15 mm wide | ~2 m each | — |
| O01  | 698zz bearing | 12 | — |
| P16  | Idler block | 3 | — |
| P17  | Left belt tension slider | 1 | — |
| P18  | Left belt tensioner | 1 | — |
| P19  | Left fixed belt tensioner | 1 | — |
| P26  | Right belt tension slider | 1 | — |
| P27  | Right belt tensioner | 2 | — |
| P28  | Right fixed belt tensioner | 2 | — |
| P08  | End-stop mount (ordinary) | 2 | — |
| T01  | M5×140 mm threaded rod (beam tie rods) | 2 | `Rod_Beam_Lo`, `Rod_Beam_Up` |
| S14  | M5×60 mm screw (top beam) | 2 | — |
| S04  | M3×20 mm screw (side plate to blocks) | 16 | — |
| S06  | M3×40 mm screw (motor to side plate) | 8 | — |
| S12  | M5×20 mm screw (belt tensioners, end-stop mounts) | 12 | — |
| S15  | M8×60 mm screw (idlers, belt tensioners) | 5 | — |
| N02  | M5 nut | ~4 | `NutR_Beam_*` |
| N03  | M8 nut | ~6 | — |
| W03  | Washer 15×8.5×1.5 mm | 24 | — |
| W04  | Washer 20×10×2 mm | 2 | — |
| W05  | Washer 8×4×0.5 mm | 8 | — |

## Side plates to upper frame

Before attaching the side plates, the MGN12H blocks (**O22**) were added back onto the rails, 2x on each side. Be careful when sliding them onto the rails, there are multiple small bearing balls that easily fall out of the blocks.

![assemble_side_plates_1](./images/build/frame/assemble_side_plates_1.jpg)

![assemble_side_plates_2](./images/build/frame/assemble_side_plates_2.jpg)

The left (**P20**) and right (**P29**) side plates where then attached to the blocks using 16x 20 mm M3 screws (**S04**) (8x on each side plate). Make sure to attach the plates on the correct side (see images below).

I had to redesign the left side plate and reprint it later in the build (after the images were taken). Therefore, the left side plate seen in the upcoming images look a bit different than the one used (see next image for the left side plate used).

![assemble_side_plates_3](./images/build/frame/assemble_side_plates_3.jpg)

![assemble_side_plates_4](./images/build/frame/assemble_side_plates_4.jpg)

![assemble_side_plates_5](./images/build/frame/assemble_side_plates_5.jpg)

![assemble_side_plates_6](./images/build/frame/assemble_side_plates_6.jpg)

![assemble_side_plates_7](./images/build/frame/assemble_side_plates_7.jpg)

![assemble_side_plates_8](./images/build/frame/assemble_side_plates_8.jpg)

## Y-axis motors, idlers and pulleys to side plates

Each idler were made up out of 1x idler blocker (**P16**), 2x 60 mm fully threaded M8 screws (**S15**), 6x 698zz bearings (**O01**) and 8x (15 mm x 8.5 mm x 1.5mm) washers (**W03**) (2x closest to the idler blocker and 6x closest to the side plate). The idlers were then attached to each side plate using two M8 nuts (**N03**). Make sure that the bearings are spinning freely.

![attach_side_plate_motors_1](./images/build/frame/attach_side_plate_motors_1.jpg)

![attach_side_plate_motors_2](./images/build/frame/attach_side_plate_motors_2.jpg)

As I designed and added the idler blocker later on in the build, some of the images doesn't have it and they also have 3x washers instead of 1x washer closest to the screw head. I left these images anyways in the guide so you can see how it looks when you attach the idlers, but please ignore the wrong number of washers. Also ignore all the other things around the idlers in the upcoming 2 images, they are taken later on in the build.

![attach_side_plate_motors_3_0](./images/build/frame/attach_side_plate_motors_3_0.jpg)

![attach_side_plate_motors_3_1](./images/build/frame/attach_side_plate_motors_3_1.jpg)

Should be idler blockers and a different number of washers in the upcoming images.

![attach_side_plate_motors_3](./images/build/frame/attach_side_plate_motors_3.jpg)

![attach_side_plate_motors_4](./images/build/frame/attach_side_plate_motors_4.jpg)

![attach_side_plate_motors_5](./images/build/frame/attach_side_plate_motors_5.jpg)

![attach_side_plate_motors_6](./images/build/frame/attach_side_plate_motors_6.jpg)

![attach_side_plate_motors_7](./images/build/frame/attach_side_plate_motors_7.jpg)

To attach the stepper motors to the side plates, the 4x M3 screws (**S07**) locking the gear box to the motor were removed. Save these as they will be used later on to attach the power supply and Arduino to the electronic boxes.

![attach_side_plate_motors_1](./images/build/frame/attach_side_plate_motors_8.jpg)

![attach_side_plate_motors_1](./images/build/frame/attach_side_plate_motors_9.jpg)

The 2x geared stepper motors (**E18**) were then inserted into the large holes on the side plates, facing inwards. 4x 40 mm M3 screws (**S06**) and 4x M3 washers (**W05**) were used to lock each stepper motor to the side plates (I forgot to add the washers in the images below, therefore they're not visible). The motors should be attached so that the cables are facing in the direction of the two bridge beams (i.e. the longer vertical surface on the side plates).

![attach_side_plate_motors_1](./images/build/frame/attach_side_plate_motors_10.jpg)

![attach_side_plate_motors_1](./images/build/frame/attach_side_plate_motors_11.jpg)

![attach_side_plate_motors_1](./images/build/frame/attach_side_plate_motors_12.jpg)

![attach_side_plate_motors_1](./images/build/frame/attach_side_plate_motors_13.jpg)

![attach_side_plate_motors_1](./images/build/frame/attach_side_plate_motors_14.jpg)

1x HTD5M timing pulley (**O18**) was attached to each motor shaft using set screws.

![attach_side_plate_motors_1](./images/build/frame/attach_side_plate_motors_15.jpg)

![attach_side_plate_motors_1](./images/build/frame/attach_side_plate_motors_16.jpg)

![attach_side_plate_motors_1](./images/build/frame/attach_side_plate_motors_17.jpg)

![attach_side_plate_motors_1](./images/build/frame/attach_side_plate_motors_18.jpg)

## Y-axis belt tensioners and end-stop mounts

2x fixed belt tensioners (**P19**, **P28**) were attached to the longer aluminium profiles of the upper frame using 4x 20mm M5 screws (**S12**) (2x for each fixed belt tensioner). When aligning the fixed belt tensioners, make sure that the "belt opening" is pointing in the direction of the rails (1x fixed belt tensioner for each rail). Also make sure that the fixed belt tensioners are positioned on the correct side of the rail (see images). Similar to before, a bradawl and a hammer were used to make indentations at the center of the holes. Cutting fluid was applied and a 4 mm drill was used to drill the holes, followed by a M5 drill tap.

![attach_tensioners_and_belts_12](./images/build/frame/attach_tensioners_and_belts_12.jpg)

![attach_tensioners_and_belts_13](./images/build/frame/attach_tensioners_and_belts_13.jpg)

![attach_tensioners_and_belts_14](./images/build/frame/attach_tensioners_and_belts_14.jpg)

![attach_tensioners_and_belts_15](./images/build/frame/attach_tensioners_and_belts_15.jpg)

![attach_tensioners_and_belts_16](./images/build/frame/attach_tensioners_and_belts_16.jpg)

![attach_tensioners_and_belts_17](./images/build/frame/attach_tensioners_and_belts_17.jpg)

![attach_tensioners_and_belts_18](./images/build/frame/attach_tensioners_and_belts_18.jpg)

2x belt tension sliders (**P17**, **P26**) were attached on the opposite side of the fixed belt tensioners, ontop of the aluminium profile, using 4x 20mm M5 screws (**S12**). To get them aligned at the exact same place on both sides, a 100 mm distance was cut out and a flat support was clamped to the inner side of the profile. The same drill and tap size were used as for the fixed belt tensioners (4mm drill, M5 drill tap). Make sure that the belt tension sliders are pointing outwards.

![attach_tensioners_and_belts_19](./images/build/frame/attach_tensioners_and_belts_19.jpg)

![attach_tensioners_and_belts_20](./images/build/frame/attach_tensioners_and_belts_20.jpg)

![attach_tensioners_and_belts_21](./images/build/frame/attach_tensioners_and_belts_21.jpg)

![attach_tensioners_and_belts_22](./images/build/frame/attach_tensioners_and_belts_22.jpg)

![attach_tensioners_and_belts_23](./images/build/frame/attach_tensioners_and_belts_23.jpg)

![attach_tensioners_and_belts_24](./images/build/frame/attach_tensioners_and_belts_24.jpg)

![attach_tensioners_and_belts_25](./images/build/frame/attach_tensioners_and_belts_25.jpg)

![attach_tensioners_and_belts_26](./images/build/frame/attach_tensioners_and_belts_26.jpg)

![attach_tensioners_and_belts_27](./images/build/frame/attach_tensioners_and_belts_27.jpg)

2x end-stop mounts (**P08**) were then attached to the same side as the belt tension sliders using 4x 20mm M5 screws (**S12**), facing outwards and aligned with the rails. The same drill and tap size were used as for the fixed belt tensioners (4mm drill, M5 drill tap).

![attach_tensioners_and_belts_1](./images/build/frame/attach_tensioners_and_belts_1.jpg)

![attach_tensioners_and_belts_2](./images/build/frame/attach_tensioners_and_belts_2.jpg)

![attach_tensioners_and_belts_3](./images/build/frame/attach_tensioners_and_belts_3.jpg)

![attach_tensioners_and_belts_4](./images/build/frame/attach_tensioners_and_belts_4.jpg)

![attach_tensioners_and_belts_5](./images/build/frame/attach_tensioners_and_belts_5.jpg)

![attach_tensioners_and_belts_6](./images/build/frame/attach_tensioners_and_belts_6.jpg)

![attach_tensioners_and_belts_7](./images/build/frame/attach_tensioners_and_belts_7.jpg)

![attach_tensioners_and_belts_8](./images/build/frame/attach_tensioners_and_belts_8.jpg)

![attach_tensioners_and_belts_9](./images/build/frame/attach_tensioners_and_belts_9.jpg)

![attach_tensioners_and_belts_10](./images/build/frame/attach_tensioners_and_belts_10.jpg)

![attach_tensioners_and_belts_11](./images/build/frame/attach_tensioners_and_belts_11.jpg)

The belt tensioners (**P18**, **P27**) were loosely attached to the belt tension sliders using 2x 60 mm fully threaded M8 screws (**S15**), 2x M8 nuts(**N03**) and 2x (20mm x 10mm x 2mm) washers (**W04**).

![attach_tensioners_and_belts_28](./images/build/frame/attach_tensioners_and_belts_28.jpg)

![attach_tensioners_and_belts_29](./images/build/frame/attach_tensioners_and_belts_29.jpg)

## Y-axis HTD5M belts

The HTD5M belt (**O17**) was first inserted into one of the fixed belt tensioners using a flat screw driver. It was then stretched along the aluminium profile, below the first idler, around the timing pulley, below the second idler and all the way to the belt tensioner.

![attach_tensioners_and_belts_30](./images/build/frame/attach_tensioners_and_belts_30.jpg)

![attach_tensioners_and_belts_31](./images/build/frame/attach_tensioners_and_belts_31.jpg)

![attach_tensioners_and_belts_32](./images/build/frame/attach_tensioners_and_belts_32.jpg)

![attach_tensioners_and_belts_33](./images/build/frame/attach_tensioners_and_belts_33.jpg)

![attach_tensioners_and_belts_34](./images/build/frame/attach_tensioners_and_belts_34.jpg)

A scissor was used to cut the belt at an appropriate length. The loose end was then inserted into the belt tensioner using a flat screw driver and the belt was stretched by tightning the M8 nut.

![attach_tensioners_and_belts_35](./images/build/frame/attach_tensioners_and_belts_35.jpg)

![attach_tensioners_and_belts_36](./images/build/frame/attach_tensioners_and_belts_36.jpg)

![attach_tensioners_and_belts_37](./images/build/frame/attach_tensioners_and_belts_37.jpg)

![attach_tensioners_and_belts_38](./images/build/frame/attach_tensioners_and_belts_38.jpg)

![attach_tensioners_and_belts_39](./images/build/frame/attach_tensioners_and_belts_39.jpg)

Make sure that the belt is not too loose and not too tight.

![attach_tensioners_and_belts_40](./images/build/frame/attach_tensioners_and_belts_40.jpg)

![attach_tensioners_and_belts_41](./images/build/frame/attach_tensioners_and_belts_41.jpg)

Repeat on the other side.
