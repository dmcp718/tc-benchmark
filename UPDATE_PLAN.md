# Update tframetest to 3025.12.0 and Add Linux Build Scripts

## Context
The tc-benchmark repo bundles tframetest binaries (currently 3025.10.2, docs say 3025.1.1). The upstream repo (github.com/tuxera/tframetest) has released **3025.12.0**. macOS has a build script but Linux has none. macOS binary can be built locally (ARM64), but Windows and Linux x86_64 binaries need an x86_64 machine.

## Repo: `/Users/davidphillips/Cursor_projects/tc-benchmark-bitbucket/tc-benchmark`

## What we do now (on this Mac)

### 1. Build macOS ARM64 binary from source
- Clone upstream tframetest repo
- `make release` (native ARM64)
- Replace `tframetest-macos` in repo root
- Replace `macos-installer/payload/usr/local/bin/tframetest`
- Rebuild macOS installer package

### 2. Download Windows binary from GitHub release
- Download `tframetest-win-x86_64-w64-mingw32-3025.12.0.zip` from GitHub release
- Save as `tframetest-3025.12.0-win64.zip` in repo root
- Delete old `tframetest-3025.10.2-win64.zip`

### 3. Create Linux build scripts (to run on x86_64 machine)

**`linux-builders/build-deb.sh`** — Builds .deb in Ubuntu 22.04 Docker container:
- Clone tframetest from GitHub, `make release`
- Package with `dpkg-deb` → output .deb to repo root

**`linux-builders/build-rpm.sh`** — Builds .rpm in AlmaLinux 9 Docker container:
- Clone tframetest from GitHub, `make release`
- Package with `rpmbuild` → output .rpm to repo root

Both take version as parameter, require only Docker.

### 4. Update all version references (3025.1.1 and 3025.10.2 → 3025.12.0)

**Files to update:**
- `tfbench.py` — installer pkg path (line 195)
- `README.md` — version string, package filenames, install commands
- `TFBENCH_EXAMPLES.md` — install commands
- `macos-installer/build-installer.sh` — VERSION variable
- `macos-installer/Distribution.xml` — title and pkg-ref version
- `macos-installer/welcome.txt` — version string
- `macos-installer/readme.txt` — version string, filenames
- `macos-installer/README.md` — version string, filenames

### 5. Delete old binaries
- `tframetest-3025.10.2-win64.zip`
- `tframetest_3025.10.2_amd64.deb`
- `tframetest-3025.10.2-1.el9.x86_64.rpm`

## What you do later (on x86_64 machine)
- Run `linux-builders/build-deb.sh 3025.12.0` → produces `tframetest_3025.12.0_amd64.deb`
- Run `linux-builders/build-rpm.sh 3025.12.0` → produces `tframetest-3025.12.0-1.el9.x86_64.rpm`
- Commit the new .deb and .rpm to the repo

## Files to create
- `linux-builders/build-deb.sh`
- `linux-builders/build-rpm.sh`
- `linux-builders/Dockerfile.deb`
- `linux-builders/Dockerfile.rpm`

## Verification
1. `./tframetest-macos --version` → 3025.12.0
2. `grep -r "3025.10.2\|3025.1.1" . --include="*.py" --include="*.md" --include="*.sh" --include="*.xml" --include="*.txt"` → no matches
3. Linux build scripts run on x86_64 machine with Docker
