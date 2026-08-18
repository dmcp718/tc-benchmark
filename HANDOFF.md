# HANDOFF — tc-benchmark

Last updated: 2026-08-18

## What this repo is

Portable packaging of [tframetest](https://github.com/tuxera/tframetest) (media-frame
storage benchmark, GPL-2.0+) plus **tfbench.py**, a Rich TUI wrapper that runs the
suite (1 write + N reads), visualizes results, flags cache-distorted numbers, and —
via `--flush-cmd` — measures true end-to-end write throughput on write-back cloud
filesystems.

## Current state (2026-08-18)

All work below is committed and pushed to **both** remotes:

- `origin` → git@bitbucket.org:lucidlink/tc-benchmark.git (master)
- `github` → https://github.com/dmcp718/tf-benchmark (master, force-unified with
  Bitbucket history on 2026-08-18; the old GitHub fork's unique AL2023 docs were
  ported first, its other commits were superseded)

### Shipped this cycle (newest first)

1. **`b5a2086` Genericize + usage/--help overhaul**
   - All LucidLink/vendor specifics removed from tfbench.py and docs. Flush
     measurement is now the opt-in generic `--flush-cmd CMD`: a shell command
     whose **last stdout line** is the bytes still queued for upload (`0`,
     `12345`, `4.51MiB`, `1.2 GB`; binary + decimal units). Polled every 2s
     after the write test until zero; failures warn and omit metrics (never
     false zeros). `--no-flush` removed (flush is opt-in now).
   - Migration for former LucidLink auto-detection users:
     `--flush-cmd "lucid cache | awk -F': ' '/Remaining upload/{print \$2}'"`
   - Help rebuilt: grouped options, uniform metavars, `--version` (prints the
     resolved tframetest binary path + version — use this to catch stale
     installs), `--parse`+target_dir now errors, `--flush-timeout` validated.
2. **`78b42b5` / `edbebda`** — README fixes (AL2023/EC2 docs ported from GitHub
   fork, package sizes, per-platform build dates, 3-reads default).
3. **`6d7b85a` Honest benchmarks on compressed write-back storage** (the big one):
   - `patches/random-fill.patch` — upstream fills frames with one repeated byte
     (`memset 't'`), which lz4-compressed filesystems collapse ~450:1, so
     benchmarks measured the compression pipeline. Now xorshift64 random fill.
     Patch includes upstream test-assertion fixes. Applied to macOS binary +
     wired into `linux-builders/` (.rpm/.deb). **Windows zip NOT yet rebuilt**
     (bead tcb-0is).
   - tfbench flush-aware write measurement, `--link-speed` local-cache flagging
     (RAM heuristic always runs, takes precedence), neutral read labels,
     `--binary`/`TFBENCH_BINARY` override, 80-col-safe rendering, CSV columns
     appended backward-compatibly.
4. **`f5be1b6` F_NOCACHE patch** — `patches/macos-f_nocache.patch`: upstream
   silently no-ops O_DIRECT on macOS ("Faking O_DIRECT for now" in platform.c);
   patch adds `fcntl(fd, F_NOCACHE, 1)` in `generic_open()`. Darwin-only.

### Reference numbers (validated live on a 1 GiB-cache, lz4, ~1 Gbps-ISP cloud FS)

| Measurement | Before fixes | After fixes |
|---|---|---|
| Reads (compressible, cached) | 61–77 **GB**/s (RAM cache) | flat ~760–775 MiB/s, flagged |
| Write, reported | 369 MiB/s | ~136 MiB/s ingest, flagged |
| Write, end-to-end (flush) | not measured | **~20–38 MiB/s** (network-bound) |
| Upload queued per 2 GiB written | 4.5 MiB (450:1 lz4) | ~100% of logical bytes |

## Open work (beads — `bd list`, `bd show <id>`)

- **tcb-dws [epic] Self-contained portable packaging** — Tiers 1 & 2 done
  2026-08-18 (see "Portable packaging (2026-08-18)" below), epic stays open
  because tcb-bku (Tier 3) is deliberately deferred:
  - ~~tcb-djq~~ (P1, CLOSED) Binary discovery order fixed — bundle/script dir
    now wins over `/usr/local/bin`/PATH.
  - ~~tcb-2gr~~ (P1, CLOSED) Tier 1: PEP 723 header + per-platform zips, on a
    draft GitHub release.
  - ~~tcb-tgp~~ (P2, CLOSED) Tier 2: PyInstaller onefile executables, macOS
    arm64 **and** Linux x86-64 both built and verified zero-prerequisite.
  - **tcb-bku (P3, OPEN, deliberately deferred)** Tier 3: PyPI platform wheels
    → `uvx tfbench`. Only worth doing if the tool goes properly public with a
    release cadence — not started.
