{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  buildInputs = with pkgs; [
    python313
    libGL
    fontconfig
    freetype
    expat
    dbus
    glib
    libxext
    libx11
    libxrender
    libice
    libsm
    libxi
    libxmu
    libxcb
    libxkbcommon
    xcb-util-cursor
    xcbutilimage
    xcbutilkeysyms
    xcbutilrenderutil
    xcbutilwm
    wayland
    stdenv.cc.cc.lib
    zlib
    zstd
  ];

  shellHook = ''
    export LD_LIBRARY_PATH="${pkgs.lib.makeLibraryPath (with pkgs; [
      libGL
      fontconfig
      freetype
      expat
      dbus
      glib
      libxext
      libx11
      libxrender
      libice
      libsm
      libxi
      libxmu
      libxcb
      libxkbcommon
      xcb-util-cursor
      xcbutilimage
      xcbutilkeysyms
      xcbutilrenderutil
      xcbutilwm
      wayland
      stdenv.cc.cc.lib
      zlib
      zstd
    ])}:$LD_LIBRARY_PATH"
    # Help PyQt6 find its bundled Qt plugins
    export QT_QPA_PLATFORM_PLUGIN_PATH=""

    # Provision (once) and activate a repo-root .venv holding the build123d
    # toolchain. Deps are declared in metal_plates/requirements.txt — the same
    # file the Ubuntu setup uses — so both platforms install an identical set,
    # and env_bootstrap.py can auto-re-exec into this .venv.
    ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
    VENV="$ROOT/.venv"
    REQ="$ROOT/hardware_mods/metal_plates/requirements.txt"
    if [ ! -f "$VENV/bin/activate" ]; then
      echo "[shell.nix] creating .venv and installing the build123d toolchain ..."
      python -m venv "$VENV"
      "$VENV/bin/pip" install --upgrade pip
      "$VENV/bin/pip" install -r "$REQ"
    fi
    source "$VENV/bin/activate"
  '';
}
