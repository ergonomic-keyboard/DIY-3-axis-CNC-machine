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

