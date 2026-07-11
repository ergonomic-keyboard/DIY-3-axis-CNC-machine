"""env_bootstrap.py — let the metal_plates tooling run on both NixOS and Ubuntu.

The tooling has two independent environment concerns:

  * **FreeCAD scripts** (``assembly/assemble_and_render.py``,
    ``assembly/export_manual_steps.py``) need the FreeCAD *compiled* libraries
    (``FreeCAD.so``) / the ``FreeCADCmd`` binary located, regardless of how
    FreeCAD was installed — a Nix store path, an extracted AppImage under
    ``~/.local/opt``, or something on ``PATH``.  This is resolved *in-process*
    by injecting the lib dir onto ``sys.path`` (see :func:`ensure_freecad`).

  * **build123d scripts** (``build_model.py`` and the per-part scripts) need the
    ``build123d`` *pip package* importable.  build123d is a normal Python
    package, so here "the environment" really means "which interpreter".  If it
    is not importable we **re-exec** into an already-set-up environment — a
    repo-root ``.venv`` on Ubuntu, or ``nix-shell shell.nix`` on NixOS — but we
    never install anything silently.  If nothing is set up we print the exact
    one-time setup command and exit (see :func:`ensure_build123d`).

Environment detection is automatic (:func:`detect_platform`); nothing here is
hard-coded to one machine.
"""
from __future__ import annotations

import glob
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

# Sentinel put in the environment before a re-exec so the child process does not
# loop forever if the environment it switched into *still* lacks build123d.
_REEXEC_SENTINEL = "_CNC_ENV_REEXEC"

# GTK/pixbuf/locale vars the VS Code snap leaks into its integrated terminal;
# they point GUI apps at /snap/code/... runtimes and break GL/pixbuf loading.
_SNAP_LEAK_VARS = (
    "GTK_PATH", "LOCPATH", "GDK_PIXBUF_MODULE_FILE", "GDK_PIXBUF_MODULEDIR",
    "GSETTINGS_SCHEMA_DIR", "GTK_IM_MODULE_FILE", "GIO_MODULE_DIR",
)


# ── platform / repo helpers ─────────────────────────────────────────────────
def detect_platform() -> str:
    """Return ``"nix"`` or ``"generic"`` (Ubuntu / macOS / other).

    We are inside/next to Nix when ``$IN_NIX_SHELL`` is set, ``nix-shell`` is on
    ``PATH``, or ``/nix/store`` exists.
    """
    if os.environ.get("IN_NIX_SHELL"):
        return "nix"
    if shutil.which("nix-shell"):
        return "nix"
    if os.path.isdir("/nix/store"):
        return "nix"
    return "generic"


