#!/usr/bin/env bash
#
# make-bundles.sh - build per-platform portable tfbench zips (Tier 1)
#
# Produces dist/tfbench-<version>-<platform>.zip, each containing:
#   tfbench.py          (PEP 723 header resolves its own deps via `uv run`)
#   tframetest-macos     -- macOS bundle only, matches tfbench.py's Darwin
#                            discovery check for a script-dir binary
#   tframetest            -- Linux bundle only, matches tfbench.py's
#                            fallback discovery check for a script-dir binary
#   COPYING              (GPL-2.0-or-later, from upstream tframetest)
#   BUNDLE-README.txt    (quick start + patch/license provenance)
#
# Usage: scripts/make-bundles.sh
#
# The macOS arm64 bundle is always built from the tframetest-macos binary
# already checked into the repo root. The Linux x86-64 bundle is only
# built if a Linux binary exists at build/tframetest-linux-x86_64 (see
# linux-builders/ for how to produce one via Docker) -- if it's missing,
# that bundle is skipped with a note, not silently faked.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
DIST_DIR="$REPO_DIR/dist"

VERSION="$(grep -m1 '^version' "$REPO_DIR/pyproject.toml" | sed -E 's/version = "(.*)"/\1/')"
if [[ -z "$VERSION" ]]; then
    echo "error: could not read version from pyproject.toml" >&2
    exit 1
fi

LINUX_BINARY="$REPO_DIR/build/tframetest-linux-x86_64"

# Optional macOS signing/notarization (see scripts/build-onefile.sh header
# for the full story). With CODESIGN_IDENTITY set, the tframetest-macos
# COPY staged into the zip is Developer ID-signed (the checked-in binary
# stays ad-hoc so it remains bit-reproducible from upstream + patches);
# with NOTARIZE=1 the finished zip is submitted to Apple, which covers the
# signed binary inside it. Zips can't be stapled -- Gatekeeper fetches the
# ticket online.
CODESIGN_IDENTITY="${CODESIGN_IDENTITY:-}"
NOTARIZE="${NOTARIZE:-0}"
NOTARY_PROFILE="${NOTARY_PROFILE:-notarytool}"
if [[ "$NOTARIZE" == "1" && -z "$CODESIGN_IDENTITY" ]]; then
    echo "error: NOTARIZE=1 requires CODESIGN_IDENTITY" >&2
    exit 1
fi

mkdir -p "$DIST_DIR"

write_bundle_readme() {
    local out="$1" patch_note="$2"
    cat > "$out" <<EOF
tfbench ${VERSION} - portable bundle
=====================================

What this is
------------
A self-contained copy of tfbench, a Rich TUI wrapper around the native
tframetest benchmark tool. This bundle carries its own tframetest binary,
so it does not depend on anything installed system-wide.

Quick start
-----------
Install uv (one-time, if you don't have it):
    curl -LsSf https://astral.sh/uv/install.sh | sh

Then, from inside this unzipped directory:
    uv run tfbench.py --version
    uv run tfbench.py -w 4k -n 500 -t 8 /path/to/target

tfbench.py carries a PEP 723 inline metadata header, so uv resolves its
only dependency (rich>=13.7.0) automatically -- no pyproject.toml or
virtualenv needed. The tframetest binary shipped alongside it in this
bundle always takes precedence over any system-installed tframetest.

License and provenance
-----------------------
tframetest is licensed GNU General Public License v2.0 or later.
Upstream project: https://github.com/tuxera/tframetest

This bundle's tframetest binary is built from the upstream git tag
3025.12.0 (https://github.com/tuxera/tframetest, tag 3025.12.0) with the
following patch(es) applied:
${patch_note}

Patch source and full corresponding source availability (GPLv2 Section 3)
are published in this project's repository:
    https://github.com/dmcp718/tf-benchmark

The complete GPL-2.0-or-later license text is included as COPYING in
this bundle.
EOF
}

build_macos_bundle() {
    local platform="macos-arm64"
    local zip_name="tfbench-${VERSION}-${platform}.zip"
    local stage
    stage="$(mktemp -d)"
    trap 'rm -rf "$stage"' RETURN

    cp "$REPO_DIR/tfbench.py" "$stage/"
    cp "$REPO_DIR/tframetest-macos" "$stage/"
    if [[ -n "$CODESIGN_IDENTITY" ]]; then
        codesign -f --timestamp --options runtime -s "$CODESIGN_IDENTITY" "$stage/tframetest-macos"
    fi
    cp "$REPO_DIR/COPYING" "$stage/"
    write_bundle_readme "$stage/BUNDLE-README.txt" \
"  - patches/macos-f_nocache.patch (Darwin-only direct I/O fix)
  - patches/random-fill.patch (incompressible frame fill, platform-neutral)"

    rm -f "$DIST_DIR/$zip_name"
    (cd "$stage" && zip -q -X "$DIST_DIR/$zip_name" tfbench.py tframetest-macos COPYING BUNDLE-README.txt)
    echo "built: dist/$zip_name"

    if [[ "$NOTARIZE" == "1" ]]; then
        echo "Submitting dist/$zip_name to Apple notary service (profile: $NOTARY_PROFILE) ..."
        xcrun notarytool submit "$DIST_DIR/$zip_name" \
            --keychain-profile "$NOTARY_PROFILE" --wait
        echo "notarized: dist/$zip_name"
    fi
}

build_linux_bundle() {
    if [[ ! -f "$LINUX_BINARY" ]]; then
        echo "skipped: Linux bundle (no binary at build/tframetest-linux-x86_64 -- see linux-builders/)"
        return
    fi

    local platform="linux-x86_64"
    local zip_name="tfbench-${VERSION}-${platform}.zip"
    local stage
    stage="$(mktemp -d)"
    trap 'rm -rf "$stage"' RETURN

    # The Linux binary is a prebuilt artifact this script cannot validate
    # against a patch set -- surface its identity so a stale build from an
    # older tag/patch set can't ship unnoticed under a fresh BUNDLE-README.
    echo "linux binary: $(shasum -a 256 "$LINUX_BINARY" | awk '{print $1}')"
    echo "linux binary mtime: $(date -r "$LINUX_BINARY" '+%Y-%m-%d %H:%M:%S' 2>/dev/null || stat -c '%y' "$LINUX_BINARY")"
    echo "verify this is a current build from linux-builders/ before distributing"

    cp "$REPO_DIR/tfbench.py" "$stage/"
    # Must be named plain "tframetest" -- tfbench's non-Darwin/Windows
    # discovery path only checks the script dir for that exact name.
    cp "$LINUX_BINARY" "$stage/tframetest"
    chmod 755 "$stage/tframetest"
    cp "$REPO_DIR/COPYING" "$stage/"
    write_bundle_readme "$stage/BUNDLE-README.txt" \
"  - patches/random-fill.patch (incompressible frame fill, platform-neutral)"

    rm -f "$DIST_DIR/$zip_name"
    (cd "$stage" && zip -q -X "$DIST_DIR/$zip_name" tfbench.py tframetest COPYING BUNDLE-README.txt)
    echo "built: dist/$zip_name"
}

build_macos_bundle
build_linux_bundle
