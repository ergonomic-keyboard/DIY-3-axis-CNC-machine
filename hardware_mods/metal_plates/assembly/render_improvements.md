# Render Improvements

If I run:
```sh
hardware_mods/metal_plates/assembly/view_assembly.sh VI
```
R.0 I want the object to be in the center of the screen (where the red dot is when you rotate).
R.1. I want the complete subcomponent to be streched out as large as possible, until it hits either the max width and max height of the window box. (So that I don't have to search for the object zooming in and zooming (and then accidentally zooming out so far that it is not visible anymore, or panning so far away at zoomed out level that I will not find it anymore.)) 
R.2 I want the navigation method set to touchscreen by default.

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
1. The vertical mgn12H rails is mounted on the front (negative x-axis direction, the face that freecad calls "left" on the top right dice, front is actually the side view from the right and bottom and top are called top.). It should be mounted on the back.
2. The clamps should be mounted against the front of the plate. (instead of against the rails.)
3. The rectangular take out for the bolt to bolt the first half of the clamp against the front of the plate is missing. 
4. The hole on the right side of the clamps (that bolts the router clamps to the front of the plate), is missing.

### Plate outtakes & rails

### Router clamps


### Router-clamp holder ("clock-like" shape)


