#!/bin/bash

# Build macOS installer package for tframetest
# Usage: ./build-installer.sh

set -e

VERSION="3025.1.1"
IDENTIFIER="com.tuxera.tframetest"
INSTALL_LOCATION="/usr/local/bin"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="$SCRIPT_DIR/build"
PAYLOAD_DIR="$SCRIPT_DIR/payload"
SCRIPTS_DIR="$SCRIPT_DIR/scripts"

echo "Building tframetest installer package..."
echo "Version: $VERSION"
echo ""

# Clean and create build directory
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

# Step 1: Build component package
echo "Step 1: Building component package..."
pkgbuild \
    --root "$PAYLOAD_DIR" \
    --identifier "$IDENTIFIER" \
    --version "$VERSION" \
    --scripts "$SCRIPTS_DIR" \
    --install-location "/" \
    "$BUILD_DIR/tframetest.pkg"

echo "✓ Component package created"

# Step 2: Build product archive (distribution package)
echo ""
echo "Step 2: Building distribution package..."
productbuild \
    --distribution "$SCRIPT_DIR/Distribution.xml" \
    --package-path "$BUILD_DIR" \
    --resources "$SCRIPT_DIR" \
    "$BUILD_DIR/tframetest-$VERSION-macos-arm64.pkg"

echo "✓ Distribution package created"

# Cleanup intermediate files
rm -f "$BUILD_DIR/tframetest.pkg"

echo ""
echo "========================================="
echo "Installer built successfully!"
echo ""
echo "Output: $BUILD_DIR/tframetest-$VERSION-macos-arm64.pkg"
echo ""
echo "To install:"
echo "  sudo installer -pkg $BUILD_DIR/tframetest-$VERSION-macos-arm64.pkg -target /"
echo ""
echo "Or double-click the .pkg file to use the GUI installer."
echo "========================================="
