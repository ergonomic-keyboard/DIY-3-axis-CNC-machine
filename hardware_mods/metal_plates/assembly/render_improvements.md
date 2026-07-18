# Render Improvements

If I run:
```sh
hardware_mods/metal_plates/assembly/view_assembly.sh VI
```
R.0 I want the object to be in the center of the screen (where the red dot is when you rotate).
R.1. I want the complete subcomponent to be streched out as large as possible, until it hits either the max width and max height of the window box. (So that I don't have to search for the object zooming in and zooming (and then accidentally zooming out so far that it is not visible anymore, or panning so far away at zoomed out level that I will not find it anymore.)) 
R.2 I want the navigation method set to touchpad by default.
R.3 Add an argument to visually show the parameters (e.g. with an double sided arrow spanning a width or something) of the parameters in router_clamp.parms.yaml, <>.params.yaml etc.
R.4 If a parameter spans multiple items of a subcomponent, e.g. the holes of the mgn12h rails, use multiple leader lines from pointing to ONE single shared text label/annotation (many-to-one).
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
For 2 Gantry beams that are on top of eachother (same x-coordinate) that are furthest in the positive x-direction: The mgn12H rails should be on the other side, so  not on the face pointing to negative x-direction, but on the face in positive x-direction. 

---

## IV — Vertical engine plate p1of2 (+ MGN12H blocks)
Render: `subcomponents/cnc_subcomponent_IV_explode.gif`
1. Like the gantry mgn12h rails, it should be moved further the other side, except the mgn12h rails should rotate 180 degrees around z or y-axis, this plate is already pointing in the right direction, but it currently goes through the gantry beams. Instead its mgn12h blocks should mount on the mgn12H rails that will be moved to the other side of the gantry beams.


## V — Top & bottom stepper plate (stepper, belt/gears, threaded rod)
Render: `subcomponents/cnc_subcomponent_V_explode.gif`


---

## VI — Vertical engine plate p2of2 (+ two router clamps + rails)
Render: `subcomponents/cnc_subcomponent_VI_explode.gif`
1. This move in positive x-direction such that its mgn12 blocks are on the vertical mgn12h rails of the plate 1of2.

### Plate outtakes & rails

### Router clamps
These should rotate 180 degrees around the z-axis and be mounted to the front(most positive x-axis) side of the engine plate p2of2.

### Router-clamp holder ("clock-like" shape)


### Constellation
