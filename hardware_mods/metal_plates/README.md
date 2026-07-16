# Metal plates

Aluminium versions of the plastic 3D-printed parts, generated with
[`build123d`](https://build123d.readthedocs.io/) using hole positions
recovered from the plastic STLs and silhouettes traced from the build
video screenshots.

## Structure

Metal-plate designs live under
`hardware_mods/metal_plates/examples/`, grouped by sub-assembly (I–VI,
matching `docs/metal/01-…06-…md`) and named by their M-code
(`M20a_left_body`, `M36a_vertical_plate`, `MX1_engine_sideways_belt_clamp`,
…).  See `examples/README.md` for the full mapping.

A canonical example of the numbered-stage layout inside one part folder is
`hardware_mods/metal_plates/examples/II_side_plates/M20a_left_body/`.

## Procedure
and for each component, 
0. I will start with a raw screenshot,
1. The original splastic images are used as a reference.
2.a The image will be flattened by opening a python command 
2.b and selecting 4 points on the image of which the coordinates are known (from the accompanying dril holes of the `.stl` files of the plastic parts (the holes stay the same just the outline/form changes)).
2.c You provide me with the description of those 4 coordinates so I know where to click.
3. You pit out the flattened image into 2_flattened_image
4. I will do some measurements on that flattened image, and store the printscreens of each of those into: 3_measurements.
5. Then I will use the 2_flattened image to draw the outline geometry of that aluminium part. Once I press quite you will store the output of that outline into 4_outline.
6.a I will then ask you to use the 3_measurements and 4_outline to generate a 3d model of the aluminum part including the holes, 
6.b and you will create a render in the form of an as an image, 
6.c and you will allow me to inspect the model in a 3d viewer. 
6.d Additionally you parameterise all the geometries (e.g. angles length sides) so I can easily modify them (and regenerate the model). 
6.e You shall use build123d to generate the model.

7. You shall throw a warning if the hole positions or sizes are modified w.r.t. the plastic stl position. 

8. Ideally you show the transparent overlay of the plastic part mapped on the exactly the same position based on the hole positions so I can easily verify the parts align well/are compatible.

## Authoring geometry in YAML

Part geometry can be edited as **commented, grouped, parametric YAML** instead
of raw JSON / bare Python constants. Each authoring file has an "expand" step
that compiles it into what the builders already consume; the builders prefer the
compiled artifact and fall back to the legacy inputs when it is absent, so
nothing breaks for parts that have not been converted.

| Part type | Author in | Compile with | Builder reads |
|-----------|-----------|--------------|---------------|
| `build_model` plates (holes) | `2_flattened_image/holes.yaml` | `expand_holes.py --example <EX>` | `holes.json` |
| `build_model` plates (outline) | `4_outline/outline.yaml` | `expand_outline.py --example <EX>` | `outline.json` |
| script-built parts (clips, clamps, belt clamp, stepper holder) | `metal_plates/parameters.yaml` (one block per part) | *(none — the script loads it on run)* | its `<script>.py` |

`holes.yaml` groups holes (shared radius, `rect4` bolt patterns numbered
clockwise-from-top-left with `dx`/`dy`, thread table, datum-relative `z_from_bottom`);
`outline.yaml` lists vertices with per-edge `constraint`/`group` and comments.

**All script-built part parameters live in the single master `metal_plates/parameters.yaml`**,
grouped by sub-component (II / III / V / VI) so it is obvious which parameters drive
which part.  Each block carries `_dir` + `_script` (identifying the part) and its
UPPER_CASE constants (shipped equal to the script defaults, so behaviour is unchanged
until edited).  On run, each `<script>.py` walks up to find this master and overrides
its constants from the matching block — so parameters are edited in one place.

Converted so far: **M20a** (holes + outline) and every script-built part. The two
manual-design plates (**M36a**, **M36b**) come from `manual_design/*.FCStd` and are
edited in FreeCAD, not YAML.

The expanders need PyYAML — run them with the FreeCAD AppImage python
(`~/.local/opt/FreeCAD-1.1.1/usr/bin/python`) or any python with `pip install pyyaml`.

## Commands

`<EX>` = your example folder (e.g.
`hardware_mods/metal_plates/examples/II_side_plates/M20a_left_body`).

### Running on Nix or Ubuntu (auto-detected)

The scripts detect their environment automatically (`env_bootstrap.py`), so you
do **not** have to remember which machine you are on:

- **NixOS** — run inside the project shell as before; its `shellHook` creates and
  populates a repo-root `.venv` from `requirements.txt` on first entry:
  ```sh
  nix-shell hardware_mods/metal_plates/shell.nix --run \
    "python hardware_mods/metal_plates/build_model.py --example <EX>"
  ```
- **Ubuntu (no Nix)** — set up the toolchain once, then run the scripts with any
  `python3`; they re-exec into the `.venv` themselves:
  ```sh
  bash hardware_mods/metal_plates/setup_env.sh          # once: creates .venv
  python3 hardware_mods/metal_plates/build_model.py --example <EX>
  ```

If `build123d` is not importable and no environment is set up, the script prints
the exact setup command and exits — it never installs anything behind your back.
The FreeCAD render pipeline (`assembly/`) locates FreeCAD the same way (extracted
AppImage on Ubuntu, `nixpkgs` on NixOS); no configuration needed.

The nix-shell command form below still works on NixOS.

```sh
# 1. Flatten the photo + trace the outline (stages 2 + 5).
nix-shell hardware_mods/metal_plates/shell.nix --run \
  "python hardware_mods/metal_plates/rectify.py \
     --example <EX> --stl docs/stl_files/side_plates/left/LEFT_PLATE.stl"

# 2. Build STEP / STL / plan PNG / plastic overlay (stages 6–8).
nix-shell hardware_mods/metal_plates/shell.nix --run \
  "python hardware_mods/metal_plates/build_model.py --example <EX>"

# 3. (Optional) Interactive H/V + snap-to-plastic editor.
nix-shell hardware_mods/metal_plates/shell.nix --run \
  "python hardware_mods/metal_plates/align_outline.py --example <EX>"
```

Run any script with `--help` to see flags and interactive controls.

```sh
EX=hardware_mods/metal_plates/examples/IV_engine_plate_p1of2/M36a_vertical_plate
PHOTO="$EX/0_raw_screenshots/starting_point.png"
STL=docs/stl_files/router/CARRIAGE.stl
nix-shell hardware_mods/metal_plates/shell.nix --run \
  "python -u hardware_mods/metal_plates/rectify.py --example $EX --stl $STL --photo \"$PHOTO\""

```