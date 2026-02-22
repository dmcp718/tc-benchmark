#!/bin/bash
#
# Build tframetest .deb package in an Ubuntu 22.04 Docker container
#
# Usage: ./build-deb.sh <version>
# Example: ./build-deb.sh 3025.12.0
#
# Requirements: Docker
# Output: ../tframetest_<version>_amd64.deb

set -euo pipefail

VERSION="${1:?Usage: $0 <version>}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
OUTPUT_FILE="tframetest_${VERSION}_amd64.deb"

echo "=== Building tframetest ${VERSION} .deb package ==="
echo ""

# Build the Docker image
echo "Building Docker image..."
docker build -t tframetest-deb-builder -f "$SCRIPT_DIR/Dockerfile.deb" "$SCRIPT_DIR"

# Run the build inside the container
echo "Building tframetest and packaging .deb..."
docker run --rm -v "$REPO_DIR:/output" tframetest-deb-builder bash -c "
    set -euo pipefail

    VERSION='${VERSION}'

    # Clone and build tframetest
    echo 'Cloning tframetest...'
    git clone --depth 1 --branch \"\${VERSION}\" https://github.com/tuxera/tframetest.git /build/tframetest
    cd /build/tframetest
    echo 'Building...'
    make release
    echo 'Build complete.'

    # Create .deb package structure
    PKG_DIR=/build/pkg
    mkdir -p \"\${PKG_DIR}/DEBIAN\"
    mkdir -p \"\${PKG_DIR}/usr/local/bin\"

    # Copy binary
    cp /build/tframetest/tframetest \"\${PKG_DIR}/usr/local/bin/tframetest\"
    chmod 755 \"\${PKG_DIR}/usr/local/bin/tframetest\"

    # Create control file
    cat > \"\${PKG_DIR}/DEBIAN/control\" <<CTRL
Package: tframetest
Version: \${VERSION}
Section: utils
Priority: optional
Architecture: amd64
Maintainer: Tuxera <support@tuxera.com>
Description: Media frame testing and benchmarking tool
 tframetest is a tool to test and benchmark writing/reading
 media frames to/from a disk.
Homepage: https://github.com/tuxera/tframetest
CTRL

    # Build the .deb
    dpkg-deb --build \"\${PKG_DIR}\" \"/output/${OUTPUT_FILE}\"
    echo 'Package built successfully.'
"

echo ""
echo "=== Done ==="
echo "Output: ${REPO_DIR}/${OUTPUT_FILE}"
ls -lh "${REPO_DIR}/${OUTPUT_FILE}"
