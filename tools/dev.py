#!/usr/bin/env python3
"""Run the shopping site locally as ONE command (SL-10.V).

Starts `mkdocs serve` and `tools/refresh_server.py` together, prefixes both
processes' logs, prints the URL, and tears both down cleanly on Ctrl-C or
when either subprocess exits.

Why: running mkdocs serve without the helper silently loses write-through —
the page falls back to localStorage and every edit lives only in the user's
browser until they remember to Export + merge. Bundling them removes the
"oops, forgot the helper" failure mode.

Usage:

    python3 tools/dev.py [--mkdocs-port 8000] [--helper-port 8765]

No third-party deps; stdlib only.
"""
from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _resolve_mkdocs_cmd() -> list[str]:
    """Find a working `mkdocs` invocation regardless of how the user installed it."""
    exe = shutil.which("mkdocs")
    if exe:
        return [exe]
    # Common conda location used on this machine — try it before falling back.
    conda_mkdocs = Path.home() / ".conda" / "bin" / "mkdocs"
    if conda_mkdocs.exists():
        return [str(conda_mkdocs)]
    # Final fallback: `python -m mkdocs`. Works if mkdocs is importable but the
    # script wrapper isn't on PATH.
    return [sys.executable, "-m", "mkdocs"]


def _pump(stream, prefix: str) -> None:
    """Forward a subprocess's lines to our stdout with a prefix."""
    try:
        for raw in iter(stream.readline, ""):
            if not raw:
                break
            sys.stdout.write(f"{prefix} {raw}")
            sys.stdout.flush()
    except Exception:
        pass


def _spawn(name: str, cmd: list[str], env: dict) -> subprocess.Popen:
    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        start_new_session=True,  # so Ctrl-C in our terminal doesn't double-signal them
    )
    threading.Thread(target=_pump, args=(proc.stdout, f"[{name}]"), daemon=True).start()
    return proc


def _terminate(name: str, proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    try:
        # Send SIGTERM to the whole process group; mkdocs spawns a livereload
        # child that doesn't always die when its parent gets a plain SIGTERM.
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=4)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--mkdocs-port", default="8000", help="port for mkdocs serve (default 8000)")
    p.add_argument("--helper-port", default="8765", help="port for refresh_server.py (default 8765)")
    args = p.parse_args(argv)

    env = os.environ.copy()
    env.setdefault("NO_MKDOCS_2_WARNING", "1")

    mkdocs_cmd = _resolve_mkdocs_cmd() + ["serve", "-a", f"127.0.0.1:{args.mkdocs_port}"]
    helper_cmd = [sys.executable, str(ROOT / "tools" / "refresh_server.py"), "--port", args.helper_port]

    print(f"dev: starting helper  {' '.join(helper_cmd)}", flush=True)
    helper = _spawn("helper", helper_cmd, env)
    # Tiny stagger so the helper's startup line lands above mkdocs's banner.
    time.sleep(0.4)
    print(f"dev: starting mkdocs  {' '.join(mkdocs_cmd)}", flush=True)
    mkdocs = _spawn("mkdocs", mkdocs_cmd, env)

    procs = [("helper", helper), ("mkdocs", mkdocs)]
    print(
        f"\ndev: shopping → http://127.0.0.1:{args.mkdocs_port}/DIY-3-axis-CNC-machine/shopping/\n"
        f"dev: helper   → http://127.0.0.1:{args.helper_port}/api/health  (write-through enabled)\n"
        f"dev: Ctrl-C to stop both.\n",
        flush=True,
    )

    def shutdown(_signum=None, _frame=None) -> None:
        print("\ndev: shutting down…", flush=True)
        for name, proc in procs:
            _terminate(name, proc)

    signal.signal(signal.SIGINT, lambda *_: shutdown())
    signal.signal(signal.SIGTERM, lambda *_: shutdown())

    # Block until either subprocess exits, then tear the other one down.
    try:
        while all(proc.poll() is None for _, proc in procs):
            time.sleep(0.3)
    finally:
        first_dead = next(((n, p) for n, p in procs if p.poll() is not None), None)
        if first_dead:
            name, proc = first_dead
            print(f"dev: {name} exited (status {proc.returncode}); stopping the other.", flush=True)
        shutdown()

    # Drain remaining log lines before returning.
    time.sleep(0.2)
    return max((proc.returncode or 0) for _, proc in procs)


if __name__ == "__main__":
    sys.exit(main())
