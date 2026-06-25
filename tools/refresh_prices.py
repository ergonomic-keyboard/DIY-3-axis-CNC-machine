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
import urllib.parse
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
    "conrad_nl",   # bot wall; product pages 403 with anything that looks like a script
    "3dhubs_print_service",  # quote-only, no fixed price
}


# URLs that are clearly listing/search/category pages get skipped without
# even fetching — they never expose a single product offer.
LISTING_HINTS = (
    "/zoeken", "/zoek?",
    "/search?", "/search/",
    "/s?", "/c/", "/categorie",
    "search=", "searchtext=", "search_text=",
    "/wholesale",
)


def looks_like_listing_url(url: str | None) -> bool:
    if not url:
        return True
    parsed = urllib.parse.urlparse(url)
    path = parsed.path or "/"
    if path in ("", "/"):
        return True
    if path.endswith("/"):  # category / directory pages on most CMSes
        return True
    low = url.lower()
    return any(h in low for h in LISTING_HINTS)


class MetaTagCollector(HTMLParser):
    """Collects every <meta> tag's attribute bag so we can look up OG / itemprop."""

    def __init__(self) -> None:
        super().__init__()
        self.metas: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "meta":
            return
        self.metas.append({k.lower(): (v or "") for k, v in attrs})


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
    """Return a Product offer from JSON-LD.

    Three outcomes (per SL-8.h):
        - No Product node at all → returns None (caller marks as failed).
        - Product node found with a price → returns full offer dict, technique='jsonld'.
        - Product node found but no usable price → returns a partial dict with
          price=None and partial=True so the caller writes a "found, no price"
          observation that the UI surfaces as a "complete this" prompt.
    """
    saw_product = False
    for node in iter_jsonld_objects(html):
        types = node.get("@type")
        if isinstance(types, list):
            type_set = {str(t).lower() for t in types}
        else:
            type_set = {str(types).lower()} if types else set()
        if "product" not in type_set:
            continue
        saw_product = True
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
                "technique": "jsonld",
            }
    if saw_product:
        return {
            "price": None,
            "currency": "EUR",
            "in_stock": None,
            "technique": "jsonld",
            "partial": True,
        }
    return None


def extract_meta_offer(html: str) -> dict[str, Any] | None:
    """Fallback: look for OpenGraph `og:price:*` or microdata `itemprop=price` meta tags. technique='opengraph'."""
    parser = MetaTagCollector()
    try:
        parser.feed(html)
    except Exception:  # noqa: BLE001
        return None

    price_raw: str | None = None
    currency_raw: str | None = None
    availability_raw: str = ""

    for meta in parser.metas:
        key = meta.get("property", "") or meta.get("name", "") or meta.get("itemprop", "")
        key = key.lower()
        value = meta.get("content", "")
        if not value:
            continue
        if key in ("og:price:amount", "product:price:amount", "price"):
            price_raw = price_raw or value
        elif key in ("og:price:currency", "product:price:currency", "pricecurrency"):
            currency_raw = currency_raw or value
        elif key in ("og:availability", "product:availability", "availability"):
            availability_raw = availability_raw or value

    if price_raw is None:
        return None
    try:
        price_f = float(price_raw.replace(",", "."))
    except ValueError:
        return None
    in_stock = (
        "instock" in availability_raw.lower()
        or availability_raw.lower() in ("", "in stock", "available")
    )
    return {
        "price": round(price_f, 2),
        "currency": (currency_raw or "EUR").upper(),
        "in_stock": bool(in_stock),
        "technique": "opengraph",
    }


def extract_offer(html: str) -> dict[str, Any] | None:
    """JSON-LD first (most reliable), Open Graph / microdata as fallback."""
    return extract_product_offer(html) or extract_meta_offer(html)


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


def now_iso_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_prices() -> dict[str, Any]:
    return json.loads(PRICES_PATH.read_text(encoding="utf-8"))


