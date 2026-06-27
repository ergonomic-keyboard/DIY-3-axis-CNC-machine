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

    VENV="$(git rev-parse --show-toplevel 2>/dev/null || pwd)/.venv"
    if [ -f "$VENV/bin/activate" ]; then
      source "$VENV/bin/activate"
    fi
  '';
}
