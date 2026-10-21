#!/usr/bin/env bash
# Packages dist/Simple-Info/ (already built by PyInstaller, onedir mode)
# into a .deb that installs to /opt/simple-info and adds a proper menu
# entry + icon, so it behaves like a native app rather than a dropped
# binary. Uses dpkg-deb directly, which ships with Debian-based distros
# (Pop!_OS included) — no extra tool to install in CI.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUNDLE="$ROOT/dist/Simple-Info"
VERSION="$(grep -o '__version__ = "[^"]*"' "$ROOT/src/simple_info/__init__.py" | cut -d'"' -f2)"
ARCH="$(dpkg --print-architecture)"
PKG_ROOT="$ROOT/dist/deb-staging"
OUT="$ROOT/dist/simple-info_${VERSION}_${ARCH}.deb"

if [ ! -d "$BUNDLE" ]; then
  echo "error: $BUNDLE not found — run PyInstaller first" >&2
  exit 1
fi

rm -rf "$PKG_ROOT" "$OUT"
mkdir -p "$PKG_ROOT/DEBIAN"
mkdir -p "$PKG_ROOT/opt/simple-info"
mkdir -p "$PKG_ROOT/usr/bin"
mkdir -p "$PKG_ROOT/usr/share/applications"

cp -R "$BUNDLE"/. "$PKG_ROOT/opt/simple-info/"
ln -s /opt/simple-info/Simple-Info "$PKG_ROOT/usr/bin/simple-info"
cp "$ROOT/packaging/linux/simple-info.desktop" "$PKG_ROOT/usr/share/applications/"

for size in 16 32 48 64 128 256 512; do
  dir="$PKG_ROOT/usr/share/icons/hicolor/${size}x${size}/apps"
  mkdir -p "$dir"
  cp "$ROOT/packaging/icons/icon_${size}.png" "$dir/simple-info.png"
done

cat > "$PKG_ROOT/DEBIAN/control" <<EOF
Package: simple-info
Version: $VERSION
Section: misc
Priority: optional
Architecture: $ARCH
Depends: libegl1, libxkbcommon0, libxcb-cursor0, libfontconfig1, libdbus-1-3
Recommends: v4l-utils
Maintainer: Mike Hellyer
Description: An information board: weather and more, at a glance
 Switch between full-screen boards of live information, each with its
 own background so you can tell at a glance what it shows. Starts with
 a big clock and the local weather forecast over the real sky.
EOF

dpkg-deb --build --root-owner-group "$PKG_ROOT" "$OUT"
rm -rf "$PKG_ROOT"

echo "wrote $OUT"
