# Developers

This site is built with [MkDocs](https://www.mkdocs.org/) using the [Material](https://squidfunk.github.io/mkdocs-material/) theme. The source for every page lives in `docs/`, and navigation is configured in `mkdocs.yml`. Deployment to GitHub Pages happens automatically on every push to `main` (see `.github/workflows/`).

## Prerequisites
- Python 3.x
- `pip`

## Install dependencies
```sh
pip install mkdocs-material
```

## Commands to run locally

One command — starts both `mkdocs serve` (the site) and `tools/refresh_server.py`
(the write-through helper) so that any edit you make on the Shopping page lands
directly in `docs/data/*.json` and shows up in `git diff` — no Export/merge
step, no "oops I forgot the helper and lost my edits" failure mode (SL-10.U /
SL-10.V):

```sh
python3 tools/dev.py
```

The shopping page is then at
<http://127.0.0.1:8000/DIY-3-axis-CNC-machine/shopping/>. Ctrl-C stops both
processes cleanly. Pass `--mkdocs-port` / `--helper-port` if you need
non-default ports.

If you only want the site (no write-through) — for example when reviewing
content that has nothing to do with shopping:
```sh
mkdocs serve
```

Build the static site into `site/`:
```sh
mkdocs build
```

Deploy manually to GitHub Pages (normally handled by CI):
```sh
mkdocs gh-deploy --force
```

## Project structure
- `docs/` — Markdown pages, images, STL/OBJ files, and the bill of materials.
- `mkdocs.yml` — site configuration and navigation order.
- `.github/workflows/` — CI pipeline that publishes the site on push to `main`.
- `claude/` — working notes and objectives (not published).

## Adding a new page
1. Create the Markdown file under `docs/` (follow the `NN-name.md` numbering convention).
2. Add an entry to the `nav:` section of `mkdocs.yml` in the desired position.
3. Verify locally with `mkdocs serve` before pushing.

## Shopping data snapshot

The Shopping page (`docs/shopping.md`) is rendered entirely from three static JSON
files in `docs/data/`. The site is static — nothing is fetched at runtime from
external shops. To update prices, edit the snapshot (manually or via a future
GitHub Action) and commit.

### Files

- **`docs/data/shops.json`** — list of shops and countries. Each shop carries
  a `currency` (ISO-4217), a `home_url`, and a `shipping` block with
  `standard_cost`, `free_above` (free-shipping threshold; set to `0` to disable),
  and `default_eta_days`.
- **`docs/data/items.json`** — index of every BOM item by `code` (e.g. `E09`),
  with `category`, `name`, `qty`, and an optional `qty_note` for free-form
  quantities like `~10m`. Keep this in sync with `docs/BILLOFMATERIAL.md`.
- **`docs/data/prices.json`** — one entry per `(item_code, shop)` pair, with a
  product `url`, an optional `ean`, and an `observations` array. Each
  observation has a `ts` (ISO-8601), `price`, `currency`, `in_stock`, `eta_days`,
  and an optional `note`. The newest observation is what the UI displays; the
  full list is the price history (SL-3.c) — never overwrite it, always append.

### Refreshing prices manually

1. Open the product page on the shop, copy the price.
2. Find the matching `entries[]` row in `docs/data/prices.json`. Prepend a new
   observation with today's timestamp; keep the older observations intact.
3. Update `last_updated_at` at the top of `prices.json`.
4. Run `NO_MKDOCS_2_WARNING=1 mkdocs serve` and confirm the Shopping page
   renders without errors.

### Refreshing prices automatically

`tools/refresh_prices.py` walks `docs/data/prices.json`, fetches each shop URL,
parses `Schema.org/Product` JSON-LD, and **appends** a new observation when it
finds a price. History is never overwritten.

```sh
python3 tools/refresh_prices.py --dry-run   # show what would change
python3 tools/refresh_prices.py             # write prices.json
```

The companion workflow `.github/workflows/refresh-prices.yml` runs this weekly
(Sundays 04:17 UTC) and on demand via the **Run workflow** button, and opens a
PR with the diff. Never let it push directly to `main`.

Reliability — what works and what doesn't:

- **TinyTronics, 123-3D, most small shops**: JSON-LD on product pages is solid.
  Works reliably as long as the URL points at a concrete product (not a
  category or search page).
- **Conrad NL**: behind Cloudflare. Returns 403 to the script. Fill manually.
- **Bol.com, Amazon.nl**: aggressive bot filters; effectively require their
  affiliate APIs (Plaza / PA-API), which need a registered seller/affiliate
  account. Listed in `SKIP_SHOPS` so the script doesn't even try.
- **AliExpress**: URLs in the snapshot are search queries (per-seller variant
  pricing makes a single product URL meaningless); skipped by design.

When you add a new shop, decide which bucket it lands in and update
`SKIP_SHOPS` accordingly. The cheapest path to coverage is always: open the
product page, copy the URL, run the script.

### Syncing item images from BOM

`tools/sync_bom_images.py` parses `docs/BILLOFMATERIAL.md` and writes each
item's image path into `docs/data/items.json` (used by the Shopping page to
show a thumbnail next to every row — SL-8.a). Re-run any time BOM images
change:

```sh
python3 tools/sync_bom_images.py
```

## Freecad
View subcomponent (from repo root):
```sh
hardware_mods/metal_plates/assembly/view_assembly.sh VI
```

