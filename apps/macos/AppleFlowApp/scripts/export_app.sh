#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$APP_DIR/../../.." && pwd)"
DIST_DIR="$REPO_ROOT/dist"
DERIVED_DIR="$APP_DIR/.build/xcodebuild"
SCHEME="AppleFlowApp"
CONFIG="Release"

mkdir -p "$DIST_DIR"

generate_icon_icns() {
  local output_icns="$1"
  local tmp_dir
  tmp_dir="$(mktemp -d)"
  local iconset_dir="$tmp_dir/AppIcon.iconset"
  mkdir -p "$iconset_dir"

  render_emoji_png() {
    local px_size="$1"
    local out_png="$2"
    swift - "$px_size" "$out_png" <<'SWIFT'
import AppKit
import Foundation

guard CommandLine.arguments.count >= 3 else {
    fputs("Usage: swift <size> <output>\n", stderr)
    exit(1)
}

let sizeValue = CGFloat(Int(CommandLine.arguments[1]) ?? 512)
let output = URL(fileURLWithPath: CommandLine.arguments[2])

let image = NSImage(size: NSSize(width: sizeValue, height: sizeValue))
image.lockFocus()

NSColor.clear.setFill()
NSBezierPath(rect: NSRect(x: 0, y: 0, width: sizeValue, height: sizeValue)).fill()

let fontSize = sizeValue * 0.78
let attributes: [NSAttributedString.Key: Any] = [
    .font: NSFont.systemFont(ofSize: fontSize),
]
let text = "🍎" as NSString
let textSize = text.size(withAttributes: attributes)
let drawRect = NSRect(
    x: (sizeValue - textSize.width) / 2.0,
    y: (sizeValue - textSize.height) / 2.0 + sizeValue * 0.02,
    width: textSize.width,
    height: textSize.height
)
text.draw(in: drawRect, withAttributes: attributes)

image.unlockFocus()

guard
    let tiffData = image.tiffRepresentation,
    let rep = NSBitmapImageRep(data: tiffData),
    let pngData = rep.representation(using: .png, properties: [:])
else {
    fputs("Failed to render icon PNG\n", stderr)
    exit(1)
}

do {
    try pngData.write(to: output)
} catch {
    fputs("Failed writing PNG: \(error)\n", stderr)
    exit(1)
}
SWIFT
  }

  render_emoji_png 16   "$iconset_dir/icon_16x16.png"
  render_emoji_png 32   "$iconset_dir/icon_16x16@2x.png"
  render_emoji_png 32   "$iconset_dir/icon_32x32.png"
  render_emoji_png 64   "$iconset_dir/icon_32x32@2x.png"
  render_emoji_png 128  "$iconset_dir/icon_128x128.png"
  render_emoji_png 256  "$iconset_dir/icon_128x128@2x.png"
  render_emoji_png 256  "$iconset_dir/icon_256x256.png"
  render_emoji_png 512  "$iconset_dir/icon_256x256@2x.png"
  render_emoji_png 512  "$iconset_dir/icon_512x512.png"
  render_emoji_png 1024 "$iconset_dir/icon_512x512@2x.png"

  iconutil -c icns "$iconset_dir" -o "$output_icns"
  rm -rf "$tmp_dir"
}

inject_icon_into_bundle() {
  local bundle_path="$1"
  local resources_dir="$bundle_path/Contents/Resources"
  local plist_path="$bundle_path/Contents/Info.plist"
  local icon_path="$resources_dir/AppIcon.icns"

  mkdir -p "$resources_dir"
  generate_icon_icns "$icon_path"

  /usr/libexec/PlistBuddy -c "Delete :CFBundleIconFile" "$plist_path" >/dev/null 2>&1 || true
  /usr/libexec/PlistBuddy -c "Add :CFBundleIconFile string AppIcon" "$plist_path"
  /usr/libexec/PlistBuddy -c "Delete :CFBundleVersion" "$plist_path" >/dev/null 2>&1 || true
  /usr/libexec/PlistBuddy -c "Add :CFBundleVersion string $(date +%s)" "$plist_path"
  /usr/libexec/PlistBuddy -c "Delete :CFBundleShortVersionString" "$plist_path" >/dev/null 2>&1 || true
  /usr/libexec/PlistBuddy -c "Add :CFBundleShortVersionString string 1.0.$(date +%s)" "$plist_path"

  # Encourage Finder/Dock to refresh icon metadata.
  /usr/bin/touch "$bundle_path"
  /usr/bin/touch "$resources_dir"
  /usr/bin/touch "$icon_path"
}

(
  cd "$APP_DIR"
  xcodebuild \
    -scheme "$SCHEME" \
    -configuration "$CONFIG" \
    -destination "platform=macOS" \
    -derivedDataPath "$DERIVED_DIR" \
    build
)

APP_BUNDLE="$DERIVED_DIR/Build/Products/$CONFIG/$SCHEME.app"
EXECUTABLE_BIN="$DERIVED_DIR/Build/Products/$CONFIG/$SCHEME"
DIST_BUNDLE="$DIST_DIR/$SCHEME.app"

if [[ ! -d "$APP_BUNDLE" ]]; then
  if [[ ! -x "$EXECUTABLE_BIN" ]]; then
    echo "Build succeeded but neither app bundle nor executable was found."
    echo "Expected one of:"
    echo "  - $APP_BUNDLE"
    echo "  - $EXECUTABLE_BIN"
    exit 1
  fi

  rm -rf "$DIST_BUNDLE"
  mkdir -p "$DIST_BUNDLE/Contents/MacOS" "$DIST_BUNDLE/Contents/Resources"
  cp "$EXECUTABLE_BIN" "$DIST_BUNDLE/Contents/MacOS/$SCHEME"
  chmod +x "$DIST_BUNDLE/Contents/MacOS/$SCHEME"

  cat > "$DIST_BUNDLE/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>CFBundleName</key>
    <string>$SCHEME</string>
    <key>CFBundleDisplayName</key>
    <string>$SCHEME</string>
    <key>CFBundleIdentifier</key>
    <string>local.appleflow.gui</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0.0</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleExecutable</key>
    <string>$SCHEME</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>LSMinimumSystemVersion</key>
    <string>13.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
  </dict>
</plist>
EOF
else
  rm -rf "$DIST_BUNDLE"
  cp -R "$APP_BUNDLE" "$DIST_BUNDLE"
fi

inject_icon_into_bundle "$DIST_BUNDLE"

(
  cd "$DIST_DIR"
  rm -f "$SCHEME-macOS.zip"
  /usr/bin/ditto -c -k --sequesterRsrc --keepParent "$SCHEME.app" "$SCHEME-macOS.zip"
)

echo "Export complete:"
echo "  App: $DIST_DIR/$SCHEME.app"
echo "  Zip: $DIST_DIR/$SCHEME-macOS.zip"
echo
echo "Tip: If running outside repo root, set APPLE_FLOW_REPO_ROOT before launching."
