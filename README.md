# tframetest - Static Binary Packages

Static binary packages of [tframetest](https://github.com/tuxera/tframetest), a tool to test and benchmark writing/reading media frames to/from disk.

## Package Information

**Version:** 3025.1.1
**Build Type:** Static (no external dependencies)
**Architecture:** x86-64
**Minimum Kernel:** Linux 3.2.0+

### Available Packages

| Package          | File                                        | Size | Target Systems                     |
|------------------|---------------------------------------------|------|------------------------------------|
| Debian/Ubuntu    | `tframetest_3025.1.1_amd64.deb`             | 322K | Debian, Ubuntu, derivatives        |
| EL9 RPM          | `tframetest-3025.1.1-1.el9.x86_64.rpm`      | 354K | RHEL 9, Rocky Linux 9, AlmaLinux 9 |
| Windows 64-bit   | `tframetest-3025.1.1-win64.zip`             | 219K | Windows 10/11, Server 2016+        |

## Installation

### Debian/Ubuntu
```bash
sudo dpkg -i tframetest_3025.1.1_amd64.deb
```

### RHEL/Rocky/AlmaLinux 9
```bash
sudo rpm -ivh tframetest-3025.1.1-1.el9.x86_64.rpm
```

### Windows 10/11
```powershell
# Extract the ZIP file
Expand-Archive tframetest-3025.1.1-win64.zip

# Add to PATH or run directly
cd tframetest-win-x86_64-w64-mingw32-3025.1.1
.\tframetest.exe --version
```

### Verification
```bash
tframetest --version
# Output: tframetest 3025.1.1
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

- `-w SIZE` - Write mode with frame size (e.g., 2k, 4k, 1m)
- `-r` - Read mode
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

## tfbench - TUI Benchmark Visualizer

This repository includes **tfbench**, a TUI (Terminal User Interface) tool that runs tframetest benchmarks and displays beautiful visual results using Rich.

**⚠️ Note:** `tfbench.py` is for **Linux/macOS only**. Windows users can use tframetest.exe directly from the command line.

### Features

- 🎨 **Rich TUI visualizations** - Bar charts, tables, and sparklines
- 📊 **Comprehensive metrics** - Throughput, latency, FPS comparisons
- 🔍 **Performance insights** - Automatic calculation of cache speedup and ratios
- 🚀 **Automated testing** - Runs full benchmark suite (1 write + 2 reads)
- ⚡ **Real-time progress** - Live progress indicators during test execution
- 💾 **CSV export** - Export results for analysis in Excel/pandas

### Installation

**Linux/macOS:**
```bash
# Requires uv (https://github.com/astral-sh/uv)
# If you don't have uv installed:
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Quick Start

```bash
# Run full benchmark suite with visual output
uv run tfbench.py -w 4k -n 500 -t 8 /media/tc-mngr/tftest

# Run with CSV export
uv run tfbench.py -w 4k -n 500 -t 8 /mnt/storage --csv results.csv

# Custom configuration with more read iterations
uv run tfbench.py -w 4k -n 500 -t 8 /mnt/storage --reads 4

# Larger test with extended timeout (for slow storage)
uv run tfbench.py -w 4k -n 2000 -t 16 /mnt/storage --timeout 3600
```

### tfbench Options

```
Options:
  -w, --write-size SIZE    Frame size (default: 4k)
  -n, --frames COUNT       Number of frames (default: 500)
  -t, --threads COUNT      Number of threads (default: 8)
  --reads COUNT            Number of read tests (default: 2)
  --timeout SECONDS        Timeout per test in seconds (default: 1800 = 30 min)
  --csv FILE               Export results to CSV file
  --parse FILE             Parse existing tframetest output (coming soon)
  target_dir               Target directory for tests
```

### Output Example

tfbench displays:

1. **Throughput Comparison** - Visual bar chart comparing write and read performance
2. **Performance Insights** - Comprehensive stats including:
   - **Write Performance**: Throughput, latency (min/avg/max), total time
   - **Read Performance**: Cache speedup, read/write ratios, per-read stats
   - Shows all individual read test results with cache indicators
3. **Latency Statistics** - Min/avg/max/range completion times in clear table format
4. **Detailed Statistics** - Complete table with all metrics

The tool automatically detects cache behavior (cold vs warm cache) and calculates performance ratios. Write statistics are prominently displayed to help characterize deployment environment storage performance.

### CSV Export

tfbench can export results to CSV format for further analysis or integration with other tools:

```bash
uv run tfbench.py -w 4k -n 500 -t 8 /mnt/storage --csv results.csv
```

**CSV format includes:**
- Metadata: timestamp, target directory, frame size, threads
- Detailed results: All metrics for each test (write/read)
- Performance insights: Cache speedup, read/write ratios, latency improvements
- All timing data in both nanoseconds and seconds

### Use Cases

- **Storage benchmarking** - Compare different storage devices
- **Cache analysis** - Visualize caching effects on read performance
- **Performance regression testing** - Track performance over time
- **Media workflow validation** - Ensure adequate I/O performance

## Technical Details

### Static Linking
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
- Build Date: October 5, 2025

## Uninstallation

### Debian/Ubuntu
```bash
sudo dpkg -r tframetest
```

### RHEL/Rocky/AlmaLinux 9
```bash
sudo rpm -e tframetest
```
