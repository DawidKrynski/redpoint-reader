#!/bin/bash
# Builds dist/Redpoint-x86_64.AppImage. Runs inside ubuntu:22.04 (glibc 2.35) so the result
# works on most current distributions. Locally:
#   docker run --rm -v "$PWD":/src -w /src ubuntu:22.04 packaging/build-appimage.sh
set -euxo pipefail
export DEBIAN_FRONTEND=noninteractive
if command -v apt-get >/dev/null && [ "$(id -u)" = 0 ]; then
  apt-get update -qq
  apt-get install -y -qq --no-install-recommends ca-certificates curl file binutils desktop-file-utils wl-clipboard \
    libegl1 libgl1 libfontconfig1 libfreetype6 libdbus-1-3 libxkbcommon0 libxkbcommon-x11-0 \
    libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 \
    libxcb-shape0 libxcb-xfixes0 libxcb-xinerama0 libxcb-xkb1 libwayland-client0 libwayland-cursor0 \
    libwayland-egl1 libx11-6 libx11-xcb1 libglib2.0-0 libgssapi-krb5-2 >/dev/null
fi
# Recent wl-clipboard: KWin 6 and other current compositors only offer ext-data-control,
# which the wl-clipboard 2.0 in Ubuntu 22.04 does not know.
WLC=build/wl-clipboard
if [ ! -x "$WLC/install/bin/wl-paste" ]; then
  apt-get install -y -qq --no-install-recommends meson ninja-build gcc libc6-dev pkg-config libwayland-dev wayland-protocols xz-utils >/dev/null
  # ext-data-control needs wayland-protocols >= 1.39 (22.04 ships 1.25)
  mkdir -p build/wayland-protocols
  curl -fsSL https://gitlab.freedesktop.org/wayland/wayland-protocols/-/releases/1.45/downloads/wayland-protocols-1.45.tar.xz \
    | tar xJ -C build/wayland-protocols --strip-components=1
  (cd build/wayland-protocols && meson setup b --prefix=/usr/local -Dtests=false >/dev/null && ninja -C b install >/dev/null)
  mkdir -p "$WLC"
  curl -fsSL https://github.com/bugaevc/wl-clipboard/archive/refs/tags/v2.3.0.tar.gz | tar xz -C "$WLC" --strip-components=1
  (cd "$WLC" && meson setup b --prefix="$PWD/install" --buildtype=release -Dzshcompletiondir=no -Dfishcompletiondir=no >/dev/null && ninja -C b install >/dev/null)
fi
export REDPOINT_WL_PASTE="$PWD/$WLC/install/bin/wl-paste"
command -v uv >/dev/null || { curl -LsSf https://astral.sh/uv/0.9.9/install.sh | sh >/dev/null; export PATH="$HOME/.local/bin:$PATH"; }
export UV_PROJECT_ENVIRONMENT=/tmp/redpoint-build-venv UV_LINK_MODE=copy
uv sync --extra dev --python 3.12 -q
uv run python tools/make_icons.py build/icons
uv run pyinstaller --noconfirm --clean --distpath build/pyi-dist --workpath build/pyi-work packaging/redpoint.spec >/dev/null
VERSION=$(uv run python -c 'import redpoint; print(redpoint.__version__)')
APPDIR=build/AppDir
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/applications" "$APPDIR/usr/share/icons/hicolor/256x256/apps"
cp -a build/pyi-dist/redpoint "$APPDIR/usr/lib-redpoint"
ln -s ../lib-redpoint/redpoint "$APPDIR/usr/bin/redpoint"
# Same idea as the AppImage excludelist: libraries every desktop has and that must match the
# host (fontconfig reads the host's config files, GPU drivers need the host's libstdc++).
for lib in libfontconfig.so.1 libfreetype.so.6 libX11.so.6 libX11-xcb.so.1 libdbus-1.so.3 libstdc++.so.6 libgcc_s.so.1; do
  rm -f "$APPDIR/usr/lib-redpoint/_internal/$lib"
done
ID=io.github.dawidkrynski.Redpoint
cat > "$APPDIR/$ID.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=Redpoint
Comment=Read selected text word by word
Exec=redpoint
Icon=$ID
Terminal=false
Categories=Utility;Accessibility;
DESK
cp "$APPDIR/$ID.desktop" "$APPDIR/usr/share/applications/"
cp build/icons/redpoint.png "$APPDIR/$ID.png"
cp build/icons/redpoint.png "$APPDIR/usr/share/icons/hicolor/256x256/apps/$ID.png"
ln -sf "$ID.png" "$APPDIR/.DirIcon"
cat > "$APPDIR/AppRun" <<'RUN'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
export APPDIR="${APPDIR:-$HERE}"
exec "$HERE/usr/lib-redpoint/redpoint" "$@"
RUN
chmod +x "$APPDIR/AppRun"
TOOL=build/appimagetool-x86_64.AppImage
[ -x "$TOOL" ] || { curl -fsSL -o "$TOOL" https://github.com/AppImage/appimagetool/releases/download/1.9.0/appimagetool-x86_64.AppImage; chmod +x "$TOOL"; }
mkdir -p dist
ARCH=x86_64 "$TOOL" --appimage-extract-and-run --no-appstream "$APPDIR" "dist/Redpoint-$VERSION-x86_64.AppImage"
ls -la dist/
