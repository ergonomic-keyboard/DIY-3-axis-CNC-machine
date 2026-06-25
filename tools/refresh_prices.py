#!/usr/bin/env python3
"""Refresh prices in docs/data/prices.json by parsing JSON-LD on each shop URL.

What this does:
    For each entry in prices.json, fetch the linked product page, look for a
    Schema.org `Product` block in JSON-LD, extract price / currency / stock,
    and append a new observation to the entry's history (never overwriting).

What this does NOT do:
    - Render JS (so any shop that prices via XHR after page load is invisible).
    - Bypass anti-bot (Cloudflare, captcha, Bol/Amazon bot filters will fail).
    - Magic the AliExpress per-seller variant pricing problem away.

Run locally:
    python3 tools/refresh_prices.py            # writes prices.json in place
    python3 tools/refresh_prices.py --dry-run  # prints what would change

The companion GitHub Action (`.github/workflows/refresh-prices.yml`) runs this
weekly and opens a PR so a human reviews the diff before publishing.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
PRICES_PATH = ROOT / "docs" / "data" / "prices.json"

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
ACCEPT_LANGUAGE = "nl-NL,nl;q=0.9,en;q=0.6"
REQUEST_TIMEOUT_S = 20
INTER_REQUEST_SLEEP_S = 1.5

# Shops where scraping a single URL is hopeless. We skip them quietly so the
# rest of the snapshot keeps refreshing.
SKIP_SHOPS = {
    "aliexpress",  # URLs are search queries, per-seller variant pricing
    "amazon_nl",   # bot wall; needs PA-API
    "bol_nl",      # bot wall; needs Plaza/affiliate API
    "3dhubs_print_service",  # quote-only, no fixed price
}


class JsonLdExtractor(HTMLParser):
    """Pulls every `<script type="application/ld+json">` body out of an HTML page."""

    def __init__(self) -> None:
        super().__init__()
        self._capture = False
        self._buf: list[str] = []
        self.blocks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "script":
            return
        attrs_d = {k.lower(): (v or "") for k, v in attrs}
        if attrs_d.get("type", "").lower() == "application/ld+json":
            self._capture = True
            self._buf = []

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self._capture:
            self.blocks.append("".join(self._buf))
            self._capture = False
            self._buf = []

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._buf.append(data)


def fetch_html(url: str) -> str | None:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": ACCEPT_LANGUAGE,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.read().decode(charset, errors="replace")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ConnectionError) as e:
        print(f"  fetch failed: {e}", file=sys.stderr)
        return None


def iter_jsonld_objects(html: str):
    """Yield every JSON object found in JSON-LD blocks (flattening @graph arrays)."""
    extractor = JsonLdExtractor()
    try:
        extractor.feed(html)
    except Exception:  # noqa: BLE001
        return
    for raw in extractor.blocks:
        # Some sites prefix HTML comments inside script tags; strip them.
        cleaned = re.sub(r"<!--.*?-->", "", raw, flags=re.DOTALL).strip()
        if not cleaned:
            continue
        try:
            obj = json.loads(cleaned)
        except json.JSONDecodeError:
            continue
        for node in _walk_jsonld(obj):
            yield node


def _walk_jsonld(node: Any):
    if isinstance(node, list):
        for item in node:
            yield from _walk_jsonld(item)
        return
    if isinstance(node, dict):
        yield node
        if "@graph" in node:
            yield from _walk_jsonld(node["@graph"])


def extract_product_offer(html: str) -> dict[str, Any] | None:
    """Return {price, currency, in_stock} from the first Product JSON-LD with an Offer."""
    for node in iter_jsonld_objects(html):
        types = node.get("@type")
        if isinstance(types, list):
            type_set = {str(t).lower() for t in types}
        else:
            type_set = {str(types).lower()} if types else set()
        if "product" not in type_set:
            continue
        offers = node.get("offers")
        if not offers:
            continue
        # offers can be an Offer, an AggregateOffer, or a list.
        for offer in _walk_jsonld(offers):
            price = offer.get("price") or offer.get("lowPrice")
            if price is None:
                continue
            try:
                price_f = float(str(price).replace(",", "."))
            except ValueError:
                continue
            currency = (
                offer.get("priceCurrency")
                or offer.get("priceCurrencyCode")
                or "EUR"
            )
            availability = str(offer.get("availability", "")).lower()
            in_stock = (
                "instock" in availability
                or "limitedavailability" in availability
                or availability == ""
            )
            return {
                "price": round(price_f, 2),
                "currency": str(currency).upper(),
                "in_stock": bool(in_stock),
            }
    return None


def latest_observation(entry: dict[str, Any]) -> dict[str, Any] | None:
    obs = entry.get("observations") or []
    if not obs:
        return None
    return max(obs, key=lambda o: o.get("ts", ""))


def observation_changed(old: dict[str, Any] | None, new: dict[str, Any]) -> bool:
    if old is None:
        return True
    keys = ("price", "currency", "in_stock")
    return any(old.get(k) != new.get(k) for k in keys)


def refresh(prices: dict[str, Any], *, dry_run: bool) -> tuple[int, int, int]:
    appended = skipped = failed = 0
    today = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    for entry in prices.get("entries", []):
        item = entry.get("item_code", "?")
        shop = entry.get("shop", "?")
        url = entry.get("url")
        label = f"{item} @ {shop}"

        if shop in SKIP_SHOPS:
            skipped += 1
            print(f"[skip ] {label}: not auto-fetchable")
            continue
        if not url or url.endswith("/"):
            skipped += 1
            print(f"[skip ] {label}: no product URL")
            continue

        print(f"[fetch] {label}: {url}")
        html = fetch_html(url)
        if html is None:
            failed += 1
            continue

        product = extract_product_offer(html)
        if product is None:
            failed += 1
            print(f"  no Product JSON-LD found")
            continue

        new_obs = {
            "ts": today,
            "price": product["price"],
            "currency": product["currency"],
            "in_stock": product["in_stock"],
            "eta_days": (latest_observation(entry) or {}).get("eta_days"),
        }
        if not observation_changed(latest_observation(entry), new_obs):
            skipped += 1
            print(f"  unchanged ({product['currency']} {product['price']})")
        else:
            entry.setdefault("observations", []).insert(0, new_obs)
            appended += 1
            print(f"  appended {product['currency']} {product['price']} (in_stock={product['in_stock']})")

        time.sleep(INTER_REQUEST_SLEEP_S)

    if appended > 0:
        prices["last_updated_at"] = today
    if not dry_run:
        PRICES_PATH.write_text(json.dumps(prices, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return appended, skipped, failed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Print changes without writing prices.json")
    args = parser.parse_args(argv)

    prices = json.loads(PRICES_PATH.read_text(encoding="utf-8"))
    appended, skipped, failed = refresh(prices, dry_run=args.dry_run)

    print()
    print(f"Summary: {appended} appended, {skipped} skipped, {failed} failed.")
    # Always exit 0 — a partial refresh is still a useful PR.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
