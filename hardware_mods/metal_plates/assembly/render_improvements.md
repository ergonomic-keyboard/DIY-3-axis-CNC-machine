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

side_plate_mgn12h_blocks.png shows that the cnc_assembly_live.Side_Plate_Left.Edge25 and cnc_assembly_live.Side_Plate_Left.Edge26 cnc_assembly_live.Side_Plate_Left.Edge30 cnc_assembly_live.Side_Plate_Left.Edge29 holes are for the right (most x-positive mgn12h block and that the

cnc_assembly_live.Side_Plate_Left.Edge32, cnc_assembly_live.Side_Plate_Left.Edge31,cnc_assembly_live.Side_Plate_Left.Edge27, cnc_assembly_live.Side_Plate_Left.Edge25, cnc_assembly_live.Side_Plate_Left.Edge28 holes are for the left most (most negative x-position)) mgn12h block. Those holes all should get teh same diameter, such that the mgn12h block bolts go through them. Then those 2 mgn12hblocks should sit on the insides of the cnc_assembly_live.Side_Plate_Left, so between that cnc_assembly_live.Side_Plate_Left plate and the Rail_Y_Left.Face2. the other side is symmetric, so the Side_Plate_Left_R.Face5 should have the two mgn12h blocks mounted on it, and those blocks should then go on the Rail_Y_Right.Face4. PS that Rail is for the x-axis mobilitiy so its name is not quite sensible. (The Z-rails are correctly named, but the Belt_X.Face6 is for the y-direction mobility, so that is also not correctly named.)

cnc_assembly_live.Engine_Sideways_Belt_Clamp.Face3 that clamp should not be there, I don't know for which it is supposed to be. It should be at Clamp_X instead.


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
 You should flip the Stepper_Z 180 degrees around the X or Y axis, zo that it is on Top_Stepper_Holder.Face5 instead of on Top_Stepper_Holder.Face3.
---

## VI — Vertical engine plate p2of2 (+ two router clamps + rails)
Render: `subcomponents/cnc_subcomponent_VI_explode.gif`

### Plate outtakes & rails

### Router clamps


### Router-clamp holder ("clock-like" shape)


### Constellation

## Additional components
