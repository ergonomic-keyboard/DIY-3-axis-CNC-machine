#!/usr/bin/env python3
"""Local helper for the shopping page's manual refresh buttons (SL-9.d).

Run alongside `mkdocs serve --dev-addr 127.0.0.1:8012`:

    python3 tools/refresh_server.py

Endpoints
---------
GET /api/health
    200 JSON describing the helper and its bots:
        {
          "status": "ok",
          "version": 1,
          "bots": [
            { "id": "tinytronics-bot", "shop": "tinytronics",
              "cooldown_s": 60, "last_run_at": "2026-06-25T19:30:00Z" | null,
              "item_count": 5 },
            ...
          ]
        }

POST /api/refresh?bot=<shop>-bot[&item=<code>]
    200 JSON: { "appended": int, "skipped": int, "failed": int,
                "details": [ { "item_code", "status", "reason", "observation"? }, ... ] }
    400 if bot is unknown / item is not configured for that shop.
    429 with Retry-After: <seconds> if the bot is in cooldown.

CORS
----
Allows http://127.0.0.1:8012 and http://localhost:8012 (the page served by
`mkdocs serve --dev-addr 127.0.0.1:8012`). Pre-flight OPTIONS handled.

Stdlib only — no third-party deps. The price-fetching logic lives in
`tools/refresh_prices.py` and is imported here; this module just adds the
HTTP shell and per-bot cooldown.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

# Path massage so `python3 tools/refresh_server.py` works without an installed package.
import pathlib as _pl
sys.path.insert(0, str(_pl.Path(__file__).resolve().parent.parent))

from tools import refresh_prices  # noqa: E402
from tools import merge_user_data  # noqa: E402

DEFAULT_PORT = 8765
ALLOWED_ORIGINS = (
    "http://127.0.0.1:8012", "http://localhost:8012",
    "http://127.0.0.1:8000", "http://localhost:8000",  # mkdocs serve default
)

# Per-shop cooldown in seconds. tinytronics is the only small shop we hit hard,
# so it gets a longer cooldown to stay polite.
COOLDOWN_S: dict[str, int] = {
    "tinytronics": 60,
}
DEFAULT_COOLDOWN_S = 30

BOT_SUFFIX = "-bot"

# Serializes concurrent /api/save-manual writes so two near-simultaneous edits
# on the page don't fight over docs/data/ writes.
SAVE_MANUAL_LOCK = threading.Lock()


def _is_loopback_origin(origin: str) -> bool:
    """Allow any localhost mkdocs serve port without enumerating them.
    The helper is bound to 127.0.0.1 so the threat model is local-only."""
    if not origin:
        return False
    return (
        origin.startswith("http://127.0.0.1:")
        or origin.startswith("http://localhost:")
    )


def shop_from_bot_id(bot_id: str) -> str | None:
    """tinytronics-bot → tinytronics. Returns None on malformed input."""
    if not bot_id.endswith(BOT_SUFFIX):
        return None
    return bot_id[: -len(BOT_SUFFIX)] or None


def cooldown_for_shop(shop: str) -> int:
    return COOLDOWN_S.get(shop, DEFAULT_COOLDOWN_S)


class CooldownTracker:
    """In-memory per-bot cooldown. Resets when the helper restarts; that's fine
    because the cooldown is a politeness measure, not a security mechanism."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last: dict[str, float] = {}  # bot_id → monotonic ts of last run

    def can_run(self, bot_id: str, cooldown_s: int) -> tuple[bool, int]:
        """Returns (can_run, retry_after_seconds)."""
        with self._lock:
            last = self._last.get(bot_id)
            if last is None:
                return True, 0
            remaining = cooldown_s - (time.monotonic() - last)
            if remaining <= 0:
                return True, 0
            return False, max(1, int(remaining) + 1)

    def mark_run(self, bot_id: str) -> None:
        with self._lock:
            self._last[bot_id] = time.monotonic()


COOLDOWN = CooldownTracker()


def list_bots(prices: dict[str, Any]) -> list[dict[str, Any]]:
    """Derive the bot list from prices.json entries: one bot per refreshable shop."""
    by_shop: dict[str, dict[str, Any]] = {}
    for entry in prices.get("entries", []):
        shop = entry.get("shop")
        if not shop or shop in refresh_prices.SKIP_SHOPS:
            continue
        bucket = by_shop.setdefault(shop, {"items": [], "last_run_at": None})
        bucket["items"].append(entry.get("item_code"))
        # last_run_at = newest non-manual observation timestamp.
        for obs in entry.get("observations", []) or []:
            tech = obs.get("technique")
            if tech and tech != "manual":
                ts = obs.get("ts")
                if ts and (bucket["last_run_at"] is None or ts > bucket["last_run_at"]):
                    bucket["last_run_at"] = ts

    bots = []
    for shop, info in sorted(by_shop.items()):
        bots.append({
            "id": shop + BOT_SUFFIX,
            "shop": shop,
            "cooldown_s": cooldown_for_shop(shop),
            "last_run_at": info["last_run_at"],
            "item_count": len(info["items"]),
        })
    return bots


