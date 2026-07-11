# Render Improvements

Improvements to the exploded-view renders (`assembly/subcomponents/*.gif`), captured as
voice notes and transcribed. These describe what is missing or wrong in the renders as they
existed **before** the yamlification refactor. Structured per subcomponent, matching the
`A.0.*` grouping in [`Render_requirements.md`](./Render_requirements.md).

---

## I — Aluminium frame
Render: `subcomponents/cnc_subcomponent_I_explode.gif`

Where the metal frame is composed, the following are all missing:

1. Holes for the threads through the small vertical rails / pipes / rectangular beams.
2. The rings (washers) that go around each thread.
3. The bolts themselves.
4. The holes in the beam.
5. The wrench/socket access holes to reach through and tighten the bolts — missing for
   both the vertical rods and the side rods.
6. The holes for the MGN12H rails.
7. The screws for the MGN12H rails.
8. The threads for those rail screws.

---

## II — Left side plate & Y-axis (gantry holder)
Render: `subcomponents/cnc_subcomponent_II_explode.gif`

### Side plate / U-bridges
1. It currently consists of **four** metal components but should consist of **three**.
2. The outer two should be a **single** component instead of two separate U-bridges
   (otherwise they are okay). See the *left-side clamp* in the reference photo below.
3. Their width/thickness is too large (~2–3 cm) — it should be only ~1 cm.
4. The clamp that holds the front gantry beam should be **rotated 90°** so the U-outtake
   actually clamps the beam; as-is it would not clamp the beam.
5. That clamp should also extend further **up and down** than it currently does — giving it
   the trapezoid/triangle profile of the *right-side clamp* in the reference photo below — so
   it has the stiffness to really clamp and hold the beam in place. (Its hole is correct
   position-wise; the diameter is unverified.)

![Physical reference — left- and right-side plate clamps holding the gantry beams (M20cd front clips)](../examples/II_side_plates/M20cd_front_clips/Screenshot%20From%202026-06-27%2000-24-02.png)

### Mid-plate
1. The bottom four holes that hold the MGN12H blocks (which ride over the central-frame rails)
   have different diameters — the bottom-right one is small, the others are large. They should
   **all be small**. They don't need threads, since the bolts go on the outside.
2. The two large holes above them are too high — they would intersect the thread that runs
   through the gantry beams holding the plate in place. They should **move down**.
3. The hole for that thread (through the gantry beams) is **missing**.
4. Those two large holes are for the spacers that hold / guide the HTD5M belt over the stepper
   motor.
5. The large hole for the stepper motor itself is **missing**.
6. On top, the thread is **missing** for the clamp that goes through the gantry beam.

---

## II_R — Right side plate & Y-axis (mirror of II)
Render: `subcomponents/cnc_subcomponent_II_R_explode.gif`

1. Should be **symmetrical** to the left side plate (II). The same improvements listed under
   component II apply here mirrored.

---

## III — Gantry & X-axis (three steel cross bars + rails)
Render: `subcomponents/cnc_subcomponent_III_explode.gif`

1. The screws that attach the rail to the steel gantry bars are **missing**.
2. The bolts are **missing**.
3. The corresponding holes are **missing**.
4. The holes that let the side plates clamp the beams in place — near (not exactly at) the
   ends of the beams — are **missing**.

---

## IV — Vertical engine plate p1of2 (+ MGN12H blocks)
Render: `subcomponents/cnc_subcomponent_IV_explode.gif`

1. The outtake lacks the CNC channel (rout) for the threaded rod. It has the rectangular hole
   that lets the thread-holder move up and down (guidance for the holder), but no guidance for
   the thread itself. The channel should extend from that hole both up and down, be **less
   wide** than the rectangular outtake, and be only slightly wider than the thread so the
   thread can rotate freely within it.
2. The bolts are correctly positioned in the outtakes, **except** they are upside-down on the
   top part.
3. On the bottom part, the outtakes for the bolt heads are in place, but the channels that
   guide the bolts to the outside are **missing**.
4. The MGN12 blocks on the **back** of the plate (that bolt onto the gantry) are in the right
   position, but the blocks themselves are **missing from the visualization** — they should be
   shown bolted on, and their bolts are missing too.
5. The MGN12 blocks clamped on the **front** are in the wrong position: too high, too far
   right, too far above. (The bolts do appear present in those blocks.)
6. The big hole appears correct.
7. The two large holes below the big hole (for HTD5M belt guidance) appear correct.

---

## V — Top & bottom stepper plate (stepper, belt/gears, threaded rod)
Render: `subcomponents/cnc_subcomponent_V_explode.gif`

1. Six holes are missing on top. Two on the outside so the plate can be clamped onto the
   vertical plate that sits on the gantry rails — this plate goes on top there, and those two
   bolts go into the bolt outtakes width-wise.
2. Two holes on the inside — purpose currently unclear.
3. Two small holes to bolt the large-gear plate onto this plate, so the thread can pass in
   between; the vertical thread should also be able to pass through this plate. All these holes
   are missing in the high T-bar section.
4. The O-shaped outtake is good; the middle longitudinal oval shape is good.
5. The small oval slots on the sides: currently there are two on **one** side. There should be
   two on **each** side (four total) instead of two.
6. There are four surrounding holes near them — the bolts should just go through the small oval
   side outtakes.

---

## VI — Vertical engine plate p2of2 (+ two router clamps + rails)
Render: `subcomponents/cnc_subcomponent_VI_explode.gif`

### Plate outtakes & rails
1. The middle rectangular outtake should move all the way up to the top edge.
2. The bolt outtake in the middle should go down, below that rectangular outtake.
3. The rectangular outtake should be at most 2–4 cm deep.
4. Directly below it there should be, in order: first the **thin part** (lets the bolt thread
   pass through), then the **wider bolt outtake** (houses the bolt head).
5. It is missing the rail groove / outtake (the "rail river") — that should be CNC'd out.
6. It is missing the holes used to mount the rails onto the plate.
7. It is missing the threads for the bolts of those rails.
8. It is missing the rail bolts themselves.

### Router clamps
1. The router clamps currently have an outtake only on the right side; they should have two —
   cut in half so there is also one on the **left** side. This lets the clamps be removed and
   the router placed in between, after which the bolts go in.
2. The bolts are in the wrong position **and** wrong direction: they should point **toward** the
   plate, not away from it.
3. They shouldn't be bolts but **large threads** that go through the plate itself.
4. The holes for those threads are missing for the **top** clamp (the bottom clamp has them).
5. The router clamp should have a small outtake for the thread through the plate. Assembly
   order: thread through plate → router clamp over the thread → nut → the other clamp →
   another nut to tighten.
6. The router clamp should still be able to close toward the ramp — it should not be pushed
   against the middle nut, so that it can be tightened.

### Router-clamp holder ("clock-like" shape)
1. The clock-like shape that holds the router clamp is missing a **routed thread** — the
   vertical thread that guides the router up and down.
2. Its basic shape: a rectangle with a half-circle on top, a small circle in the middle, four
   small holes around it, and one large hole in the center of the rectangle.
