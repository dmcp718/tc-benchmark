#!/usr/bin/env bash
#
# build-onefile.sh - build a zero-prerequisite tfbench onefile executable
# (Tier 2). Embeds Python + rich + the platform tframetest binary into a
# single file via PyInstaller; no Python/uv install is needed to run the
# result.
#
# Usage: scripts/build-onefile.sh
#
# Run this ON the target OS/arch -- PyInstaller does not cross-compile.
#
# macOS: run directly on this machine (uses whatever `uname -m` reports;
#   this repo only ships a tframetest-macos arm64 binary today).
#
# Linux x86-64: no build box is available in this dev environment, so run
#   it inside the same AlmaLinux 9 image linux-builders/ uses for the
#   .rpm, with a Linux tframetest binary already built at
#   build/tframetest-linux-x86_64 (see linux-builders/build-rpm.sh for how
#   that's produced -- apply patches/random-fill.patch, `make release
#   LDFLAGS='-static -pthread'`, after `dnf config-manager --set-enabled
#   crb && dnf install -y glibc-static` for the static libc):
#     docker run --rm --platform linux/amd64 -v "$(pwd):/repo" -w /repo \
#       almalinux:9 bash -c './scripts/build-onefile.sh'
#   The container needs python3/pip (dnf install -y python3 python3-pip);
#   this script falls back to pip when uv isn't on PATH.
#
# Windows x86-64: run on a real or VM Windows box (PyInstaller does not
#   cross-compile Windows executables from macOS/Linux either):
#     py -m pip install pyinstaller "rich>=13.7.0"
#     pyinstaller --onefile --name tfbench-<version>-win64 ^
#       --add-binary "tframetest.exe;." tfbench.py
#   (requires an unpatched-or-better win64 tframetest.exe -- see tcb-0is
#   for the still-open item to rebuild it with the patches applied.)
#
# macOS Gatekeeper note: an ad-hoc-signed onefile binary downloaded through
# a browser gets the com.apple.quarantine xattr, which Gatekeeper will
# block on first run ("cannot be opened because the developer cannot be
# verified"). Two ways around it:
#   - Distribute via curl/scp instead of a browser download (neither sets
#     the quarantine attribute).
#   - If it was downloaded via browser: `xattr -d com.apple.quarantine <path>`
#     before running.
# A properly signed+notarized binary (Apple Developer ID) avoids this
# entirely but requires paid enrollment and is out of scope here.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
DIST_DIR="$REPO_DIR/dist"

VERSION="$(grep -m1 '^version' "$REPO_DIR/pyproject.toml" | sed -E 's/version = "(.*)"/\1/')"
if [[ -z "$VERSION" ]]; then
    echo "error: could not read version from pyproject.toml" >&2
    exit 1
fi

OS="$(uname -s)"
ARCH="$(uname -m)"
STAGE_DIR="$(mktemp -d)"
trap 'rm -rf "$STAGE_DIR"' EXIT

case "$OS" in
    Darwin)
        BINARY_SRC="$REPO_DIR/tframetest-macos"
        # Kept under its existing name -- Darwin discovery checks for
        # tframetest-macos (or plain tframetest) in the bundle dir.
        STAGED_BINARY="$STAGE_DIR/tframetest-macos"
        PLATFORM_TAG="macos-${ARCH}"
        ;;
    Linux)
        BINARY_SRC="$REPO_DIR/build/tframetest-linux-x86_64"
        # Renamed to plain "tframetest" -- --add-binary keeps the source
        # basename, and tfbench's non-Darwin/Windows discovery only
        # checks for that exact name in the bundle dir.
        STAGED_BINARY="$STAGE_DIR/tframetest"
        PLATFORM_TAG="linux-x86_64"
        ;;
    *)
        echo "error: this script doesn't know how to build a onefile executable on '$OS'." >&2
        echo "See the Windows notes in this script's header for the manual commands." >&2
        exit 1
        ;;
esac

if [[ ! -f "$BINARY_SRC" ]]; then
    echo "error: expected tframetest binary not found at $BINARY_SRC" >&2
    if [[ "$OS" == "Linux" ]]; then
        echo "(build it first -- see linux-builders/ and this script's header)" >&2
    fi
    exit 1
fi
cp "$BINARY_SRC" "$STAGED_BINARY"
chmod 755 "$STAGED_BINARY"

OUT_NAME="tfbench-${VERSION}-${PLATFORM_TAG}"

mkdir -p "$DIST_DIR"

echo "Building onefile executable for $PLATFORM_TAG ..."
cd "$REPO_DIR"

if command -v uv >/dev/null 2>&1; then
    uvx --with "rich>=13.7.0" pyinstaller \
        --onefile \
        --name "$OUT_NAME" \
        --distpath "$DIST_DIR" \
        --workpath "$REPO_DIR/build/pyinstaller" \
        --specpath "$REPO_DIR/build" \
        --add-binary "$STAGED_BINARY:." \
        tfbench.py
else
    # No uv on this box (e.g. a bare Docker build image) -- fall back to
    # a plain pip install of pyinstaller + rich.
    python3 -m pip install --quiet pyinstaller "rich>=13.7.0"
    python3 -m PyInstaller \
        --onefile \
        --name "$OUT_NAME" \
        --distpath "$DIST_DIR" \
        --workpath "$REPO_DIR/build/pyinstaller" \
        --specpath "$REPO_DIR/build" \
        --add-binary "$STAGED_BINARY:." \
        tfbench.py
fi

OUT_PATH="$DIST_DIR/$OUT_NAME"

if [[ "$OS" == "Darwin" ]]; then
    echo "Ad-hoc codesigning $OUT_PATH ..."
    codesign -s - --force "$OUT_PATH"
fi

chmod 755 "$OUT_PATH"
echo "built: dist/$OUT_NAME"
