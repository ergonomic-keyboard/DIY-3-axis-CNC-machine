# Render Requirements

PRIMARY REQUIREMENTS:

A. And for the http://127.0.0.1:8000/DIY-3-axis-CNC-machine/metal/
page:
A.0 Create 5 sub tabs:
A.0.I Aluminium frame.
A.0.II Left and right gantry holders with hm5 band and its hmd5 band holders and its tensioner, and how that is mounted on the aluminum frame.
A.0.III The gantry of the 3 steel cross bars, and the hdm5 band that goes accross that, along with its clamp and tensioner that is mounted on the gantry, and the rails that are screwd onto 2 of the 3 horizontal gantry steel bars.
A.0.IV The vertical engine plate p1_of2, the mgn12h blocks that are bolted onto it, and how that is mounted on the gantry with the other MGN12H blocks that are mounted on its backside.
A.0.V The top and bottom plate that go onto the engine_plate p1_of2 and how they will house the stepper and 3:20 stepper moter belt and gears, along with the vertical threaded rod. 
A.0.VI The vertical engine plate p2of2 and the 2 cnc router clamps and the rails that are bolted to it.
A.1 Per page table of the E/P etc. numbers, like E03 E14, O22 etc. from the:
http://127.0.0.1:8000/DIY-3-axis-CNC-machine/shopping/
page,  and indicate which ones are from the plastic variant (and not used anymore, like the P20 left side plate and how they are replaced by metal parts, like the 3 metal components now. Give them M20.a M20.b M20.c as identifiers, and give the human name referred in this chat like engine_holder_p1of2 in that table. 
A.2  show the 3d gif of each of those components groups, first individually as component, and then how the component of each page of e.g. A.0.II for that page are assembled with exploded view coming together.
A.3 Then have a full page  that shows the assembly of the whole CNC based on the assembled submodules of A.0.I to A.0.VI.
A.4 For each of the sub assembly pages use the text and fotos of http://127.0.0.1:8000/DIY-3-axis-CNC-machine/01-main-frame/ and 
http://127.0.0.1:8000/DIY-3-axis-CNC-machine/04-stepper-motors-and-end-stops/ etc. to include the instructions written and with the fotos as guide (even though some may only be from plastic components that are not used anymore). Name each foto (copy pastable name, so I can quickly tell you which fotos should move where if you put them in the wrong place.)


B.0 Use the manual designs where available.
B.1 Include an image of the 3d render of the replacement metal part(s) in the table next to the image of the original plastic part.



C.0 Ensure a 3d render of each metal part is available. 
C.1 Ensure the connection mechanisms function. (For example m36a_plan shows 4 hexacgonal nut heads in the right position in the drawing, but actually those top 2 bolts should be rotated 90 degrees to point upwards, (instead of into the screen), and similarly the bottom ones should point downwards. The usage of bolts is weird in this design as some go into the sides of the plates instead of through the flat holes of the plates like one normally bolts ).
C.2 Ensure all connection mechanisms, like bolts are parametererised, such that if one swaps out a M4 bolt with an M5 bolt, that it updates the accompanying holes.
C.3 Ensure the assembly physically is possible, e.g. make sure the bolts do not go through the metal (instead of through a hole).
C.4 Add threads into the designs, or at least a thread specification per hole where appropriate.
C.5 Ensure you update the freecad models where necessary (with versioning in the name.)
C.6.0 Make the assembly of the sub componets:
Overview & full assembly
I. Aluminium frame
II. Side plates & Y-axis
III. Gantry & X-axis
IV. Engine plate p1of2
V. Z-axis drive
VI. Engine plate p2of2 & router
as a exploded view towards assembly script (with parameterisation).
C.6.1 Ensure those visualisations are both visible (in Freecad as movement animation if possible, and) as gif and .mp4.
C.6 Then ensure the sub-components assembly is visualised in 1 large visualisation.


## Handover data:

Handover for new chat — DIY CNC machine docs, branch retry-assembly-renders


We've been building metal instruction pages under docs/metal/ for the MkDocs site (mkdocs serve running at http://127.0.0.1:8000). Read the memory file project_docs_metal_pages.md for full state.


What's working:

A global thumbnail slider (part-thumb-slider.js) auto-injects a "Thumbnails" size control on any page with .part-thumb images. CSS variable --part-thumb-size lives on :root. The slider persists to localStorage.
All 6 metal pages (01–06) have labeled build photos (` filename above each image) and thumbnail columns in the Components table using ![alt](../images/...){.part-thumb} syntax (markdown, not raw HTML — important for MkDocs path rewriting).