def run_refresh(bot_id: str, *, item_code: str | None) -> dict[str, Any]:
    """Refresh either every entry for a shop, or a single (item, shop) entry."""
    shop = shop_from_bot_id(bot_id)
    if shop is None:
        return {"error": "bad_bot_id", "detail": f"bot id {bot_id!r} must end with {BOT_SUFFIX!r}"}
    if shop in refresh_prices.SKIP_SHOPS:
        return {"error": "skip_shop", "detail": f"{shop} is not auto-fetchable"}

    prices = refresh_prices.load_prices()
    candidates = [
        e for e in prices.get("entries", [])
        if e.get("shop") == shop and (item_code is None or e.get("item_code") == item_code)
    ]
    if not candidates:
        return {
            "error": "no_entries",
            "detail": f"no entries for shop={shop}" + (f" item={item_code}" if item_code else ""),
        }

    today = refresh_prices.now_iso_utc()
    appended = skipped = failed = 0
    details: list[dict[str, Any]] = []
    for i, entry in enumerate(candidates):
        result = refresh_prices.refresh_entry(entry, today=today)
        details.append({
            "item_code": entry.get("item_code"),
            "status": result["status"],
            "reason": result["reason"],
            "observation": result.get("observation"),
        })
        if result["status"] == "appended":
            appended += 1
        elif result["status"] == "skipped":
            skipped += 1
        else:
            failed += 1
        # Same inter-request politeness sleep as the CLI, except after the last one.
        if i < len(candidates) - 1:
            time.sleep(refresh_prices.INTER_REQUEST_SLEEP_S)

    if appended > 0:
        prices["last_updated_at"] = today
        refresh_prices.save_prices(prices)

    return {
        "appended": appended,
        "skipped": skipped,
        "failed": failed,
        "details": details,
    }


class RefreshHandler(BaseHTTPRequestHandler):
    server_version = "RefreshServer/1.0"

    # Silence the default access log; we'll print our own one-liner per request.
    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
        sys.stderr.write("[%s] %s - %s\n" % (
            self.log_date_time_string(), self.address_string(), fmt % args))

    def _cors_headers(self) -> None:
        origin = self.headers.get("Origin", "")
        if origin in ALLOWED_ORIGINS or _is_loopback_origin(origin):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "600")

    def _send_json(self, status: int, payload: dict[str, Any], extra_headers: dict[str, str] | None = None) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    # SL-10.U: POST /api/save-manual — write the user's manual edits straight
    # into docs/data/*.json via merge_user_data.merge_state. Body is the same
    # shape as the page's "Export data" download: {"state": {...}}.
    def _handle_save_manual(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            self._send_json(400, {"error": "missing_body"})
            return
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            self._send_json(400, {"error": "bad_json", "detail": str(e)})
            return
        state = body.get("state") if isinstance(body, dict) else None
        if not isinstance(state, dict):
            self._send_json(400, {"error": "missing_state"})
            return
        try:
            with SAVE_MANUAL_LOCK:
                result = merge_user_data.merge_state(state, dry_run=False)
        except Exception as e:  # noqa: BLE001
            self._send_json(500, {"error": "merge_failed", "detail": str(e)})
            return
        self._send_json(200, {
            "ok": True,
            "summary": result["summary"],
            "consumed": result["consumed"],
            "id_translations": result["id_translations"],
        })

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/health":
            try:
                prices = refresh_prices.load_prices()
            except Exception as e:  # noqa: BLE001
                self._send_json(500, {"status": "error", "detail": str(e)})
                return
            self._send_json(200, {
                "status": "ok",
                "version": 1,
                "bots": list_bots(prices),
                # SL-10.U: signals the page that POST /api/save-manual exists
                # so it can write manual edits straight to docs/data/*.json.
                "write_through": True,
            })
            return
        self._send_json(404, {"error": "not_found", "path": parsed.path})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/save-manual":
            self._handle_save_manual()
            return
        if parsed.path != "/api/refresh":
            self._send_json(404, {"error": "not_found", "path": parsed.path})
            return
        qs = urllib.parse.parse_qs(parsed.query)
        bot_id = (qs.get("bot") or [""])[0].strip()
        item_code = (qs.get("item") or [""])[0].strip() or None

        if not bot_id:
            self._send_json(400, {"error": "missing_bot", "detail": "?bot=<shop>-bot required"})
            return

        shop = shop_from_bot_id(bot_id)
        if shop is None:
            self._send_json(400, {"error": "bad_bot_id", "detail": f"bot id {bot_id!r} must end with {BOT_SUFFIX!r}"})
            return

        cooldown_s = cooldown_for_shop(shop)
        ok, retry_after = COOLDOWN.can_run(bot_id, cooldown_s)
        if not ok:
            self._send_json(429,
                {"error": "cooldown", "retry_after_s": retry_after, "cooldown_s": cooldown_s},
                extra_headers={"Retry-After": str(retry_after)})
            return

        # Mark first so concurrent calls are rejected even if the fetch is slow.
        COOLDOWN.mark_run(bot_id)
        try:
            result = run_refresh(bot_id, item_code=item_code)
        except Exception as e:  # noqa: BLE001
            self._send_json(500, {"error": "refresh_failed", "detail": str(e)})
            return

        if "error" in result:
            self._send_json(400, result)
            return
        self._send_json(200, result)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local helper for the shopping page's manual refresh buttons (SL-9.d).")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"port to listen on (default {DEFAULT_PORT})")
    parser.add_argument("--host", default="127.0.0.1", help="host to bind (default 127.0.0.1)")
    args = parser.parse_args(argv)

    server = ThreadingHTTPServer((args.host, args.port), RefreshHandler)
    print(f"refresh_server: listening on http://{args.host}:{args.port}", flush=True)
    print(f"refresh_server: CORS origins = {', '.join(ALLOWED_ORIGINS)}", flush=True)
    print("refresh_server: GET /api/health   POST /api/refresh?bot=<shop>-bot[&item=<code>]   POST /api/save-manual", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nrefresh_server: shutting down", flush=True)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
