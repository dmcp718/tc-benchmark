# tframetest - Static Binary Packages

Static binary packages of [tframetest](https://github.com/tuxera/tframetest), a tool to test and benchmark writing/reading media frames to/from disk.

## Package Information

**Version:** 3025.12.0
**Build Type:** Static (no external dependencies)
**Architecture:** x86-64
**Minimum Kernel:** Linux 3.2.0+

### Available Packages

| Package          | File                                        | Size | Target Systems                     |
|------------------|---------------------------------------------|------|------------------------------------|
| **macOS ARM64**  | `tframetest-3025.12.0-macos-arm64.pkg`       | 17K  | macOS 10.13+, Apple Silicon (M1/M2/M3) |
| Debian/Ubuntu    | `tframetest_3025.12.0_amd64.deb`             | 322K | Debian, Ubuntu, derivatives        |
| EL9 RPM          | `tframetest-3025.12.0-1.el9.x86_64.rpm`      | 354K | RHEL 9, Rocky Linux 9, AlmaLinux 9 |
| Windows 64-bit   | `tframetest-3025.12.0-win64.zip`             | 53K  | Windows 10/11, Server 2016+        |

## Installation

### macOS (Apple Silicon - M1/M2/M3)

**GUI Installation (Recommended):**
```bash
# Double-click the .pkg file in Finder
open macos-installer/build/tframetest-3025.12.0-macos-arm64.pkg
```

**Command-Line Installation:**
```bash
sudo installer -pkg macos-installer/build/tframetest-3025.12.0-macos-arm64.pkg -target /
```

**Building the Installer:**
```bash
cd macos-installer
./build-installer.sh
```

The installer places `tframetest` in `/usr/local/bin/` for system-wide access.

**Auto-Installation via tfbench.py:**
If tfbench.py finds no binary next to itself (see "Binary Discovery" below), no
system install, and nothing on PATH — but a built installer package is present
at `macos-installer/build/` — it offers to run the installer interactively.
In a normal checkout of this repo this never triggers, because the repo ships
`tframetest-macos` alongside tfbench.py and that is found first.

### Debian/Ubuntu
```bash
sudo dpkg -i tframetest_3025.12.0_amd64.deb
```

### RHEL/Rocky/AlmaLinux 9 / Amazon Linux 2023
```bash
sudo rpm -ivh tframetest-3025.12.0-1.el9.x86_64.rpm
```

**Note for Amazon Linux 2023:** The EL9 RPM is fully compatible with Amazon Linux 2023.

### Windows 10/11
```powershell
# Extract the ZIP file
Expand-Archive tframetest-3025.12.0-win64.zip

# Add to PATH or run directly
cd tframetest-win-x86_64-w64-mingw32-3025.12.0
.\tframetest.exe --version
```

### Verification
```bash
tframetest --version
# Output: tframetest 3025.12.0
```

## Usage

### Basic Workflow

**1. Write frames to disk:**
```bash
mkdir test_directory
tframetest -w 2k -n 1000 -t 4 test_directory
```

**2. Read frames back:**
```bash
tframetest -r -n 1000 -t 4 test_directory
```

### Command Options

- `-w SIZE` - Write mode with frame size (e.g., 2k, 4k, 8k)
- `-r` - Read mode
- `-s FILE` - Streaming mode: write/read frames to a single file
- `-z SIZE` - Frame size in bytes (required for streaming mode)
- `-n COUNT` - Number of frames to write/read
- `-t THREADS` - Number of threads to use
- `-l` - List available profiles
- `--help` - Display all available options

### Available Profiles

tframetest includes predefined profiles for common media frame formats:

| Profile            | Resolution    | Bit Depth | Compression | Frame Size  |
|--------------------|---------------|-----------|-------------|-------------|
| SD-32bit-cmp       | 720x576       | 32-bit    | Yes         | ~1.6 MiB    |
| SD-24bit           | 720x576       | 24-bit    | No          | ~1.2 MiB    |
| SD-16bit           | 720x576       | 16-bit    | No          | ~0.8 MiB    |
| HD-32bit-cmp       | 1280x720      | 32-bit    | Yes         | ~3.5 MiB    |
| HD-24bit           | 1280x720      | 24-bit    | No          | ~2.6 MiB    |
| FULLHD-32bit-cmp   | 1920x1080     | 32-bit    | Yes         | ~7.9 MiB    |
| FULLHD-24bit       | 1920x1080     | 24-bit    | No          | ~5.9 MiB    |
| 2K-32bit-cmp       | 2048x1080     | 32-bit    | Yes         | ~8.4 MiB    |
| 2K-24bit           | 2048x1080     | 24-bit    | No          | ~6.3 MiB    |
| 4K-32bit-cmp       | 4096x2160     | 32-bit    | Yes         | ~33.6 MiB   |
| 4K-24bit           | 4096x2160     | 24-bit    | No          | ~25.2 MiB   |
| 8K-32bit-cmp       | 7680x4320     | 32-bit    | Yes         | ~126.2 MiB  |
| 8K-24bit           | 7680x4320     | 24-bit    | No          | ~94.7 MiB   |

**Usage:**
```bash
# List all available profiles
tframetest -l

# Use a specific profile
tframetest -w 4K-32bit-cmp -n 100 -t 8 /mnt/storage

# Or use custom sizes
tframetest -w 4k -n 100 -t 8 /mnt/storage
```

### Example: Performance Testing

```bash
# Create test directory
mkdir -p /mnt/storage/frametest

# Write 10,000 4KB frames with 8 threads
tframetest -w 4k -n 10000 -t 8 /mnt/storage/frametest

# Read them back and measure performance
tframetest -r -n 10000 -t 8 /mnt/storage/frametest
```

### Streaming Mode

Streaming mode (`-s`) writes/reads frames to a single file instead of individual files per frame. Use `-z` to specify the frame size in bytes and `-s` to specify the target file.

```bash
# Write 100 frames of 4 MB each to a single file
tframetest -w -z 4194304 -s /mnt/storage/stream_test.bin -n 100 -t 1

# Read them back
tframetest -r -z 4194304 -s /mnt/storage/stream_test.bin -n 100 -t 1
```

### Windows Examples

```powershell
# Multi-file write/read (uses FILE_FLAG_NO_BUFFERING to bypass RAM cache)
.\tframetest.exe -w 4k -n 500 -t 4 D:\benchmarks
.\tframetest.exe -r -n 500 -t 4 D:\benchmarks

# Streaming write/read to a single file
.\tframetest.exe -w -z 4194304 -s D:\benchmarks\stream_test.bin -n 100 -t 1
.\tframetest.exe -r -z 4194304 -s D:\benchmarks\stream_test.bin -n 100 -t 1

# List available profiles
.\tframetest.exe -l
```

## tfbench - TUI Benchmark Visualizer

This repository includes **tfbench**, a TUI (Terminal User Interface) tool that runs tframetest benchmarks and displays visual results using Rich.

**⚠️ Note:** `tfbench.py` is for **Linux/macOS only**. Windows users can use tframetest.exe directly from the command line.

**🍎 macOS Users:** in this repo (and in the release bundles) tfbench.py runs the `tframetest-macos` binary sitting next to it — no installation needed. See "Binary Discovery" below for the full lookup order.

### Portable install (no clone required)

You don't need to clone this repo to use tfbench. Grab a per-platform bundle from
[GitHub Releases](https://github.com/dmcp718/tf-benchmark/releases), which pairs `tfbench.py`
with the matching `tframetest` binary so `uv run` needs nothing else:

```bash
# 1. Install uv (one-time), if you don't have it already
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Download and unzip the bundle for your platform, then run
unzip tfbench-1.0.0-macos-arm64.zip -d tfbench && cd tfbench
uv run tfbench.py --version
uv run tfbench.py -w 4k -n 500 -t 8 /path/to/target
```

`tfbench.py` carries a [PEP 723](https://peps.python.org/pep-0723/) inline metadata header, so
`uv run` resolves its one dependency (`rich`) automatically — no `pyproject.toml` or virtualenv
needed. See "Binary Discovery" below for why the binary shipped in the bundle always wins over
any system-installed `tframetest`.

The releases also carry single-file executables (`tfbench-<version>-<platform>`) that need
neither uv nor Python. Note the **Linux single-file executable requires glibc >= 2.33**
(RHEL/Rocky 9+, Ubuntu 22.04+, Debian 12+) because of the CPython runtime embedded at build
time; on older distros use the zip instead — its `tframetest` binary is fully static and uv
brings its own Python, so the zip has no glibc floor.

### Features

- 🎨 **Rich TUI visualizations** - Bar charts, tables, and sparklines
- 📊 **Comprehensive metrics** - Throughput, latency, FPS comparisons
- 🔍 **Performance insights** - Automatic calculation of cache speedup and ratios
- 🚀 **Automated testing** - Runs full benchmark suite (1 write + N reads, default 3)
- ⚡ **Real-time progress** - Live progress indicators during test execution
- 💾 **CSV export** - Export results for analysis in Excel/pandas

### Installation

**Linux/macOS:**
```bash
# Requires uv (https://github.com/astral-sh/uv)
# If you don't have uv installed:
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Amazon Linux 2023 (AWS EC2):**

When deployed via AWS deployment automation that pre-installs tfbench and its dependencies, access your instance via SSM Session Manager:

```bash
# Connect to instance
aws ssm start-session --target i-xxxxxxxxxxxxx --region us-east-1

# Run benchmarks (virtual environment is pre-configured)
tfbench -w 4k -n 500 -t 8 /cache/disk1
```

**Manual setup on Amazon Linux 2023:**
```bash
# Install uv system-wide
sudo bash -c 'curl -LsSf https://astral.sh/uv/install.sh | env INSTALLER_NO_MODIFY_PATH=1 sh && \
  mv /root/.local/bin/uv /usr/local/bin/uv && \
  mv /root/.local/bin/uvx /usr/local/bin/uvx'

# Create virtual environment and install dependencies
sudo bash -c 'cd /opt/tfbench && uv venv .venv && \
  uv pip install -r <(echo "rich>=13.7.0") && \
  chmod -R 755 .venv'

# Run tfbench (requires sudo if .venv not pre-created)
cd /opt/tfbench && sudo uv run tfbench.py -w 4k -n 500 -t 8 /cache/disk1
```

### Quick Start

```bash
# Run full benchmark suite with visual output
uv run tfbench.py -w 4k -n 500 -t 8 /media/tc-mngr/tftest

# Amazon Linux 2023 (if deployed via automation)
tfbench -w 4k -n 500 -t 8 /cache/disk1

# Run with CSV export
uv run tfbench.py -w 4k -n 500 -t 8 /mnt/storage --csv results.csv

# Custom configuration with more read iterations
uv run tfbench.py -w 4k -n 500 -t 8 /mnt/storage --reads 4

# Larger test with extended timeout (for slow storage)
uv run tfbench.py -w 4k -n 2000 -t 16 /mnt/storage --timeout 3600
```

### tfbench Options

```
positional arguments:
  target_dir               Directory to benchmark (required unless --parse or
                           --version is given)

options:
  --version                Show which tframetest binary would be used and its
                           version, then exit

benchmark options (run mode):
  -w, --write-size SIZE    Frame size (2k, 4k, 1m, ...) or a tframetest profile
                           name such as 4K-32bit-cmp (default: 4k)
  -n, --frames COUNT       Frames per test pass (default: 500)
  -t, --threads COUNT      Worker threads (default: 8); in --parse mode,
                           overrides the auto-detected thread count shown
  --reads COUNT            Read passes after the write pass (default: 3)
  --timeout SECONDS        Timeout per tframetest invocation (default: 1800)
  --binary PATH            tframetest binary to run instead of auto-discovery
                           (env: TFBENCH_BINARY)

upload flush (run mode):
  --flush-cmd CMD          Shell command polled after the write test; its last
                           stdout line must be the number of bytes still
                           queued for upload (bare bytes or with a unit: '0',
                           '12345', '4.51MiB', '1.2 GB'). Flush measurement
                           only runs when this is given
  --flush-timeout SECONDS  Max seconds to wait for the upload queue to drain
                           (default: 600); independent of --timeout

analysis and output:
  --link-speed MBPS        Link speed in Mbps (megabits/second, not MiB/s).
                           Reads/writes exceeding what the link could
                           physically deliver are flagged as served from a
                           local cache. The 10 GiB/s RAM-cache check (reads
                           only) always runs too and takes precedence
  --csv FILE               Export results (including flush metrics when
                           measured) to a CSV file

parse mode:
  --parse FILE             Visualize existing tframetest output instead of
                           running tests (mutually exclusive with target_dir);
                           only -t, --link-speed, and --csv apply
```

### Binary Discovery

`tfbench.py` picks a `tframetest` binary to run using this order, and stops at the
first match:

1. **`--binary PATH`** or the **`TFBENCH_BINARY`** environment variable, if given —
   an explicit override always wins and skips everything below.
2. **The bundle's own binary**, next to `tfbench.py` (or, in a PyInstaller onefile
   build, extracted alongside it at runtime): `tframetest-macos` or `tframetest` on
   macOS, `tframetest.exe` on Windows, `tframetest` elsewhere.
3. **`/usr/local/bin/tframetest`** (macOS only — the installer's target path).
4. Whatever `tframetest` resolves to on **`PATH`**.
5. On macOS, if a bundled installer `.pkg` is present, an interactive **prompt to
   install** it, then re-checking `/usr/local/bin`.
6. A bare `"tframetest"` fallback, which fails immediately if none of the above
   found anything.

This order is intentionally bundle-first: a portable zip or onefile executable
must always run the copy of `tframetest` it shipped with, never a stale or
differently-patched system install shadowing it. Use `--version` to see exactly
which binary and version would be used before running a real benchmark.

### Output Example

tfbench displays:

1. **Throughput Comparison** - Visual bar chart comparing write and read performance
2. **Performance Insights** - Comprehensive stats including:
   - **Write Performance**: Throughput, latency (min/avg/max), total time, and — with
     `--flush-cmd` — upload drain time and end-to-end (flushed) throughput
   - **Read Performance**: Read repeatability (Read #2 / Read #1), read/write ratios, per-read stats
   - Shows all individual read test results, flagged when their throughput
     exceeds a real disk/SSD/network (RAM cache, or `--link-speed` if given)
3. **Latency Statistics** - Min/avg/max/range completion times in clear table format
4. **Detailed Statistics** - Complete table with all metrics, including a Flag column
5. **Upload Flush Metrics** (with `--flush-cmd`) - Cache-ingest vs. end-to-end
   throughput, drain time, and peak queued upload

Read results are labeled neutrally (Read #1, #2, ...) — tfbench does not assume any read is
"cold": on cached cloud filesystems the files it just wrote are already warm in the local cache, so
consecutive reads mostly measure repeatability, not a cache warm-up effect. Results whose
throughput implausibly exceeds real storage or network capacity are flagged instead, either via
the 10 GiB/s RAM-cache heuristic or `--link-speed` if you know your link's real throughput.

### CSV Export

tfbench can export results to CSV format for further analysis or integration with other tools:

```bash
uv run tfbench.py -w 4k -n 500 -t 8 /mnt/storage --csv results.csv
```

**CSV format includes:**
- Metadata: timestamp, target directory, frame size, threads, link speed (if given)
- Detailed results: All metrics for each test (write/read), a `cache_flag` column, and
  flush columns (`drain_seconds`, `peak_remaining_upload_mib`, `end_to_end_mib_per_sec`)
  populated for the write row when `--flush-cmd` is given
- Performance insights: Read repeatability, read/write ratios, latency improvements
- All timing data in both nanoseconds and seconds

### Parsing Existing Output

tfbench can parse and visualize output from tframetest that was run separately:

```bash
# Run tframetest directly and save output
tframetest -w 4k -n 500 -t 8 /mnt/storage > results.txt
tframetest -r -n 500 -t 8 /mnt/storage >> results.txt
tframetest -r -n 500 -t 8 /mnt/storage >> results.txt

# Visualize the saved results
uv run tfbench.py --parse results.txt

# Parse and export to CSV
uv run tfbench.py --parse results.txt --csv analysis.csv
```

This is useful for:
- Analyzing results from tests run on remote machines
- Re-visualizing old benchmark results
- Processing output from automated test scripts

### Use Cases

- **Storage benchmarking** - Compare different storage devices
- **Cache analysis** - Visualize caching effects on read performance
- **Performance regression testing** - Track performance over time
- **Media workflow validation** - Ensure adequate I/O performance

## Technical Details

### Static Linking (.rpm/.deb tframetest packages)

The claims below apply to the **tframetest binaries** in the platform packages —
not to the tfbench single-file executables from GitHub Releases, which carry an
embedded CPython runtime with a glibc >= 2.33 floor on Linux (see "Portable
install" above).
Both packages contain **statically linked** binaries, meaning:
- ✓ No glibc version dependencies
- ✓ Portable across different Linux distributions
- ✓ No external library requirements
- ✓ Self-contained executable

### Portability
The static binaries will run on:
- Any x86-64 Linux system with kernel 3.2.0 or later
- Systems without matching glibc versions
- Minimal/container environments

## About tframetest

tframetest is an open-source replacement for the closed-source `frametest` tool, designed specifically for testing and benchmarking media frame I/O operations on storage devices.

**Use Cases:**
- Storage performance testing
- Media workflow validation
- I/O benchmarking
- Frame-based workload simulation

**License:** GNU General Public License v2.0 or later

**Original Project:** https://github.com/tuxera/tframetest

## Build Information

These packages were built with:
- Compiler: GCC (EL9)
- LDFLAGS: `-static -pthread`
- Optimization: `-O2`
- Build Dates: Linux packages October 5, 2025; Windows zip February 22, 2026
  (unpatched — see TODO below); macOS binary August 18, 2026 (both patches applied)

Patches are kept in `patches/` at the repo root:

| Patch | Scope | Applies to |
|---|---|---|
| `patches/macos-f_nocache.patch` | Darwin-only | macOS builds only |
| `patches/random-fill.patch` | Platform-neutral | macOS and Linux (.rpm/.deb) builds (Windows: not yet applied — see below) |

### macOS Direct I/O Patch (F_NOCACHE)

Upstream tframetest opens all test files with `PLATFORM_OPEN_DIRECT`, which maps
to `O_DIRECT` on Linux and `FILE_FLAG_NO_BUFFERING` on Windows — but is silently
a no-op on macOS (`/* Faking O_DIRECT for now... */` in `platform.c`), so reads
were served from the unified buffer cache and could report RAM speeds instead of
storage speeds.

The macOS binary in this repository is built with `patches/macos-f_nocache.patch`
applied, which implements direct I/O on Darwin via `fcntl(fd, F_NOCACHE, 1)` in
`generic_open()`. This patch is Darwin-only and is not applied on Linux/Windows
builds (`O_DIRECT`/`FILE_FLAG_NO_BUFFERING` already do the right thing there).

### Incompressible Frame Fill (random-fill)

Upstream tframetest fills every frame with a single repeated byte
(`frame_fill(res, 't')` in `frame.c`). On storage with transparent
compression — e.g. an lz4-compressed cloud filesystem — a 51 MB frame made
of one repeated byte compresses ~450:1, so benchmarks end up measuring the
compression pipeline instead of storage I/O (verified: writing frames to a
compressed cloud filesystem with a 1 GiB local cache queued only a few MiB
for upload, and reported write speed reflected cache-ingest, not the true
end-to-end rate).

This patch is platform-neutral (it only touches `frame.c`'s fill logic, not any
platform-specific I/O code) and is applied via `patches/random-fill.patch` to the
macOS binary and to Linux `.rpm`/`.deb` builds (`linux-builders/` applies it
automatically). **The shipped Windows binary
(`tframetest-3025.12.0-win64.zip`) has NOT yet been rebuilt with this patch** and
still writes compressible single-byte frames — TODO: rebuild it (mingw cross or
native) with `patches/random-fill.patch` applied. The patch
fills frames with fast pseudorandom data (xorshift64, 8 bytes/iteration, with
correct handling of the trailing bytes when frame size isn't a multiple of 8)
instead of a repeated byte. The `-e`/empty-frame profile is unaffected
(zero-size frames are always skipped). The patch also updates the upstream unit
test assertions in `tests/test_frame.c` that hard-coded the old `'t'`-fill byte,
so `make test` still passes on platforms where the test harness can link (macOS's
Apple `ld` doesn't support the `--wrap` flag the test harness uses, independent
of this patch).

**Known limitation:** within a single tframetest invocation, every frame file
written shares one in-memory buffer that upstream `frametest.c` allocates once
per run and reuses, unsynchronized, across all worker threads (see `opts->frm`
in `frametest.c` and its use in `tester_run_write()`/`tester_run_read()`). That
means all frame files produced by one run are byte-identical to each other. This
defeats transparent *compression* (the bug this patch fixes — lz4 etc. operate
within a single file/stream) but would **not** defeat a *deduplicating* backend
that recognizes identical content across files. Stamping a per-frame marker into
the write hot path (`tester_frame_write()` in `tester.c`) was considered but
rejected: that shared frame buffer is written by multiple threads concurrently
under `-t`/`--threads > 1` with no synchronization around it, so mutating its
content per-frame would race and could corrupt whichever frame(s) are mid-write
at the time. Fixing that properly needs per-thread frame buffers, which is a
larger change than this patch's scope.

To reproduce the macOS build with both patches:

```bash
git clone --branch 3025.12.0 --depth 1 https://github.com/tuxera/tframetest.git
cd tframetest
git apply ../patches/macos-f_nocache.patch
git apply ../patches/random-fill.patch
make release   # output: build/tframetest (arm64)
```

### Linux Build (.rpm / .deb)

`linux-builders/build-rpm.sh` and `linux-builders/build-deb.sh` clone the exact
tagged release inside a Docker container, apply `patches/random-fill.patch`
(bind-mounted into the container from the repo root), then `make release` and
package the result. They do **not** apply `patches/macos-f_nocache.patch` (it's
Darwin-only). To reproduce manually in the same environment as the container:

```bash
git clone --branch 3025.12.0 --depth 1 https://github.com/tuxera/tframetest.git
cd tframetest
git apply ../patches/random-fill.patch
make release   # output: build/tframetest
```

## Uninstallation

### macOS
```bash
sudo rm /usr/local/bin/tframetest
```

### Debian/Ubuntu
```bash
sudo dpkg -r tframetest
```

### RHEL/Rocky/AlmaLinux 9
```bash
sudo rpm -e tframetest
```
