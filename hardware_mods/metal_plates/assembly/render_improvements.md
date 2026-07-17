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
1. Ensure the 4 mgn12H blocksfor the vertical rail are also mounted to the front of the plate, not only the horizontal rail mgn12H blocks on the back. 
2. Ensure the parameters are visualised in the render.
3. Ensure the bolt thread channels like the ones on top at:
cnc_live_IV.Engine_Holder_P1.Edge34
are also added in the bottom bolt head holes like:
cnc_live_IV.Engine_Holder_P1.Edge71
4. Ensure the bolt heads are in the bolthead head rectangles (instead of sticking out of the plate, make the bolt threads stick out the plate.)
 
---


## V — Top & bottom stepper plate (stepper, belt/gears, threaded rod)
Render: `subcomponents/cnc_subcomponent_V_explode.gif`


---

## VI — Vertical engine plate p2of2 (+ two router clamps + rails)
Render: `subcomponents/cnc_subcomponent_VI_explode.gif`

### Plate outtakes & rails

### Router clamps


### Router-clamp holder ("clock-like" shape)


### Constellation.
Ensure the 
cnc_assembly_live.Side_Plate_Beam_Clamp_R.Face2 
and cnc_assembly_live.Side_Plate_Beam_Clamp_R.Edge7
align with:
cnc_assembly_live.Gantry_Beam_Lower.Edge14 


and that the top rows and  similarly:
cnc_assembly_live.Side_Plate_Beam_Clamp_R.Edge9
cnc_assembly_live.Side_Plate_Left_R.Edge91
align/are on 
cnc_assembly_live.Side_Plate_Left_R.Edge91 of the gantry beam.

Also parameterise the cutout width such such that u-shaped outtakes described above perfectly slide around the gantry bars, and that tying bolt 
 cnc_assembly_live.Side_Plate_Left_R.Edge91
 presses the 2 u-shapes against the gentry beams instead of against eachother like <>. 
 Make it 1 millimeter, such that it has maximum flesh contact with the gantrybeam.
 Make both sides of the u-shape evenly span the gantry beam so 
 cnc_assembly_live.Side_Plate_Left_R.Edge91
 cnc_assembly_live.Side_Plate_Beam_Clamp_R.Edge9 
 are equally long, and combined have the length of:
 cnc_assembly_live.Gantry_Beam_Lower.Edge14-cutout_parameter_length (so practically 40-1=39mm)

Then fix that for the u-shaped gantry beams as well. (Move the gantry beams to realise that, ensure the front most (positive x) gantry beams are above eachother, (on same x-position. )