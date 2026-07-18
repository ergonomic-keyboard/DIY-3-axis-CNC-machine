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

---

## IV — Vertical engine plate p1of2 (+ MGN12H blocks)
Render: `subcomponents/cnc_subcomponent_IV_explode.gif`


## V — Top & bottom stepper plate (stepper, belt/gears, threaded rod)
Render: `subcomponents/cnc_subcomponent_V_explode.gif`
Move the top stepper holder plate such that cnc_assembly_live.Bolt_P1_Top_TL_M5.Face4 goes through the hole cnc_assembly_live.Top_Stepper_Holder.Edge20 and such that cnc_assembly_live.Bolt_P1_Top_TR_M5.Face4 goes through the hole: cnc_assembly_live.Top_Stepper_Holder.Edge46.

---

## VI — Vertical engine plate p2of2 (+ two router clamps + rails)
Render: `subcomponents/cnc_subcomponent_VI_explode.gif`
The vertical engine plate p2of2 should rotate 180 degrees around Z-axis, such that its rail outtakes are over the vertical MGN12 rails. The vertical MGN12H blocks should be bolted on to the vertical engine plate p1of2 (instead of p2of2). The vertical mgn12h rails should then sit into those mgn12h blocks.

### Plate outtakes & rails

### Router clamps


### Router-clamp holder ("clock-like" shape)


### Constellation
