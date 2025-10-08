# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This repository distributes **static binary packages** of tframetest, a tool for testing and benchmarking media frame I/O operations on storage devices. It is an open-source replacement for the closed-source `frametest` tool.

**Purpose:** Package distribution repository, not primary development
**Upstream:** https://github.com/tuxera/tframetest (included as git submodule)

## Repository Structure

- `tframetest/` - Git submodule pointing to upstream tframetest source
- `tframetest_3025.1.1_amd64.deb` - Static Debian/Ubuntu package
- `tframetest-3025.1.1-1.el9.x86_64.rpm` - Static RHEL 9/Rocky/AlmaLinux package
- `tfbench.py` - TUI benchmark visualizer (Python/Rich)
- `pyproject.toml` - Python project configuration for uv
- `README.md` - Package documentation and usage instructions

## Working with Submodule

Initialize/update the tframetest submodule:
```bash
git submodule update --init --recursive
```

The submodule contains the actual C source code for tframetest.

## Building tframetest from Source

Navigate to the submodule directory:
```bash
cd tframetest
```

Build commands:
```bash
# Standard build (creates build/tframetest)
make

# Release build (stripped binary)
make release

# Run tests
make test

# Code coverage report
make coverage

# Clean build artifacts
make clean

# Create source distribution tarball
make dist

# Windows builds (requires mingw-w64)
make win      # 32-bit
make win64    # 64-bit
```

## Creating Static Packages

The repository contains pre-built **static binaries** (no external dependencies). When creating new packages:

1. Build static binary in the tframetest submodule:
   ```bash
   cd tframetest
   LDFLAGS="-static -pthread" make release
   ```

2. The static binary at `build/tframetest` should be packaged for distribution

**Key requirements:**
- Use `-static` linker flag for portability
- Include `-pthread` for thread support
- Strip symbols with `strip` command or `make release`
- Target: x86-64 architecture, Linux kernel 3.2.0+

## Package Version

Current version: **3025.1.1**

Version numbers are defined in `tframetest/Makefile`:
- `MAJOR=3025`
- `MINOR=1`
- `PATCH=1`

## Testing Packages

After building/modifying packages, verify installation:

**Debian/Ubuntu:**
```bash
sudo dpkg -i tframetest_VERSION_amd64.deb
tframetest --version
```

**RHEL/Rocky/AlmaLinux:**
```bash
sudo rpm -ivh tframetest-VERSION.el9.x86_64.rpm
tframetest --version
```

## tfbench - TUI Benchmark Visualizer

**Purpose:** Python-based TUI tool to run tframetest benchmarks and visualize results using Rich library.

**Running tfbench:**
```bash
# Always use uv run to execute tfbench
uv run tfbench.py -w 4k -n 500 -t 8 /path/to/test/directory

# Custom configuration with extended timeout
uv run tfbench.py -w 4k -n 2000 -t 16 /media/storage --reads 3 --timeout 3600
```

**Architecture:**
- `TframetestParser` - Regex-based parser for tframetest output (handles both write and read formats)
- `BenchmarkRunner` - Subprocess management for running tframetest commands
- `BenchmarkVisualizer` - Rich TUI components (panels, tables, bar charts, sparklines)
- `BenchmarkResult` - Dataclass storing parsed metrics

**Key features:**
- Automated benchmark suite: 1 write + N reads (default 2)
- Real-time progress indicators during execution
- Visual comparisons: throughput bar charts, latency statistics
- Automatic calculations: cache speedup ratio, read/write ratio, latency improvements
- Color-coded outputs: green (write), blue (read #1), cyan (read #2)
- CSV export: Full results export for analysis and automation

**Dependencies:**
- Managed by uv (automatic virtual env creation)
- `rich>=13.7.0` - TUI rendering library

**Testing:**
```bash
# Test visualizer with sample data
uv run test_visualizer.py

# Test CSV export
uv run test_csv_export.py
```

**CSV Export:**
- Use `--csv filename.csv` to export results
- CSV includes metadata, full benchmark results, and calculated insights
- Format is compatible with pandas, Excel, and standard CSV tools

## Code Architecture (Upstream tframetest)

The tframetest tool is written in C99 and uses a modular architecture:

**Core modules:**
- `frametest.c` - Main entry point, thread management, command-line interface
- `frame.c` - Frame data structure and I/O operations
- `tester.c` - Test execution engine (read/write operations)
- `platform.c` - Platform-specific implementations (Linux/Windows/FreeBSD)
- `profile.c` - Configuration and test profiles
- `report.c` - Results reporting and output formatting
- `histogram.c` - Performance metrics and histogram generation
- `timing.c` - High-resolution timing utilities

**Test framework:**
- `tests/` directory contains unit tests
- Uses custom `unittest.h` framework
- Tests cover all core modules

**Key characteristics:**
- Multi-threaded I/O testing using POSIX threads
- Direct file I/O with configurable frame sizes
- Performance profiling with latency histograms
- Cross-platform support (Linux primary, Windows/FreeBSD)

## License

GNU General Public License v2.0 or later (GPLv2+)
