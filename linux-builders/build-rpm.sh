#!/bin/bash
#
# Build tframetest .rpm package in an AlmaLinux 9 Docker container
#
# Usage: ./build-rpm.sh <version>
# Example: ./build-rpm.sh 3025.12.0
#
# Requirements: Docker
# Output: ../tframetest-<version>-1.el9.x86_64.rpm

set -euo pipefail

VERSION="${1:?Usage: $0 <version>}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
OUTPUT_FILE="tframetest-${VERSION}-1.el9.x86_64.rpm"

echo "=== Building tframetest ${VERSION} .rpm package ==="
echo ""

# Build the Docker image
echo "Building Docker image..."
docker build -t tframetest-rpm-builder -f "$SCRIPT_DIR/Dockerfile.rpm" "$SCRIPT_DIR"

# Run the build inside the container
echo "Building tframetest and packaging .rpm..."
docker run --rm -v "$REPO_DIR:/output" tframetest-rpm-builder bash -c "
    set -euo pipefail

    VERSION='${VERSION}'

    # Clone and build tframetest
    echo 'Cloning tframetest...'
    git clone --depth 1 --branch \"\${VERSION}\" https://github.com/tuxera/tframetest.git /build/tframetest
    cd /build/tframetest
    echo 'Building...'
    make release
    echo 'Build complete.'

    # Set up rpmbuild directory structure
    mkdir -p /root/rpmbuild/{BUILD,RPMS,SOURCES,SPECS,SRPMS}
    mkdir -p /root/rpmbuild/BUILDROOT/tframetest-\${VERSION}-1.el9.x86_64/usr/local/bin

    # Copy binary
    cp /build/tframetest/tframetest /root/rpmbuild/BUILDROOT/tframetest-\${VERSION}-1.el9.x86_64/usr/local/bin/tframetest
    chmod 755 /root/rpmbuild/BUILDROOT/tframetest-\${VERSION}-1.el9.x86_64/usr/local/bin/tframetest

    # Create spec file
    cat > /root/rpmbuild/SPECS/tframetest.spec <<SPEC
Name:           tframetest
Version:        \${VERSION}
Release:        1.el9
Summary:        Media frame testing and benchmarking tool
License:        GPLv2+
URL:            https://github.com/tuxera/tframetest

%description
tframetest is a tool to test and benchmark writing/reading
media frames to/from a disk.

%install
mkdir -p %{buildroot}/usr/local/bin
cp /root/rpmbuild/BUILDROOT/tframetest-\${VERSION}-1.el9.x86_64/usr/local/bin/tframetest %{buildroot}/usr/local/bin/tframetest

%files
/usr/local/bin/tframetest
SPEC

    # Build the RPM
    rpmbuild -bb /root/rpmbuild/SPECS/tframetest.spec
    cp /root/rpmbuild/RPMS/x86_64/tframetest-\${VERSION}-1.el9.x86_64.rpm /output/
    echo 'Package built successfully.'
"

echo ""
echo "=== Done ==="
echo "Output: ${REPO_DIR}/${OUTPUT_FILE}"
ls -lh "${REPO_DIR}/${OUTPUT_FILE}"