Show the parameter dimensions (R.3) — labelled double-arrows for each locatable value
from the master `parameters.yaml`:
```sh
hardware_mods/metal_plates/assembly/view_assembly.sh VI --params
```
It draws:
- **overall extents** (matched by value, e.g. `PLATE_WIDTH = 110 mm`, `PLATE_THICK = 12 mm`)
  and a lone **bore** as on-part double arrows;
- a parameter that spans **multiple features** (e.g. a shared hole diameter, or the
  mgn12h rail holes) as **many leader lines to ONE shared label parked in the top-right
  legend** (R.4) — instead of one cluttered dimension per hole.

**Binary per-parameter toggle:** each part block in `parameters.yaml` may carry a
`_show:` list — only those parameters are drawn (omit a name to hide it). Without `_show`
the overlay falls back to the extents + any large bore. So to turn a parameter's
annotation on/off, add/remove it from that part's `_show`.

**Coverage** (which sub-components the overlay annotates): **VI** (2 router clamps + the
plate rail holes), **V** (stepper plate: `PLATE_THICKNESS`, `POCKET_DIAM`), **IV** (p1of2
plate: `PLATE_THICKNESS/WIDTH/HEIGHT`, `BORE_DIAM`, `ACCESS_HOLE_DIAM`, and the ×36
`RAIL_BOLT_DIAM` many-to-one), **III** (belt clamp: `BODY_X/Y/Z` — but the clamp is tiny
beside the gantry beams, so zoom to it to read the labels). IV's p1of2 is a manual-design
plate with no generator, so its `parameters.yaml` block is **annotation-only** (no
`_dir`/`_script`; the values are measured-dimension snapshots). **II is not covered**: the
M20 side-plate clips are fused / re-modelled into `Side_Plate_Front_Clamp` /
`Side_Plate_Beam_Clamp` (different objects, trimmed geometry), so their `parameters.yaml`
blocks don't map to a distinct assembly object. **I** (aluminium frame) has no parametric
part. Label/arrow sizes scale with the shown extent (`fs`) so small parts stay legible.

The many-to-one legend callouts are each drawn in a distinct colour cycled from
`_ANNO_COLORS` (so overlapping bundles stay separable); the plain on-part dimensions
(extents + lone bore) use `_DIM_COLOR` — **white** by default, so the text reads on the
viewer's dark/gradient background. (On-part dimensions are drawn from Part edges + a
Draft **Text**, not `Draft.makeDimension`, because the built-in Draft Dimension text
ignores `TextColor` in this build and always renders black.) The solid parts are made
semi-transparent (`_PARAMS_TRANSPARENCY`, default 60 %) in this overlay so each leader
reads end-to-end — its feature end shows through the material instead of being cut off
inside it. (Leaders keep ending exactly at the real holes; that's why transparency is
used rather than stopping them at an outer surface, which would detach them from the
holes and still be occluded by neighbouring parts.)

The object→(subcomponent, part) map, the non-parametric callouts (e.g. rail holes), and
the drawing live in `assemble_and_render.py` (`_PARAMS_OBJ`, `_EXTRA_CALLOUTS`,
`_load_master_params`, `_annotate_params`, `_make_callout`). The legend is anchored in
world space off the top-right of the fitted isometric view, so it reads top-right on
open; orbiting moves it with the model (3D annotations aren't screen-locked).

**All script-built part parameters are consolidated in one file:
`hardware_mods/metal_plates/parameters.yaml`** — grouped by sub-component so it is
obvious which parameters drive which part. Edit values there; each part's
`<script>.py` reads its block from that master on run (matched by `_dir` + `_script`).
Then to show all (eye) components of that subcomponent in top: `View>Panels>Python Console` and paste and run:
```py
# show everything
for o in App.ActiveDocument.Objects:
    if o.ViewObject: o.ViewObject.Visibility = True
```
Then Hide all (shut eye) components:
```sh
# hide everything
for o in App.ActiveDocument.Objects:
    if o.ViewObject: o.ViewObject.Visibility = False
```

### Dev shortcut — copy a hovered element's path (F4)

When you open the viewer (`view_assembly.sh [SC]`), press **`F4`** while hovering over
an edge/face/vertex to copy its full path — e.g. `cnc_live_VI.Engine_Holder_P2.Edge200`
— to the clipboard, ready to paste into `render_improvements.md`. Hover so the element
is *preselected* (its path shows in the status bar), press `F4`, then paste. **Nothing
to install** — the viewer's startup script sets it up every launch.

How it works (and why it's fiddly): FreeCAD has no built-in shortcut for this —
`getPreselection()` only exposes the hovered element to a macro. And a normal
command/keyboard shortcut does **not** work over the 3D view: the Coin viewer swallows
shortcut keys, and touchpad navigation claims *every* modifier combo held over the view
(`Ctrl+Shift` = zoom, `Ctrl+Alt` = rotate, …). So `view_assembly.sh` installs an
**application-wide Qt event filter** (in its generated `_view_setup.py`) that catches
the `F4` key press before any widget sees it and copies the preselection. To change the
key, edit `QtCore.Qt.Key_F4` in the event-filter block of `view_assembly.sh`.

There is also a standalone `.freecad/Macro/CopyPreselection.FCMacro` plus an optional
installer `python3 .freecad/setup_dev_macros.py` that registers it as a **"Dev macros"**
toolbar/menu command for general (non-viewer) FreeCAD use — but note its keyboard
shortcut is subject to the 3D-view limitation above; the reliable path is the viewer's
`F4`.