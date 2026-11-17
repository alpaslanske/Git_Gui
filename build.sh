#!/bin/sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
APPIMAGETOOL=${APPIMAGETOOL:-appimagetool}
ARCH=${ARCH:-x86_64}

if ! command -v "$APPIMAGETOOL" >/dev/null 2>&1; then
    echo "appimagetool is required. Install it or set APPIMAGETOOL to its path." >&2
    exit 1
fi

APPDIR=$(mktemp -d "${TMPDIR:-/tmp}/git-manager-appdir.XXXXXX")
trap 'rm -rf "$APPDIR"' EXIT HUP INT TERM

install -D -m 755 "$PROJECT_DIR/git_gui.py" "$APPDIR/usr/share/git-manager/git_gui.py"
install -m 644 "$PROJECT_DIR/git_motoru.py" "$APPDIR/usr/share/git-manager/git_motoru.py"
install -m 644 "$PROJECT_DIR/lang.py" "$APPDIR/usr/share/git-manager/lang.py"
install -m 644 "$PROJECT_DIR/icon.png" "$APPDIR/git-manager.png"

cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
APPDIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 "$APPDIR/usr/share/git-manager/git_gui.py" "$@"
EOF
chmod 755 "$APPDIR/AppRun"

cat > "$APPDIR/git-manager.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Git Manager
Exec=AppRun
Icon=git-manager
Categories=Development;Utility;
Terminal=false
EOF
ln -s git-manager.png "$APPDIR/.DirIcon"

"$APPIMAGETOOL" "$APPDIR" "$PROJECT_DIR/Git_Gui_Portable-${ARCH}.AppImage"
