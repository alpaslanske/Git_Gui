#!/bin/sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
APPIMAGETOOL=${APPIMAGETOOL:-appimagetool}
ARCH=${ARCH:-x86_64}
export ARCH

if ! command -v "$APPIMAGETOOL" >/dev/null 2>&1; then
    echo "appimagetool is required. Install it or set APPIMAGETOOL to its path." >&2
    exit 1
fi

if ! command -v pyinstaller >/dev/null 2>&1; then
    echo "pyinstaller is required. Install it via pip install pyinstaller." >&2
    exit 1
fi

BUILD_TMP=$(mktemp -d "${TMPDIR:-/tmp}/git-manager-build.XXXXXX")
APPDIR="$BUILD_TMP/AppDir"
trap 'rm -rf "$BUILD_TMP"' EXIT HUP INT TERM

# 1. PyInstaller ile Python yorumlayıcısı, PySide6 ve GitPython'u paketle
pyinstaller --noconfirm --onedir --windowed \
    --name "git-manager" \
    --distpath "$BUILD_TMP/dist" \
    --workpath "$BUILD_TMP/work" \
    --specpath "$BUILD_TMP" \
    --add-data "$PROJECT_DIR/git_motoru.py:." \
    --add-data "$PROJECT_DIR/lang.py:." \
    --add-data "$PROJECT_DIR/icon.png:." \
    "$PROJECT_DIR/git_gui.py"

# 2. AppDir yapısını oluştur ve izinleri ayarla
mkdir -p "$APPDIR/usr/bin"
chmod 755 "$APPDIR"

cp -r "$BUILD_TMP/dist/git-manager/"* "$APPDIR/usr/bin/"
install -m 644 "$PROJECT_DIR/icon.png" "$APPDIR/git-manager.png"

# 3. AppRun başlatıcısını oluştur (gömülü PyInstaller çalıştırıcısını başlatır)
cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
APPDIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export PATH="$APPDIR/usr/bin:$PATH"
exec "$APPDIR/usr/bin/git-manager" "$@"
EOF
chmod 755 "$APPDIR/AppRun"

# 4. Masaüstü dosyası ve AppStream metaverisi
APP_ID="io.github.git_gui.GitManager"
mkdir -p "$APPDIR/usr/share/applications"

cat > "$APPDIR/${APP_ID}.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Git Manager
Exec=AppRun
Icon=git-manager
Categories=Development;
Terminal=false
EOF

cp "$APPDIR/${APP_ID}.desktop" "$APPDIR/usr/share/applications/${APP_ID}.desktop"
ln -s git-manager.png "$APPDIR/.DirIcon"

mkdir -p "$APPDIR/usr/share/metainfo"
cat > "$APPDIR/usr/share/metainfo/${APP_ID}.metainfo.xml" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<component type="desktop-application">
  <id>${APP_ID}</id>
  <metadata_license>FSFAP</metadata_license>
  <project_license>GPL-3.0+</project_license>
  <name>Git Manager</name>
  <summary>Graphical user interface for Git repositories</summary>
  <description>
    <p>Git Manager is a lightweight graphical interface to manage your Git repositories easily.</p>
  </description>
  <launchable type="desktop-id">${APP_ID}.desktop</launchable>
  <url type="homepage">https://github.com</url>
  <developer id="io.github.alpaslanske">
    <name>alpaslanske</name>
  </developer>
  <content_rating type="oars-1.1" />
</component>
EOF

chmod -R a+rX "$APPDIR"

# 5. Nihai AppImage dosyasını oluştur
"$APPIMAGETOOL" "$APPDIR" "$PROJECT_DIR/Git_Gui_Portable-${ARCH}.AppImage"
