#!/usr/bin/env python3
"""Merge a `cnc-shopping-user-export-*.json` (downloaded from the shopping
page's "↓ Export data" button) into the repo's primary data files:

    docs/data/shops.json
    docs/data/items.json
    docs/data/prices.json

The shopping page stores everything the user types — prices, EANs, added
shops, added alternatives — in their browser's localStorage. For data to
persist across machines / browsers / cache wipes it must land in the repo;
that's what this script does.

Workflow (per SL-10.T):

  1. On the shopping page, click "↓ Export data" and save the file.
  2. python3 tools/merge_user_data.py path/to/cnc-shopping-state-….json
  3. Review the diff (git diff docs/data/) and commit.

The script is idempotent: a price observation with the same (item, shop, ts)
is not appended twice, EAN updates are last-write-wins, and synthetic
"__addedshop_…" shop ids from the browser are translated to stable repo ids
once and recorded back into a sidecar manifest so subsequent runs match.

If --dry-run is passed, no files are written; the merge plan is printed.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "docs" / "data"
SHOPS_PATH = DATA_DIR / "shops.json"
ITEMS_PATH = DATA_DIR / "items.json"
PRICES_PATH = DATA_DIR / "prices.json"

ADDED_SHOP_PREFIX = "__addedshop_"
USER_ALT_PREFIX = "-user-"      # user alt codes look like "<parent>-user-<4hex>"
USER_SHOP_PREFIX = "__user_"    # the alt's synth shop id


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s or "shop"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _save_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _find_entry(prices: dict, item_code: str, shop_id: str) -> dict | None:
    for e in prices.get("entries", []):
        if e.get("item_code") == item_code and e.get("shop") == shop_id:
            return e
    return None


def _ensure_entry(prices: dict, item_code: str, shop_id: str, url: str | None) -> dict:
    e = _find_entry(prices, item_code, shop_id)
    if e is None:
        e = {
            "item_code": item_code,
            "shop": shop_id,
            "url": url,
            "ean": None,
            "observations": [],
        }
        prices["entries"].append(e)
    elif url and not e.get("url"):
        e["url"] = url
    return e


# ----------------------------------------------------------------------- shops

def _existing_shop_ids(shops: dict) -> set[str]:
    return {s.get("id") for s in shops.get("shops", [])}


def _stable_user_shop_id(existing_ids: set[str], shop_label: str, item_code: str) -> str:
    """Choose a stable, human-readable shop id for a browser-added shop.

    First tries `user-<slug>`. If that's taken by a different shop already,
    falls back to `user-<slug>-<item>`. If still taken (different label),
    appends a short hash of the label so the id is deterministic.
    """
    base = "user-" + _slugify(shop_label)
    if base not in existing_ids:
        return base
    cand = f"{base}-{_slugify(item_code)}"
    if cand not in existing_ids:
        return cand
    h = hashlib.sha1(shop_label.encode("utf-8")).hexdigest()[:6]
    return f"{base}-{h}"


def _add_or_merge_user_shop(
    shops: dict,
    existing_ids: set[str],
    label: str,
    url: str | None,
    currency: str,
    eta_days: int | None,
    shipping_cost: float | None,
    country: str,
    item_code_for_id: str,
) -> str:
    """Return the stable repo shop id for a browser-added user shop."""
    # Reuse an existing user-* shop with the same label/home_url first.
    for s in shops.get("shops", []):
        if s.get("id", "").startswith("user-") and s.get("name") == label:
            if not url or s.get("home_url") == url:
                return s["id"]
    new_id = _stable_user_shop_id(existing_ids, label, item_code_for_id)
    shops.setdefault("shops", []).append({
        "id": new_id,
        "name": label,
        "country": country,
        "currency": currency or "EUR",
        "home_url": url or "#",
        "shipping": {
            "standard_cost": float(shipping_cost) if shipping_cost is not None else 0.0,
            "default_eta_days": int(eta_days) if eta_days is not None else None,
        },
        "added_by_user": True,
    })
    existing_ids.add(new_id)
    return new_id


# -------------------------------------------------------------------- merging

def merge(export: dict, *, dry_run: bool) -> int:
    """CLI entry: validate the export envelope, call merge_state, print summary."""
    if export.get("$kind") != "cnc-shopping-user-export":
        print("error: input does not look like a cnc-shopping-user-export", file=sys.stderr)
        return 2
    result = merge_state(export.get("state") or {}, dry_run=dry_run)
    _print_summary(result["summary"], result["id_translations"])
    if dry_run:
        print("\n[dry-run] no files written.")
    else:
        print(f"\nWrote: {SHOPS_PATH}, {ITEMS_PATH}, {PRICES_PATH}")
        print("Next: git diff docs/data/ — review and commit if it looks right.")
        print(
            "Then clear your browser state for this site (DevTools → Application → "
            "Local Storage → cnc-shopping-state-v5) so future renders don't double "
            "up on top of what's now in the repo."
        )
    return 0


def merge_state(state: dict, *, data_dir: Path = DATA_DIR, dry_run: bool = False) -> dict:
    """Merge a state blob (the body of an export envelope) into the repo data.

    Returns a dict with keys:
      summary:          counts + lists of what landed
      id_translations:  {synthetic_shop_id: real_shop_id} for shopOverride rewrites
      consumed:         {bucket: [keys-or-codes...]} that the caller (e.g. the
                        shopping page) can clear from its localStorage so the
                        next render doesn't double-overlay on top of what's
                        now persisted in the repo.

    Pass `dry_run=True` to skip writing the JSON files.
    """
    shops_path = data_dir / "shops.json"
    items_path = data_dir / "items.json"
    prices_path = data_dir / "prices.json"
    shops = _load_json(shops_path)
    items = _load_json(items_path)
    prices = _load_json(prices_path)
    existing_ids = _existing_shop_ids(shops)
    country = state.get("country") or "NL"

    summary = {
        "shops_added": [],
        "alts_added": [],
        "observations_added": 0,
        "observations_skipped_duplicate": 0,
        "eans_set": 0,
    }
    id_translations: dict[str, str] = {}
    consumed = {
        "userPriceObservations": [],
        "userShops": [],
        "userAlternatives": [],
        "userEans": [],
    }

    # 1) Translate state.userShops → real shops + price entries.
    for item_code, lst in (state.get("userShops") or {}).items():
        if not lst:
            continue
        for us in lst:
            synth_id = us.get("id")
            label = us.get("shop_label") or "Custom shop"
            url = us.get("url")
            price = us.get("price")
            eta = us.get("eta_days")
            ship = us.get("shipping_cost")
            real_id = _add_or_merge_user_shop(
                shops, existing_ids, label, url,
                us.get("currency") or "EUR", eta, ship, country, item_code,
            )
            if synth_id and synth_id != real_id:
                id_translations[synth_id] = real_id
            summary["shops_added"].append({"item": item_code, "id": real_id, "label": label})

            entry = _ensure_entry(prices, item_code, real_id, url)
            ts = us.get("ts") or _now_iso()
            obs = {
                "ts": ts,
                "price": float(price) if isinstance(price, (int, float)) else None,
                "currency": us.get("currency") or "EUR",
                "in_stock": bool(us.get("in_stock", True)),
                "eta_days": int(eta) if isinstance(eta, (int, float)) else None,
                "technique": "manual",
            }
            if _append_obs_unique(entry, obs):
                summary["observations_added"] += 1
            else:
                summary["observations_skipped_duplicate"] += 1
        consumed["userShops"].append(item_code)

    # 2) state.userAlternatives → items.json alternatives + price entries.
    items_by_code = {i.get("code"): i for i in items.get("items", [])}
    for parent_code, lst in (state.get("userAlternatives") or {}).items():
        parent = items_by_code.get(parent_code)
        if not parent or not lst:
            if not parent:
                print(f"warn: parent {parent_code} not found in items.json — skipping alt", file=sys.stderr)
            continue
        parent.setdefault("alternatives", [])
        for ua in lst:
            alt_code = ua.get("code")
            if not alt_code:
                continue
            if not any(a.get("code") == alt_code for a in parent["alternatives"]):
                alt_entry = {"code": alt_code, "name": ua.get("name") or alt_code}
                if ua.get("ean"):
                    alt_entry["ean"] = ua["ean"]
                if ua.get("image"):
                    alt_entry["image"] = ua["image"]
                parent["alternatives"].append(alt_entry)
                summary["alts_added"].append(
                    {"parent": parent_code, "code": alt_code, "name": alt_entry["name"]}
                )

            shop_blob = ua.get("shop") or {}
            if shop_blob.get("shop_label"):
                shop_id = _add_or_merge_user_shop(
                    shops, existing_ids,
                    shop_blob.get("shop_label"),
                    shop_blob.get("url"),
                    shop_blob.get("currency") or "EUR",
                    shop_blob.get("eta_days"),
                    None,
                    country, alt_code,
                )
                synth_alt_shop_id = USER_SHOP_PREFIX + alt_code
                id_translations[synth_alt_shop_id] = shop_id
                entry = _ensure_entry(prices, alt_code, shop_id, shop_blob.get("url"))
                obs = {
                    "ts": _now_iso(),
                    "price": float(shop_blob["price"]) if isinstance(shop_blob.get("price"), (int, float)) else None,
                    "currency": shop_blob.get("currency") or "EUR",
                    "in_stock": True,
                    "eta_days": int(shop_blob["eta_days"]) if isinstance(shop_blob.get("eta_days"), (int, float)) else None,
                    "technique": "manual",
                }
                if _append_obs_unique(entry, obs):
                    summary["observations_added"] += 1
        consumed["userAlternatives"].append(parent_code)

    # 3) state.userPriceObservations → append manual observations.
    for key, ob in (state.get("userPriceObservations") or {}).items():
        if "::" not in key:
            continue
        item_code, shop_id = key.split("::", 1)
        shop_id = id_translations.get(shop_id, shop_id)
        if shop_id.startswith(ADDED_SHOP_PREFIX) or shop_id.startswith(USER_SHOP_PREFIX):
            print(f"warn: no real shop id for {shop_id}; skipping price for {item_code}", file=sys.stderr)
            continue
        entry = _ensure_entry(prices, item_code, shop_id, None)
        obs = {
            "ts": ob.get("ts") or _now_iso(),
            "price": float(ob["price"]) if isinstance(ob.get("price"), (int, float)) else None,
            "currency": ob.get("currency") or "EUR",
            "in_stock": bool(ob.get("in_stock", True)),
            "eta_days": int(ob["eta_days"]) if isinstance(ob.get("eta_days"), (int, float)) else None,
            "technique": "manual",
        }
        if _append_obs_unique(entry, obs):
            summary["observations_added"] += 1
        else:
            summary["observations_skipped_duplicate"] += 1
        consumed["userPriceObservations"].append(key)

    # 4) state.userEans → set entry.ean on matching entries (last write wins).
    for key, ean in (state.get("userEans") or {}).items():
        if "::" not in key or not ean:
            continue
        item_code, shop_id = key.split("::", 1)
        shop_id = id_translations.get(shop_id, shop_id)
        entry = _find_entry(prices, item_code, shop_id) or _ensure_entry(prices, item_code, shop_id, None)
        entry["ean"] = ean
        summary["eans_set"] += 1
        consumed["userEans"].append(key)

    prices["last_updated_at"] = _now_iso()

    if not dry_run:
        _save_json(shops_path, shops)
        _save_json(items_path, items)
        _save_json(prices_path, prices)

    return {"summary": summary, "id_translations": id_translations, "consumed": consumed}


def _append_obs_unique(entry: dict, obs: dict) -> bool:
    """Append obs unless an observation with the same ts already exists."""
    ts = obs.get("ts")
    if any(o.get("ts") == ts for o in entry.get("observations") or []):
        return False
    entry.setdefault("observations", []).append(obs)
    return True


def _print_summary(s: dict, id_translations: dict | None = None) -> None:
    print(f"Shops added:        {len(s['shops_added'])}")
    for x in s["shops_added"]:
        print(f"  - {x['id']:<28} ({x['label']}) for {x['item']}")
    print(f"Alternatives added: {len(s['alts_added'])}")
    for x in s["alts_added"]:
        print(f"  - {x['parent']} → {x['code']}: {x['name']}")
    print(f"Observations added: {s['observations_added']}")
    print(f"  duplicates skipped: {s['observations_skipped_duplicate']}")
    print(f"EANs set:           {s['eans_set']}")
    if id_translations:
        print(f"Shop-id rewrites:   {len(id_translations)}")
        for synth, real in id_translations.items():
            print(f"  {synth} → {real}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("export_path", type=Path, help="Path to the exported JSON.")
    p.add_argument("--dry-run", action="store_true", help="Don't write files; just print the plan.")
    args = p.parse_args()

    if not args.export_path.exists():
        print(f"error: {args.export_path} not found", file=sys.stderr)
        return 1
    export = json.loads(args.export_path.read_text(encoding="utf-8"))
    return merge(export, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
