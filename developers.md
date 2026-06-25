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
To serve the website locally with live-reload at <http://127.0.0.1:8000/>:
```sh
mkdocs serve
```

To build the static site into `site/`:
```sh
mkdocs build
```

To deploy manually to GitHub Pages (normally handled by CI):
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

