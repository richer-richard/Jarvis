#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_ROOT="$(cd "$PACKAGE_DIR/.." && pwd)"

APP_NAME="${APP_NAME:-Jarvis}"
BUNDLE_ID="${BUNDLE_ID:-local.leo.jarvis}"
CONFIGURATION="${CONFIGURATION:-debug}"
OUTPUT_ROOT="${OUTPUT_ROOT:-$PROJECT_ROOT/output}"
APP_VERSION="${APP_VERSION:-0.1.342}"
BUILD_NUMBER="${BUILD_NUMBER:-342}"
REPLACE_APP="${REPLACE_APP:-0}"

default_sign_identity() {
  local local_identity="Jarvis Local Code Signing"
  if command -v security >/dev/null 2>&1 \
    && security find-identity -v -p codesigning 2>/dev/null | grep -Fq "\"$local_identity\""; then
    printf '%s\n' "$local_identity"
    return
  fi
  printf '%s\n' "-"
}

SIGN_IDENTITY="${SIGN_IDENTITY:-$(default_sign_identity)}"

xml_escape() {
  local value="$1"
  value="${value//&/&amp;}"
  value="${value//</&lt;}"
  value="${value//>/&gt;}"
  value="${value//\"/&quot;}"
  value="${value//\'/&apos;}"
  printf '%s' "$value"
}

APP_NAME_XML="$(xml_escape "$APP_NAME")"
BUNDLE_ID_XML="$(xml_escape "$BUNDLE_ID")"
APP_VERSION_XML="$(xml_escape "$APP_VERSION")"
BUILD_NUMBER_XML="$(xml_escape "$BUILD_NUMBER")"

mkdir -p "$OUTPUT_ROOT"

swift build --package-path "$PACKAGE_DIR" -c "$CONFIGURATION" --product jarvis-menu-bar
BIN_DIR="$(swift build --package-path "$PACKAGE_DIR" -c "$CONFIGURATION" --show-bin-path)"
SOURCE_EXECUTABLE="$BIN_DIR/jarvis-menu-bar"

if [[ ! -x "$SOURCE_EXECUTABLE" ]]; then
  echo "Missing built executable: $SOURCE_EXECUTABLE" >&2
  exit 1
fi

APP_DIR="$OUTPUT_ROOT/$APP_NAME.app"
if [[ -e "$APP_DIR" ]]; then
  case "$REPLACE_APP" in
    1|true|TRUE|yes|YES|on|ON)
      rm -rf "$APP_DIR"
      ;;
    *)
      index=2
      while [[ -e "$OUTPUT_ROOT/$APP_NAME-$index.app" ]]; do
        index=$((index + 1))
      done
      APP_DIR="$OUTPUT_ROOT/$APP_NAME-$index.app"
      ;;
  esac
fi

CONTENTS_DIR="$APP_DIR/Contents"
MACOS_DIR="$CONTENTS_DIR/MacOS"
RESOURCES_DIR="$CONTENTS_DIR/Resources"

mkdir -p "$MACOS_DIR" "$RESOURCES_DIR"
cp "$SOURCE_EXECUTABLE" "$MACOS_DIR/jarvis-menu-bar"
chmod 755 "$MACOS_DIR/jarvis-menu-bar"

if [[ -f "$PROJECT_ROOT/assets/Jarvis.icns" ]]; then
  cp "$PROJECT_ROOT/assets/Jarvis.icns" "$RESOURCES_DIR/Jarvis.icns"
fi

if [[ -f "$PROJECT_ROOT/assets/jarvis-logo-512.png" ]]; then
  cp "$PROJECT_ROOT/assets/jarvis-logo-512.png" "$RESOURCES_DIR/JarvisLogo.png"
elif [[ -f "$PROJECT_ROOT/assets/jarvis-logo-256.png" ]]; then
  cp "$PROJECT_ROOT/assets/jarvis-logo-256.png" "$RESOURCES_DIR/JarvisLogo.png"
fi
printf '%s\n' "$PROJECT_ROOT" > "$RESOURCES_DIR/JarvisWorkspaceRoot.txt"

WORKER_DIR="$RESOURCES_DIR/JarvisWorker"
mkdir -p "$WORKER_DIR/scripts"
rsync -a --delete --delete-excluded --exclude '__pycache__' "$PROJECT_ROOT/jarvis/" "$WORKER_DIR/jarvis/"
cp "$PROJECT_ROOT/scripts/run_dashboard.py" "$WORKER_DIR/scripts/run_dashboard.py"

cat > "$CONTENTS_DIR/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDevelopmentRegion</key>
  <string>en</string>
  <key>CFBundleDisplayName</key>
  <string>$APP_NAME_XML</string>
  <key>CFBundleExecutable</key>
  <string>jarvis-menu-bar</string>
  <key>CFBundleIconFile</key>
  <string>Jarvis.icns</string>
  <key>CFBundleIdentifier</key>
  <string>$BUNDLE_ID_XML</string>
  <key>CFBundleInfoDictionaryVersion</key>
  <string>6.0</string>
  <key>CFBundleName</key>
  <string>$APP_NAME_XML</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>$APP_VERSION_XML</string>
  <key>CFBundleVersion</key>
  <string>$BUILD_NUMBER_XML</string>
  <key>LSMinimumSystemVersion</key>
  <string>14.0</string>
  <key>NSHighResolutionCapable</key>
  <true/>
  <key>NSMicrophoneUsageDescription</key>
  <string>Jarvis will use the microphone only after Leo enables voice command capture.</string>
  <key>NSSpeechRecognitionUsageDescription</key>
  <string>Jarvis will use speech recognition only after Leo enables command transcription.</string>
  <key>NSPrincipalClass</key>
  <string>NSApplication</string>
</dict>
</plist>
EOF

plutil -lint "$CONTENTS_DIR/Info.plist" >/dev/null

if command -v codesign >/dev/null 2>&1; then
  codesign --force --deep --sign "$SIGN_IDENTITY" "$APP_DIR" >/dev/null
fi

echo "$APP_DIR"
