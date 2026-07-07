# Metal — Y-axis

## Metal components

| M-code | Human name | Replaces | Script object | Status |
|--------|-----------|----------|---------------|--------|
| M20.a | side plate left — body | P20 | `Side_Plate_Left` | **metal** |
| M20.b | side plate left — back clip | P21 | `Side_Plate_Back_Clip` | **metal** |
| M20.c | side plate left — lower front clip | P22 | `Side_Plate_Lower_Front_Clip` | **metal** |
| M20.d | side plate left — upper front clip | P23 | `Side_Plate_Upper_Front_Clip` | **metal** |
| M29.a | side plate right — body | P29 | `Side_Plate_Left_R` | **metal** (Y-mirror of M20.a) |
| M29.b | side plate right — back clip | P30 | `Side_Plate_Back_Clip_R` | **metal** (Y-mirror of M20.b) |
| M29.c | side plate right — lower front clip | P31 | `Side_Plate_Lower_Front_Clip_R` | **metal** (Y-mirror of M20.c) |
| M29.d | side plate right — upper front clip | P32 | `Side_Plate_Upper_Front_Clip_R` | **metal** (Y-mirror of M20.d) |
| O22 | MGN12H block | — | — | unchanged |
| E18 | Geared NEMA17 stepper motor (Y-axis) | — | — | unchanged |
| O18 | HTD5M pulley | — | — | unchanged |
| O17 | HTD5M belt | — | — | unchanged |
| T01 | M5×140 mm threaded rod | — | `Rod_Beam_Lo/Up` | unchanged |
| S04 | M3×20 mm screw (side plate to blocks) | — | — | unchanged |

## Assembly GIF — stage 2 (side plates)

The staged assembly GIF below shows all 5 build stages. Side plates appear in **stage 2** (frames 8–15 of the animation).

![Staged assembly](../images/metal/cnc_assembly_staged_gif.gif)

> Per-stage sub-GIF (frames 8–15 only) is planned — see Render_requirements.md RR-04.
> Per-component rotating GIFs (M20.a–d) are planned — see RR-03.

## Side plate plan views

| Part | Plan view |
|------|-----------|
| M20.a — side plate left body | ![plan](../images/metal/components/M20a_plan.png) |
| M20.a vs plastic P20 | ![vs plastic](../images/metal/components/M20a_vs_plastic.png) |
| M20.b — back clip | ![plan](../images/metal/components/M20b_plan.png) |
| M20.c — lower front clip | ![plan](../images/metal/components/M20c_plan.png) |
| M20.d — upper front clip | ![plan](../images/metal/components/M20d_plan.png) |

M29.a–d (right side) are the same plates mirrored in Y — no separate design files.

---

## Side plates to upper frame

Same process as the [plastic build](../02-y-axis.md#side-plates-to-upper-frame), but use metal parts **M20.a + M29.a** instead of P20 + P29.

The four clips (M20.b/c/d and M29.b/c/d) replace the separate printed clips P21–P23 and P30–P32. They are bolted to the bridge beams and side plates using T01 threaded rods and N02 nuts, exactly as described for the plastic clips.

The blocks (O22) and screw count (S04 ×16) are unchanged.

## Y-axis motors, idlers and pulleys to side plates

Unchanged from [plastic build](../02-y-axis.md#y-axis-motors-idlers-and-pulleys-to-side-plates). Geared stepper motors (E18) mount into the same large holes on M20.a / M29.a as on P20 / P29.

## Y-axis belt tensioners and end-stop mounts

The metal side plates have the same hole pattern as the plastic ones for belt tensioners (P17–P19, P26–P28) and end-stop mounts (P08). Follow [plastic instructions](../02-y-axis.md#y-axis-belt-tensioners-and-end-stop-mounts).

## Y-axis HTD5M belts

Unchanged. Follow [plastic instructions](../02-y-axis.md#y-axis-htd5m-belts).