def repo_root() -> Path:
    """Locate the git repo root (falls back to walking up for a ``.git`` dir)."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True,
        )
        return Path(out.stdout.strip())
    except Exception:
        d = Path(__file__).resolve()
        for parent in [d, *d.parents]:
            if (parent / ".git").exists():
                return parent
        return Path(__file__).resolve().parents[2]


def _metal_plates_dir() -> Path:
    return Path(__file__).resolve().parent


# ── FreeCAD discovery (in-process) ──────────────────────────────────────────
def find_freecad_lib() -> str | None:
    """Return the dir containing ``FreeCAD.so``/``FreeCAD.pyd``, or ``None``.

    Search order (works on any machine, no hard-coded store hash):
      1. ``$FREECAD_LIB``
      2. extracted AppImage under ``~/.local/opt/FreeCAD-*/usr/lib`` (Ubuntu)
      3. any ``/nix/store/*-freecad-*/lib`` (NixOS)
      4. derived from a ``freecad``/``FreeCADCmd`` binary on ``PATH``
    """
    cands: list[str] = []
    if os.environ.get("FREECAD_LIB"):
        cands.append(os.environ["FREECAD_LIB"])
    cands += sorted(glob.glob(os.path.expanduser("~/.local/opt/FreeCAD-*/usr/lib")),
                    reverse=True)
    cands += sorted(glob.glob("/nix/store/*-freecad-*/lib"), reverse=True)
    for exe in ("freecad", "FreeCAD", "FreeCADCmd", "freecadcmd"):
        p = shutil.which(exe)
        if not p:
            continue
        real = Path(p).resolve()
        # .../usr/bin/freecad -> .../usr/lib ; .../bin/FreeCAD -> .../lib
        for up in (real.parents[1] / "lib", real.parents[1] / "usr" / "lib"):
            cands.append(str(up))
    for c in cands:
        if os.path.exists(os.path.join(c, "FreeCAD.so")) or \
           os.path.exists(os.path.join(c, "FreeCAD.pyd")):
            return c
    return None


def find_freecadcmd() -> str:
    """Return a usable ``FreeCADCmd`` command (headless FreeCAD CLI)."""
    if os.environ.get("FREECADCMD"):
        return os.environ["FREECADCMD"]
    for exe in ("freecadcmd", "FreeCADCmd"):
        p = shutil.which(exe)
        if p:
            return p
    for pat in ("~/.local/opt/FreeCAD-*/usr/bin/freecadcmd",
                "~/.local/opt/FreeCAD-*/usr/bin/FreeCADCmd"):
        hits = sorted(glob.glob(os.path.expanduser(pat)), reverse=True)
        if hits:
            return hits[0]
    return "FreeCADCmd"  # last resort — assume it is on PATH


def find_ffmpeg() -> str:
    """Return an ffmpeg binary (imageio-ffmpeg's static build, or one on PATH)."""
    try:
        import imageio_ffmpeg  # type: ignore
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return shutil.which("ffmpeg") or "ffmpeg"


def setup_gui_env() -> None:
    """Force the xcb Qt backend and strip the VS Code snap env leak."""
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
    for var in _SNAP_LEAK_VARS:
        os.environ.pop(var, None)


def ensure_freecad(render_deps_dir: str | None = None) -> str:
    """Prepare the process to ``import FreeCAD`` on nix *or* Ubuntu.

    Locates the FreeCAD lib dir, puts it on ``sys.path`` and exports
    ``$FREECAD_LIB`` (so re-invoked render subprocesses inherit it), sets the Qt
    backend, and optionally adds a local ``.render_deps`` dir (pip-installed
    imageio-ffmpeg) to ``sys.path``.  Returns the resolved lib dir.
    """
    setup_gui_env()
    if render_deps_dir and os.path.isdir(render_deps_dir) and render_deps_dir not in sys.path:
        sys.path.insert(0, render_deps_dir)
    lib = find_freecad_lib()
    if lib is None:
        raise RuntimeError(
            "Could not locate FreeCAD. Install one of:\n"
            "  * Ubuntu: extract the FreeCAD AppImage to "
            "~/.local/opt/FreeCAD-<ver>/ (see memory freecad-launch-setup)\n"
            "  * NixOS:  add `freecad` to your shell/environment\n"
            "or set $FREECAD_LIB to the dir containing FreeCAD.so."
        )
    os.environ["FREECAD_LIB"] = lib
    if lib not in sys.path:
        sys.path.insert(0, lib)
    return lib


# ── build123d discovery (via re-exec) ───────────────────────────────────────
def _importable(mod: str) -> bool:
    import importlib.util
    return importlib.util.find_spec(mod) is not None


def _reexec(cmd_argv: list[str]) -> "None":
    """Replace the current process, marking the child so it will not loop."""
    env = dict(os.environ, **{_REEXEC_SENTINEL: "1"})
    sys.stderr.write(f"[env] switching environment: {' '.join(cmd_argv)}\n")
    sys.stderr.flush()
    os.execvpe(cmd_argv[0], cmd_argv, env)


def _fail_missing_build123d(plat: str, root: Path, shellnix: Path) -> "None":
    req = root / "hardware_mods/metal_plates/requirements.txt"
    setup = root / "hardware_mods/metal_plates/setup_env.sh"
    lines = [
        "",
        "[env] build123d is not importable and no set-up environment was found.",
        f"[env] detected platform: {plat}",
        "[env] Set it up once, then re-run this command:",
        "",
    ]
    if plat == "nix":
        lines += [
            f"    nix-shell {shellnix} --run \\",
            "      'python -m venv .venv && "
            f".venv/bin/pip install -r {req}'",
            "",
            "  then run the script through the shell, e.g.:",
            f"    nix-shell {shellnix} --run 'python <this-script> <args>'",
        ]
    else:
        lines += [
            f"    bash {setup}                 # convenience wrapper, or manually:",
            "    python3 -m venv .venv",
            f"    .venv/bin/pip install -r {req}",
        ]
    lines += [""]
    sys.stderr.write("\n".join(lines))
    sys.stderr.flush()
    sys.exit(1)


def ensure_build123d(script_path: str, argv: list[str] | None = None) -> None:
    """Guarantee ``import build123d`` will work, or re-exec / exit trying.

    Called at the very top of every build123d script.  If build123d is already
    importable (we are already inside the right env) it returns immediately.
    Otherwise it re-execs the same script+args into an already-provisioned env:
    a repo ``.venv`` on Ubuntu, or ``nix-shell shell.nix`` on NixOS.  It never
    installs anything; if nothing is set up it prints the setup command and
    exits(1).
    """
    if _importable("build123d"):
        return
    if os.environ.get(_REEXEC_SENTINEL):
        # We already re-exec'd once and build123d is *still* missing — the target
        # env is incomplete.  Don't loop; tell the user how to fix it.
        _fail_missing_build123d(detect_platform(), repo_root(),
                                _metal_plates_dir() / "shell.nix")

    argv = list(argv if argv is not None else sys.argv[1:])
    script_path = os.path.abspath(script_path)
    plat = detect_platform()
    root = repo_root()
    shellnix = _metal_plates_dir() / "shell.nix"
    venv_py = root / ".venv" / "bin" / "python"

    def reexec_venv() -> None:
        _reexec([str(venv_py), script_path, *argv])

    def reexec_nix() -> None:
        inner = "python " + " ".join(shlex.quote(a) for a in [script_path, *argv])
        _reexec(["nix-shell", str(shellnix), "--run", inner])

    # On Nix the deps live behind the shellHook's LD_LIBRARY_PATH, so we must go
    # through nix-shell (which then activates any .venv itself).  On Ubuntu we
    # exec the .venv interpreter directly.
    if plat == "nix" and shutil.which("nix-shell") and shellnix.exists():
        reexec_nix()
    if venv_py.exists():
        reexec_venv()
    if shutil.which("nix-shell") and shellnix.exists():
        reexec_nix()
    _fail_missing_build123d(plat, root, shellnix)


def bootstrap_import_path() -> None:
    """Add the metal_plates dir to ``sys.path`` (for scripts in sub-folders).

    Kept for symmetry — scripts include a tiny inline finder instead, so this is
    only used by helpers already located in the metal_plates dir.
    """
    d = str(_metal_plates_dir())
    if d not in sys.path:
        sys.path.insert(0, d)
