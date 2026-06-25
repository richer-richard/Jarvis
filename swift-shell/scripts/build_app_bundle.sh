#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_ROOT="$(cd "$PACKAGE_DIR/.." && pwd)"

APP_NAME="${APP_NAME:-Jarvis}"
BUNDLE_ID="${BUNDLE_ID:-local.leo.jarvis}"
CONFIGURATION="${CONFIGURATION:-debug}"
DEFAULT_OUTPUT_ROOT="$PROJECT_ROOT/output"
OUTPUT_ROOT="${OUTPUT_ROOT:-$DEFAULT_OUTPUT_ROOT}"
APP_VERSION="${APP_VERSION:-0.1.497}"
BUILD_NUMBER="${BUILD_NUMBER:-497}"
REPLACE_APP="${REPLACE_APP:-1}"
ALLOW_NON_CANONICAL_JARVIS_BUNDLE="${ALLOW_NON_CANONICAL_JARVIS_BUNDLE:-0}"

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

is_truthy() {
  case "$1" in
    1|true|TRUE|yes|YES|on|ON)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

realpath_portable() {
  python3 -c 'import pathlib, sys; print(pathlib.Path(sys.argv[1]).resolve())' "$1"
}

canonical_output_root="$(realpath_portable "$DEFAULT_OUTPUT_ROOT")"
requested_output_root="$(realpath_portable "$OUTPUT_ROOT")"
if [[ "$requested_output_root" == "$canonical_output_root" ]] && ! is_truthy "$ALLOW_NON_CANONICAL_JARVIS_BUNDLE"; then
  if [[ "$APP_NAME" != "Jarvis" || "$BUNDLE_ID" != "local.leo.jarvis" ]]; then
    cat >&2 <<EOF
Refusing to build a non-canonical Jarvis app in $OUTPUT_ROOT.
Use APP_NAME=Jarvis and BUNDLE_ID=local.leo.jarvis for Leo's normal app, or set
ALLOW_NON_CANONICAL_JARVIS_BUNDLE=1 with a separate OUTPUT_ROOT for experiments.
EOF
    exit 1
  fi
  case "$REPLACE_APP" in
    1|true|TRUE|yes|YES|on|ON)
      ;;
    *)
      cat >&2 <<EOF
Refusing to create a numbered Jarvis bundle in $OUTPUT_ROOT.
The canonical build replaces output/Jarvis.app so Leo does not see duplicate Jarvis apps.
EOF
      exit 1
      ;;
  esac
fi

cleanup_numbered_app_bundles() {
  find "$OUTPUT_ROOT" -maxdepth 1 -type d -name "$APP_NAME-*.app" -exec rm -rf {} +
}

swift build --package-path "$PACKAGE_DIR" -c "$CONFIGURATION" --product jarvis-menu-bar
swift build --package-path "$PACKAGE_DIR" -c "$CONFIGURATION" --product jarvis-status-helper
swift build --package-path "$PACKAGE_DIR" -c "$CONFIGURATION" --product jarvis-browser-page-probe
swift build --package-path "$PACKAGE_DIR" -c "$CONFIGURATION" --product jarvis-browser-permission-probe
swift build --package-path "$PACKAGE_DIR" -c "$CONFIGURATION" --product jarvis-visible-screen-probe
BIN_DIR="$(swift build --package-path "$PACKAGE_DIR" -c "$CONFIGURATION" --show-bin-path)"
SOURCE_EXECUTABLE="$BIN_DIR/jarvis-menu-bar"
SOURCE_STATUS_HELPER="$BIN_DIR/jarvis-status-helper"
SOURCE_BROWSER_PAGE_PROBE="$BIN_DIR/jarvis-browser-page-probe"
SOURCE_BROWSER_PERMISSION_PROBE="$BIN_DIR/jarvis-browser-permission-probe"
SOURCE_VISIBLE_SCREEN_PROBE="$BIN_DIR/jarvis-visible-screen-probe"

if [[ ! -x "$SOURCE_EXECUTABLE" ]]; then
  echo "Missing built executable: $SOURCE_EXECUTABLE" >&2
  exit 1
fi
if [[ ! -x "$SOURCE_STATUS_HELPER" ]]; then
  echo "Missing built status helper: $SOURCE_STATUS_HELPER" >&2
  exit 1
fi
if [[ ! -x "$SOURCE_BROWSER_PAGE_PROBE" ]]; then
  echo "Missing built browser page probe: $SOURCE_BROWSER_PAGE_PROBE" >&2
  exit 1
fi
if [[ ! -x "$SOURCE_BROWSER_PERMISSION_PROBE" ]]; then
  echo "Missing built browser permission probe: $SOURCE_BROWSER_PERMISSION_PROBE" >&2
  exit 1
fi
if [[ ! -x "$SOURCE_VISIBLE_SCREEN_PROBE" ]]; then
  echo "Missing built visible screen probe: $SOURCE_VISIBLE_SCREEN_PROBE" >&2
  exit 1
fi

APP_DIR="$OUTPUT_ROOT/$APP_NAME.app"
if [[ -e "$APP_DIR" ]]; then
  case "$REPLACE_APP" in
    1|true|TRUE|yes|YES|on|ON)
      rm -rf "$APP_DIR"
      cleanup_numbered_app_bundles
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
cp "$SOURCE_STATUS_HELPER" "$MACOS_DIR/jarvis-status-helper"
chmod 755 "$MACOS_DIR/jarvis-status-helper"
cp "$SOURCE_BROWSER_PAGE_PROBE" "$MACOS_DIR/jarvis-browser-page-probe"
chmod 755 "$MACOS_DIR/jarvis-browser-page-probe"
cp "$SOURCE_BROWSER_PERMISSION_PROBE" "$MACOS_DIR/jarvis-browser-permission-probe"
chmod 755 "$MACOS_DIR/jarvis-browser-permission-probe"
cp "$SOURCE_VISIBLE_SCREEN_PROBE" "$MACOS_DIR/jarvis-visible-screen-probe"
chmod 755 "$MACOS_DIR/jarvis-visible-screen-probe"

if [[ -f "$PROJECT_ROOT/assets/Jarvis.icns" ]]; then
  cp "$PROJECT_ROOT/assets/Jarvis.icns" "$RESOURCES_DIR/Jarvis.icns"
fi

if [[ -f "$PROJECT_ROOT/assets/jarvis-logo-512.png" ]]; then
  cp "$PROJECT_ROOT/assets/jarvis-logo-512.png" "$RESOURCES_DIR/JarvisLogo.png"
elif [[ -f "$PROJECT_ROOT/assets/jarvis-logo-256.png" ]]; then
  cp "$PROJECT_ROOT/assets/jarvis-logo-256.png" "$RESOURCES_DIR/JarvisLogo.png"
fi
if [[ -f "$PROJECT_ROOT/assets/jarvis-menu-head.png" ]]; then
  cp "$PROJECT_ROOT/assets/jarvis-menu-head.png" "$RESOURCES_DIR/JarvisMenuHead.png"
fi
if [[ ! -f "$RESOURCES_DIR/JarvisMenuHead.png" ]]; then
  echo "Missing required menu-bar head image: $PROJECT_ROOT/assets/jarvis-menu-head.png" >&2
  exit 1
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
  <key>NSAppleEventsUsageDescription</key>
  <string>Jarvis needs permission to inspect or control apps such as Google Chrome only when Leo asks it to use those apps.</string>
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
