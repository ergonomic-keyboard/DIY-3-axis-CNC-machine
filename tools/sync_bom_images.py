#!/usr/bin/env python3
"""Populate `image` field on each item in docs/data/items.json from the BOM.

Run from repo root:

    python3 tools/sync_bom_images.py

Re-run any time docs/BILLOFMATERIAL.md changes. Items with no image in the
BOM are left without an `image` key — the Shopping UI falls back to a
placeholder for those.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BOM = ROOT / "docs" / "BILLOFMATERIAL.md"
ITEMS = ROOT / "docs" / "data" / "items.json"

# Match a markdown table row whose first cell looks like an item code (P01, E09, …).
ROW_RE = re.compile(r"^\s*\|\s*([A-Z]\d{2})\s*\|")
# Match the first ![](./images/...) image in a row.
IMG_RE = re.compile(r"!\[[^\]]*\]\((?:\./)?(images/[^\s)]+)\)")


def parse_bom() -> dict[str, str]:
    images: dict[str, str] = {}
    for line in BOM.read_text(encoding="utf-8").splitlines():
        m = ROW_RE.match(line)
        if not m:
            continue
        code = m.group(1)
        img = IMG_RE.search(line)
        if img:
            images[code] = img.group(1)
    return images


def main() -> None:
    images = parse_bom()
    data = json.loads(ITEMS.read_text(encoding="utf-8"))
    updated = 0
    for item in data["items"]:
        code = item["code"]
        if code in images:
            if item.get("image") != images[code]:
                item["image"] = images[code]
                updated += 1
        else:
            item.pop("image", None)
    ITEMS.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Synced {updated} image path(s) for {len(images)} BOM items with images.")


if __name__ == "__main__":
    main()
