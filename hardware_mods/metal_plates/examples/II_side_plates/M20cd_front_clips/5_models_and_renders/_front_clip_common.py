"""Shared geometry helpers for the front clips (upper + lower).

Both front clips share the same cross-section: a 23 x 20 mm block (X, Y)
with an "I-shape" along the Z axis — two end ears at full thickness with
a narrower neck in between. The neck wraps around the steel bar that
sticks out from the plate; the ears sit flat on the plate and are bolted
through a single central M5/M6 hole on each ear ... actually a single
central bolt on the body (see slice X=178.5: one bolt at the Z midpoint).

Coordinates match the plastic STL: bar protrudes from the plate in the -X
direction, clip wraps around it on the +X side. Z is the bar axis.

Parameters that differ between upper and lower are passed in.
"""
from __future__ import annotations

# ── cross-env bootstrap: make the build123d toolchain importable on Nix or Ubuntu ─
# Walks up to hardware_mods/metal_plates/env_bootstrap.py, then re-execs this script
# into a set-up env (.venv on Ubuntu / nix-shell on NixOS) when build123d is not
# already importable. No-op when already inside the right environment.
import os as _os, sys as _sys  # noqa: E402
_d = _os.path.dirname(_os.path.abspath(__file__))
while _d != _os.path.dirname(_d) and not _os.path.exists(_os.path.join(_d, "env_bootstrap.py")):
    _d = _os.path.dirname(_d)
if _d not in _sys.path:
    _sys.path.insert(0, _d)
import env_bootstrap as _env  # noqa: E402
_env.ensure_build123d(__file__)

from build123d import (
    Box,
    Cylinder,
    Location,
    Part,
)


def build_front_clip(
    *,
    x_min: float, x_max: float,
    y_min: float, y_max: float,
    z_min: float, z_max: float,
    neck_z_min: float, neck_z_max: float,
    neck_x_start: float,
    bolt_diam: float,
    bolt_cz: float,
) -> Part:
    """Build a front-clip part.

    Outer envelope x_min..x_max, y_min..y_max, z_min..z_max.
    Neck (the narrower middle section that wraps the bar) spans
    neck_z_min..neck_z_max along Z; in X it sits from neck_x_start..x_max
    (everything from x_min..neck_x_start is hollow in the neck region).
    Single bolt clearance hole through the body along +X at z = bolt_cz.
    """
    cx = (x_min + x_max) / 2
    cy = (y_min + y_max) / 2
    cz = (z_min + z_max) / 2

    body = Box(x_max - x_min, y_max - y_min, z_max - z_min).locate(
        Location((cx, cy, cz)))

    # Remove the neck pocket on the -X side
    neck_cx = (x_min + neck_x_start) / 2
    neck_cz = (neck_z_min + neck_z_max) / 2
    neck_cut = Box(
        neck_x_start - x_min,
        y_max - y_min,
        neck_z_max - neck_z_min,
    ).locate(Location((neck_cx, cy, neck_cz)))

    # Bolt clearance — axis along +X, fully through the body.
    bolt = Cylinder(
        radius=bolt_diam / 2,
        height=(x_max - x_min) * 1.5,
        rotation=(0, 90, 0),
    ).locate(Location((cx, cy, bolt_cz)))

    return body - neck_cut - bolt