- **tcb-0is (P2)** Rebuild `tframetest-3025.12.0-win64.zip` with
  `patches/random-fill.patch` (NOT f_nocache — Windows already maps DIRECT to
  FILE_FLAG_NO_BUFFERING). Also fix the download-table size in README while
  replacing the zip. Windows exe was last built natively Feb 2026 (commit
  0defeb1) pre-patch, so it still writes compressible frames. Also blocks a
  Windows entry in the new portable-packaging release (no patched win64
  `tframetest.exe`, no Windows build box available yet).

### Portable packaging (2026-08-18) — committed on `master`

tfbench can now be run without cloning this repo. tcb-djq/tcb-2gr/tcb-tgp closed;
full verification evidence is in each bead's close reason (`bd show <id>`).

- **tfbench.py**: `_find_tframetest()` reordered so the script/bundle directory
  binary always wins over `/usr/local/bin`, PATH, and the installer prompt
  (only `--binary`/`TFBENCH_BINARY` outrank it). Added `sys._MEIPASS` handling
  for PyInstaller frozen builds. Added a PEP 723 inline metadata header
  (`requires-python >=3.10`, `rich>=13.7.0`) so `uv run tfbench.py` works with
  zero repo/pyproject/venv.
- **scripts/make-bundles.sh** (Tier 1): builds `dist/tfbench-<version>-macos-arm64.zip`
  and `dist/tfbench-<version>-linux-x86_64.zip` — each is `tfbench.py` + the
  platform `tframetest` binary + `COPYING` + a generated `BUNDLE-README.txt`
  with GPL provenance. The Linux binary must exist first at
  `build/tframetest-linux-x86_64` (gitignored build artifact — not checked in).
- **scripts/build-onefile.sh** (Tier 2): builds a zero-prerequisite PyInstaller
  onefile executable, `dist/tfbench-<version>-<platform>`. Auto-detects OS,
  falls back from `uv`/`uvx` to plain `pip install pyinstaller rich` when `uv`
  isn't on PATH (needed inside the bare Docker build image). macOS build is
  ad-hoc codesigned.
- **Linux binary provenance for this cycle**: built via
  `linux-builders/Dockerfile.rpm`'s AlmaLinux 9 image, using **Podman**
  (`podman build`/`podman run --platform linux/amd64`; podman-machine-default
  was already running, applehv backend) — the user's stated preference over
  Docker Desktop, which was tried first and abandoned mid-task once corrected.
  Both `linux-builders/build-rpm.sh` and `build-deb.sh` were genericized to
  honor `CONTAINER_ENGINE=${CONTAINER_ENGINE:-docker}` so either engine works
  (`CONTAINER_ENGINE=podman ./build-rpm.sh <version>`); the Dockerfiles are
  unchanged and OCI-portable. `--platform linux/amd64` is required either way
  — this Mac's container engines default to host arch (arm64), which silently
  produces the wrong architecture (caught once via `file` on a mislabeled
  ARM64 ELF). Needed `dnf config-manager --set-enabled crb && dnf install -y
  glibc-static` for `-static -pthread` to link; only `patches/random-fill.patch`
  applied (f_nocache is Darwin-only), matching the existing README provenance
  table. Output at `build/tframetest-linux-x86_64` (gitignored) — rebuilding
  under Podman reproduced the byte-identical binary (same BuildID) as the
  earlier Docker build.
- **Linux onefile build note**: building the PyInstaller onefile inside
  `python:3.12-slim` failed at runtime (`GLIBC_2.38' not found`) against an
  older glibc target (`debian:bookworm-slim`) — that base image tracks a
  newer glibc than expected. Switched to building inside the same AlmaLinux 9
  image as the Tier-1 binary (older glibc, `dnf install -y python3
  python3-pip binutils`; PyInstaller needs `objdump` from `binutils`, not
  present in `python:3.12-slim` either). Lesson: always build onefile
  executables in the *oldest* glibc environment you intend to support, not
  whatever has Python preinstalled.
- **GitHub release**: `v1.0.0` on `dmcp718/tf-benchmark` — **PUBLISHED**
  2026-08-18 (user published it; the GitHub repo was also renamed
  tc-benchmark → tf-benchmark that day; old URLs redirect; Bitbucket keeps
  the tc-benchmark name). Tag `v1.0.0` = commit 8b9e12c, the exact revision
  all assets were built from. Five assets: both zips, both onefile
  executables, COPYING.
  https://github.com/dmcp718/tf-benchmark/releases/tag/v1.0.0
