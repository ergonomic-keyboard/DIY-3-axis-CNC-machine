"""Generate docs/data/mod_construction_parts.json from the repo.

Scans:
  hardware_mods/metal_plates/examples/<group>/<part>/  for each part:
    1_original_plastic_images/   → studio plastic photos
    0_raw_screenshots/           → build-video screenshots
    5_models_and_renders/        → metal model renders (PNGs)
    2_flattened_image/holes_from_stl.json   → source STL → drawing lookup
  docs/stl_drawings/<group>/<stem>_drawing.{png,json}
  docs/images/parts/consumables/{screws,nuts,washers}/   → fastener palette

Output JSON:
  {
    "parts": [ ... ],
    "fasteners": [ ... ]
  }

Run from repo root (no nix-shell required):
  python tools/build_mod_construction_data.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOCS = REPO / "docs"
EXAMPLES_REAL = REPO / "hardware_mods" / "metal_plates" / "examples"

# Paths in the JSON are emitted relative to docs/ so the static site can
# serve them directly.
def docs_url(p: Path) -> str:
    """Return a path relative to docs/ as a URL (no symlink resolution)."""
    return p.relative_to(DOCS).as_posix()


def example_to_url(example_path: Path) -> Path:
    """Map a real examples/ path under the docs/ symlinked tree."""
    rel = example_path.relative_to(EXAMPLES_REAL)
    return DOCS / "metal_plates_examples" / rel


IMG_EXT = {".png", ".jpg", ".jpeg"}


def collect_part(part_dir: Path) -> dict | None:
    """Build a single part record. Returns None if nothing useful inside."""
    plastic_dir = part_dir / "1_original_plastic_images"
    raw_dir = part_dir / "0_raw_screenshots"
    renders_dir = part_dir / "5_models_and_renders"
    holes_meta = part_dir / "2_flattened_image" / "holes_from_stl.json"

    plastic_imgs: list[str] = []
    build_imgs: list[str] = []
    render_imgs: list[str] = []
    drawing_png: str | None = None
    drawing_data: dict | None = None

    if plastic_dir.is_dir():
        for f in sorted(plastic_dir.iterdir()):
            if f.suffix.lower() in IMG_EXT:
                plastic_imgs.append(docs_url(example_to_url(f)))
    if raw_dir.is_dir():
        for f in sorted(raw_dir.iterdir()):
            if f.suffix.lower() in IMG_EXT:
                build_imgs.append(docs_url(example_to_url(f)))
    # Many WIP folders just dump their raw screenshots at the top level
    # (before the numbered-stage layout is set up). Treat those as build
    # images too — they're equivalent to 0_raw_screenshots content.
    for f in sorted(part_dir.iterdir()):
        if f.is_file() and f.suffix.lower() in IMG_EXT:
            build_imgs.append(docs_url(example_to_url(f)))
    if renders_dir.is_dir():
        for f in sorted(renders_dir.iterdir()):
            if f.suffix.lower() == ".png":
                render_imgs.append(docs_url(example_to_url(f)))

    if holes_meta.is_file():
        try:
            meta = json.loads(holes_meta.read_text())
            src = Path(meta.get("source_stl", ""))
            if src.exists():
                # Find the corresponding drawing file under docs/stl_drawings/.
                rel = src.relative_to(REPO / "docs" / "stl_files")
                drawing = (DOCS / "stl_drawings" / rel.parent / f"{src.stem}_drawing.png")
                drawing_json = drawing.with_suffix(".json")
                if drawing.exists():
                    drawing_png = docs_url(drawing)
                if drawing_json.exists():
                    drawing_data = json.loads(drawing_json.read_text())
        except (ValueError, OSError, KeyError):
            pass

    if not (plastic_imgs or build_imgs or render_imgs or drawing_png):
        return None

    return {
        "id": part_dir.name,
        "group": part_dir.parent.name,
        "name": _pretty(part_dir.name),
        "plastic_images": plastic_imgs,
        "build_images": build_imgs,
        "metal_renders": render_imgs,
        "drawing": drawing_png,
        "drawing_data": drawing_data,
    }


def _pretty(name: str) -> str:
    return name.replace("_", " ").strip()


def _has_images(d: Path) -> bool:
    """True if d holds an image file directly or in any numbered subdir."""
    if not d.is_dir():
        return False
    for f in d.iterdir():
        if f.is_file() and f.suffix.lower() in IMG_EXT:
            return True
        if f.is_dir() and f.name in {
            "0_raw_screenshots",
            "1_original_plastic_images",
            "5_models_and_renders",
        }:
            for g in f.iterdir():
                if g.is_file() and g.suffix.lower() in IMG_EXT:
                    return True
    return False


def collect_parts() -> list[dict]:
    parts: list[dict] = []
    for entry in sorted(EXAMPLES_REAL.iterdir()):
        if not entry.is_dir():
            continue
        if _has_images(entry):
            # Ungrouped part directly under examples/ (cnc_clamp, all, etc.).
            rec = collect_part(entry)
            if rec is not None:
                rec["group"] = ""  # no group → suppressed in UI
                parts.append(rec)
            continue
        # Otherwise treat as a group: each subdir is a part.
        for part_dir in sorted(entry.iterdir()):
            if not part_dir.is_dir():
                continue
            rec = collect_part(part_dir)
            if rec is not None:
                parts.append(rec)
    return parts


def collect_plastic_library() -> list[dict]:
    """All 3D-printed part photos under docs/images/parts/3d-printed/.

    The user can pick from this list to attach a "studio" photo of a
    plastic component to any metal part on the website.
    """
    base = DOCS / "images" / "parts" / "3d-printed"
    if not base.is_dir():
        return []
    out: list[dict] = []
    for f in sorted(base.rglob("*")):
        if not f.is_file() or f.suffix.lower() not in IMG_EXT:
            continue
        rel = f.relative_to(base)
        category = rel.parts[0] if len(rel.parts) > 1 else "other"
        out.append({
            "id": f.stem,
            "category": category,
            "name": _pretty(f.stem),
            "image": docs_url(f),
        })
    return out


SIZE_PATTERN = re.compile(r"^(M\d+(?:\.\d+)?|[\d.]+-[\d.]+mm)(?:[_-](\d+(?:\.\d+)?)mm)?", re.I)


def parse_fastener_filename(stem: str) -> tuple[str, str | None]:
    """Extract (thread, length_mm_str) from a filename stem.
    Examples:
      M5_20mm        → ("M5", "20")
      M8_locknut     → ("M8", None)
      3-5mm_20mm     → ("3-5mm", "20")
    """
    m = SIZE_PATTERN.match(stem)
    if not m:
        return stem, None
    return m.group(1), m.group(2)


def collect_fasteners() -> list[dict]:
    base = DOCS / "images" / "parts" / "consumables"
    if not base.is_dir():
        return []
    out: list[dict] = []
    for kind in ("screws", "nuts", "washers"):
        kdir = base / kind
        if not kdir.is_dir():
            continue
        for entry in sorted(kdir.rglob("*.jpg")):
            stem = entry.stem
            thread, length = parse_fastener_filename(stem)
            if "locknut" in stem.lower():
                role = "locknut"
            else:
                role = kind[:-1] if kind.endswith("s") else kind
            label_parts = [thread]
            if length:
                label_parts.append(f"{length} mm")
            if role and role not in ("screw",):
                label_parts.append(role)
            out.append({
                "id": f"{kind}_{stem}",
                "kind": kind,
                "role": role,
                "thread": thread,
                "length_mm": float(length) if length else None,
                "label": " · ".join(label_parts),
                "image": docs_url(entry),
            })
    return out


def main() -> None:
    parts = collect_parts()
    fasteners = collect_fasteners()
    plastic_library = collect_plastic_library()
    out = {
        "generated_from": "tools/build_mod_construction_data.py",
        "parts": parts,
        "fasteners": fasteners,
        "plastic_library": plastic_library,
    }
    out_path = DOCS / "data" / "mod_construction_parts.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2))
    print(
        f"wrote {out_path}  ({len(parts)} part(s), "
        f"{len(fasteners)} fastener(s), "
        f"{len(plastic_library)} plastic library photo(s))"
    )


if __name__ == "__main__":
    main()
