# Render Improvements

If I run:
```sh
hardware_mods/metal_plates/assembly/view_assembly.sh VI
```
R.0 I want the object to be in the center of the screen (where the red dot is when you rotate).
R.1. I want the complete subcomponent to be streched out as large as possible, until it hits either the max width and max height of the window box. (So that I don't have to search for the object zooming in and zooming (and then accidentally zooming out so far that it is not visible anymore, or panning so far away at zoomed out level that I will not find it anymore.)) 
R.2 I want the navigation method set to touchpad by default.

---

## I — Aluminium frame
Render: `subcomponents/cnc_subcomponent_I_explode.gif`


---

## II — Left side plate & Y-axis (gantry holder)
Render: `subcomponents/cnc_subcomponent_II_explode.gif`

### Side plate / U-bridges

![Physical reference — left- and right-side plate clamps holding the gantry beams (M20cd front clips)](../examples/II_side_plates/M20cd_front_clips/Screenshot%20From%202026-06-27%2000-24-02.png)

### Mid-plate

---

## II_R — Right side plate & Y-axis (mirror of II)
Render: `subcomponents/cnc_subcomponent_II_R_explode.gif`

---

## III — Gantry & X-axis (three steel cross bars + rails)
Render: `subcomponents/cnc_subcomponent_III_explode.gif`


---

## IV — Vertical engine plate p1of2 (+ MGN12H blocks)
Render: `subcomponents/cnc_subcomponent_IV_explode.gif`


---

## V — Top & bottom stepper plate (stepper, belt/gears, threaded rod)
Render: `subcomponents/cnc_subcomponent_V_explode.gif`


---

## VI — Vertical engine plate p2of2 (+ two router clamps + rails)
Render: `subcomponents/cnc_subcomponent_VI_explode.gif`
3. The rectangular take out for the bolt to bolt the first half of the clamp against the front of the plate is missing. 
4. The hole on the right side of the clamps (that bolts the router clamps to the front of the plate), is missing. This is the hole like 
cnc_live_VI.Router_Clamp_Top.edge5  (near cnc_live_VI.Router_Clamp_Top.Edge3)
but which lives in the 
cnc_live_VI.Router_Clamp_Top.Face1
plane, but then on the right side of that face, near 
cnc_live_VI.Router_Clamp_Top.Edge1.
5. Same as 4 but then for the bottom clamp.
6. The 2 half moons consisting of:
cnc_live_VI.Engine_Holder_P2.Edge184
cnc_live_VI.Engine_Holder_P2.Edge185
cnc_live_VI.Engine_Holder_P2.Edge186
cnc_live_VI.Engine_Holder_P2.Edge187
can be removed, same as the holes
cnc_live_VI.Engine_Holder_P2.Edge182
cnc_live_VI.Engine_Holder_P2.Edge183
7. The rectangles containing:
cnc_live_VI.Engine_Holder_P2.Edge102
cnc_live_VI.Engine_Holder_P2.Edge105
cnc_live_VI.Engine_Holder_P2.Edge109
cnc_live_VI.Engine_Holder_P2.Edge98
cnc_live_VI.Engine_Holder_P2.Edge95
and the one containing 
cnc_live_VI.Engine_Holder_P2.Edge134 etc. too.
And the holes/bolts/whatever at:
cnc_live_VI.Bolt_P2_379_140_0_M3.Face5
cnc_live_VI.Bolt_P2_379_140_1_M3.Face5
cnc_live_VI.Bolt_P2_379_140_2_M3.Face5
cnc_live_VI.Bolt_P2_379_140_3_M3.Face5
and:
cnc_live_VI.Engine_Holder_P2.Edge197
cnc_live_VI.Engine_Holder_P2.Edge198

cnc_live_VI.Engine_Holder_P2.Edge199
cnc_live_VI.Engine_Holder_P2.Edge200
should go

and the same for the construction at the left side with (amongst others):
rectangle:
cnc_live_VI.Engine_Holder_P2.Edge134
boltes/nuts/whatever:
cnc_live_VI.Bolt_P2_444_140_0_M3.Face5
cnc_live_VI.Bolt_P2_444_140_1_M3.Face5
cnc_live_VI.Bolt_P2_444_140_2_M3.Face5
cnc_live_VI.Bolt_P2_444_140_3_M3.Face5
holes:
cnc_live_VI.Engine_Holder_P2.Edge201
cnc_live_VI.Engine_Holder_P2.Edge202
cnc_live_VI.Engine_Holder_P2.Edge203
cnc_live_VI.Engine_Holder_P2.Edge204


### Plate outtakes & rails

### Router clamps


### Router-clamp holder ("clock-like" shape)


