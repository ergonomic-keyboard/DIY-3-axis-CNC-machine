#!/usr/bin/env bash
# setup_env.sh — one-time Ubuntu (non-Nix) setup for the build123d part scripts.
#
# Creates a repo-root .venv and installs the build123d toolchain into it.
# After this, `python hardware_mods/metal_plates/build_model.py ...` just works:
# env_bootstrap.py detects the .venv and re-execs into it automatically.
#
# On NixOS you do NOT need this — use `nix-shell hardware_mods/metal_plates/shell.nix`,
# whose shellHook provisions the same .venv from requirements.txt.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(git -C "$HERE" rev-parse --show-toplevel 2>/dev/null || echo "$HERE/../..")"
VENV="$ROOT/.venv"
REQ="$HERE/requirements.txt"

PY="${PYTHON:-python3}"
echo "[setup] repo root : $ROOT"
echo "[setup] venv       : $VENV"
echo "[setup] python     : $("$PY" --version 2>&1)"

if [ ! -x "$VENV/bin/python" ]; then
  echo "[setup] creating venv ..."
  "$PY" -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/python" -m pip install -r "$REQ"

echo "[setup] done. build123d scripts will now auto-use $VENV"