- **macOS signing/notarization (2026-08-18)**: both macOS assets are
  Developer ID-signed (identity "DAVID MCKEEN PHILLIPS (53R5U5WLK4)") and
  notarized (Apple status: Accepted × 2) — browser downloads run without
  quarantine workarounds. Wired into both scripts behind
  `CODESIGN_IDENTITY=... NOTARIZE=1` (notary keychain profile: `notarytool`,
  entitlements in scripts/entitlements.plist — PyInstaller needs
  allow-unsigned-executable-memory + disable-library-validation under the
  hardened runtime). The checked-in tframetest-macos stays ad-hoc for
  bit-reproducibility; only the STAGED copies get the real signature.
  Gotchas: bare Mach-O binaries can't be stapled (Gatekeeper fetches the
  ticket online on first run), and `spctl -t execute` reports "does not
  seem to be an app" for notarized CLI binaries — notarytool's Accepted is
  the authoritative gate; verify by exec'ing a quarantined copy.
- **README**: added "Portable install (no clone required)" and "Binary
  Discovery" sections under the tfbench heading.
- **.gitignore**: added `*.spec` (PyInstaller-generated specs); `build/` and
  `dist/` were already ignored.
- **Not done / explicitly out of scope this cycle**:
  - Windows portable artifacts (zip or onefile) — blocked on tcb-0is, no
    Windows build box here. Manual commands documented in
    `scripts/build-onefile.sh`'s header for whenever that's unblocked.
  - tcb-bku (PyPI/Tier 3) — left untouched per instruction, deliberately
    deferred.
  - `dist/` and `build/` artifacts are gitignored — the Linux binary and all
    release artifacts exist locally and on the draft release, not in git.

### Opus review round (2026-08-18, post-implementation)

All original claims verified PASS (including independent gzip-expansion proof
that BOTH shipped binaries carry random-fill). Fixes applied from findings:
- Linux **onefile requires glibc >= 2.33** (embedded CPython from AlmaLinux 9)
  — fails on RHEL/Rocky 8, Ubuntu 20.04, Debian 11. Release body + README now
  state the floor and steer older distros to the zip (verified working on
  Ubuntu 20.04: static tframetest + uv-provided Python = no floor).
- Discovery now requires the exec bit on script-dir binaries (os.access X_OK)
  so a bundle copy that lost it falls back to system locations instead of
  dying EACCES.
- Stale README macOS auto-installer-prompt claims rewritten (prompt is dead
  in-repo since tframetest-macos sits next to tfbench.py and wins first).
- make-bundles.sh prints the Linux binary's sha256+mtime (staleness guard);
  BUNDLE-README names the upstream tag explicitly; COPYING attached as a
  fifth release asset; .gitignore *.spec anchored to /build/.
- PEP 723 header carries a sync-with-pyproject NOTE (uv prefers the header
  over pyproject even in-repo — contributor trap otherwise).

## Gotchas / hard-won facts

- **Reproducing the binaries**: `git clone --branch 3025.12.0 --depth 1` upstream,
  `git apply` both patches, `make release`. Shipped macOS binaries are
  bit-identical to this recipe (verified twice by independent rebuild).
- **`make test` cannot link on macOS** (Apple ld lacks `--wrap`) — pre-existing
  upstream issue, not a patch regression. test_frame.c hunks in the patch keep
  Linux `make test` green.
- **Do not stamp per-frame markers into the frame buffer** (dedup idea):
  upstream shares ONE frame_t across all worker threads unsynchronized —
  stamping in the write path is a data race. Documented in README; frames are
  mutually identical (defeats compression, not cross-file dedup).
- **flush-cmd contract**: last non-empty stdout line only; prose lines like
  `Remaining upload: 5MiB` are rejected by design — pipe through awk/grep.
- **When benchmarking a cloud FS**: always pass `--link-speed <Mbps>` and, for
  writes, `--flush-cmd`; otherwise you're measuring the local cache. Frames just
  written are warm everywhere — read passes show repeatability, not cold reads.
- **`tfbench.py --version`** shows which tframetest binary will actually run.
  On macOS `/usr/local/bin` wins until tcb-djq lands — after rebuilding, rerun
  the `.pkg` installer or the old binary keeps being used.
- Local install on this Mac: `/usr/local/bin/tframetest` = F_NOCACHE+random-fill
  build (installed from the rebuilt .pkg 2026-08-18).
- `.DS_Store` files are untracked and NOT gitignored — avoid `git add -A`.
- GitHub pushes: `git push github master` (remote already configured; gh auth
  as dmcp718).

## Process notes

- Multi-agent pattern used this cycle: Sonnet agent implements per beads, Opus
  agent adversarially reviews (2 rounds + confirmation pass), main session
  triages findings and commits after an explicit COMMIT verdict. Worked well.
- Live verification target used previously: a LucidLink filespace mount (any
  cloud FS mount works now via --flush-cmd). Always clean up `frame*.tst` after
  the upload queue reports zero, never mid-drain.
- No AI attribution in commit messages (repo owner's standing rule).
