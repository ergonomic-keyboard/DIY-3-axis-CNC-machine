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

- **Y-belt:** add an HTD tensioner belt across the frame top rail (over `Frame_Up_Left_Y.Face3`), with a tensioner at one end. Y-axis drive — stepper lives in II_R.

---

## II — Left side plate & Y-axis (gantry holder)
Render: `subcomponents/cnc_subcomponent_II_explode.gif`

### Side plate / U-bridges

![Physical reference — left- and right-side plate clamps holding the gantry beams (M20cd front clips)](../examples/II_side_plates/M20cd_front_clips/Screenshot%20From%202026-06-27%2000-24-02.png)

### Mid-plate

---

## II_R — Right side plate & Y-axis (mirror of II)
Render: `subcomponents/cnc_subcomponent_II_R_explode.gif`

- **Y-stepper:** mount the Y-axis stepper on the cnc_assembly_live.Engine_Holder_P1.Edge156. Add the belt that dfirves those mid plates
---

## III — Gantry & X-axis (three steel cross bars + rails)
Render: `subcomponents/cnc_subcomponent_III_explode.gif`

- **X-belt:** HTD5M belt runs across the top of `Gantry_Beam_Upper1.Face3`, anchored on the gantry beam near the side-plate ends (`Side_Plate_Left.Face56` + right mirror). On the other end, a tensioner instead of a clamp is tensioned with a bolt through the side plate. Stepper + idlers in IV.

---

## IV — Vertical engine plate p1of2 (+ MGN12H blocks)
Render: `subcomponents/cnc_subcomponent_IV_explode.gif`

- **Y-drive stepper:** mount on p1of2 at `Engine_Holder_P1.Edge156`, bolted via the holes at `Engine_Holder_P1.Edge345`.
- **X-belt drivers:** two HTD5M belt bearings in the two holes just below the stepper (`Engine_Holder_P1.Edge423` + the other). and the stepper would be in cnc_assembly_live.Side_Plate_Left.Edge17 it should move because it doesn't fit there anymore,  Feed the X-belt (III).

## V — Top & bottom stepper plate (stepper, belt/gears, threaded rod)
Render: `subcomponents/cnc_subcomponent_V_explode.gif`

- **Z-stepper:** seat the Z-axis stepper in the `Top_Stepper_Holder.Face31` hole, bolted with the four existing bolts `Bolt_TSH_235_506_M5` (`.Edge3` + the other three).

---

## VI — Vertical engine plate p2of2 (+ two router clamps + rails)
Render: `subcomponents/cnc_subcomponent_VI_explode.gif`

### Plate outtakes & rails

### Router clamps


### Router-clamp holder ("clock-like" shape)


### Constellation

## Additional components