def save_prices(prices: dict[str, Any]) -> None:
    PRICES_PATH.write_text(json.dumps(prices, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def refresh_entry(entry: dict[str, Any], *, today: str | None = None) -> dict[str, Any]:
    """Refresh a single (item_code, shop) entry in-place.

    Mutates `entry` only when status == 'appended'. Returns:
        {"status": "appended"|"skipped"|"failed", "reason": str, "observation": dict|None}

    Used both by `refresh()` (CLI loop) and by `tools/refresh_server.py` (SL-9.d
    local helper). The caller is responsible for `time.sleep` between calls
    when iterating, and for writing prices.json back to disk.
    """
    if today is None:
        today = now_iso_utc()

    shop = entry.get("shop", "?")
    url = entry.get("url")

    if shop in SKIP_SHOPS:
        return {"status": "skipped", "reason": "not auto-fetchable", "observation": None}
    if looks_like_listing_url(url):
        return {"status": "skipped", "reason": "listing/search/category URL, not a product page", "observation": None}

    html = fetch_html(url)
    if html is None:
        return {"status": "failed", "reason": "fetch failed", "observation": None}

    product = extract_offer(html)
    if product is None:
        return {"status": "failed", "reason": "no Product JSON-LD / Open Graph price found", "observation": None}

    new_obs = {
        "ts": today,
        "price": product["price"],
        "currency": product["currency"],
        "in_stock": product["in_stock"],
        "eta_days": (latest_observation(entry) or {}).get("eta_days"),
        "technique": product.get("technique", "jsonld"),
    }
    if product.get("partial"):
        # SL-8.h: product page existed but no price could be parsed. Persist a
        # partial observation so the UI can prompt the user to complete it.
        new_obs["partial"] = True
        entry.setdefault("observations", []).insert(0, new_obs)
        return {"status": "appended", "reason": "partial (product found, no price)", "observation": new_obs}

    if not observation_changed(latest_observation(entry), new_obs):
        return {"status": "skipped", "reason": "unchanged", "observation": new_obs}

    entry.setdefault("observations", []).insert(0, new_obs)
    return {"status": "appended", "reason": "new observation", "observation": new_obs}


def refresh(prices: dict[str, Any], *, dry_run: bool) -> tuple[int, int, int]:
    appended = skipped = failed = 0
    today = now_iso_utc()

    for entry in prices.get("entries", []):
        item = entry.get("item_code", "?")
        shop = entry.get("shop", "?")
        label = f"{item} @ {shop}"

        # Pre-fetch skips get their own log line so the user sees why nothing happened.
        if shop in SKIP_SHOPS:
            skipped += 1
            print(f"[skip ] {label}: not auto-fetchable")
            continue
        if looks_like_listing_url(entry.get("url")):
            skipped += 1
            print(f"[skip ] {label}: listing/search/category URL, not a product page")
            continue

        print(f"[fetch] {label}: {entry.get('url')}")
        result = refresh_entry(entry, today=today)
        status = result["status"]
        obs = result.get("observation") or {}

        if status == "failed":
            failed += 1
            print(f"  {result['reason']}")
        elif status == "skipped":
            skipped += 1
            if obs.get("currency") and obs.get("price") is not None:
                print(f"  unchanged ({obs['currency']} {obs['price']})")
            else:
                print(f"  {result['reason']}")
        else:  # appended
            appended += 1
            if obs.get("partial"):
                print(f"  appended partial (product found, no price; technique={obs.get('technique')})")
            else:
                print(f"  appended {obs.get('currency')} {obs.get('price')} (in_stock={obs.get('in_stock')})")

        time.sleep(INTER_REQUEST_SLEEP_S)

    if appended > 0:
        prices["last_updated_at"] = today
    if not dry_run:
        save_prices(prices)
    return appended, skipped, failed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Print changes without writing prices.json")
    args = parser.parse_args(argv)

    prices = load_prices()
    appended, skipped, failed = refresh(prices, dry_run=args.dry_run)

    print()
    print(f"Summary: {appended} appended, {skipped} skipped, {failed} failed.")
    # Always exit 0 — a partial refresh is still a useful PR.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
