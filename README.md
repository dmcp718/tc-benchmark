# tframetest - Static Binary Packages

Static binary packages of [tframetest](https://github.com/tuxera/tframetest), a tool to test and benchmark writing/reading media frames to/from disk.

## Package Information

**Version:** 3025.1.1
**Build Type:** Static (no external dependencies)
**Architecture:** x86-64
**Minimum Kernel:** Linux 3.2.0+

### Available Packages

| Package       | File                                        | Size | Target Systems                     |
|---------------|---------------------------------------------|------|------------------------------------|
| Debian/Ubuntu | `tframetest_3025.1.1_amd64.deb`             | 322K | Debian, Ubuntu, derivatives        |
| EL9 RPM       | `tframetest-3025.1.1-1.el9.x86_64.rpm`      | 354K | RHEL 9, Rocky Linux 9, AlmaLinux 9 |

## Installation

### Debian/Ubuntu
```bash
sudo dpkg -i tframetest_3025.1.1_amd64.deb
```

### RHEL/Rocky/AlmaLinux 9
```bash
sudo rpm -ivh tframetest-3025.1.1-1.el9.x86_64.rpm
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
- `--help` - Display all available options

### Example: Performance Testing

```bash
# Create test directory
mkdir -p /mnt/storage/frametest

# Write 10,000 4KB frames with 8 threads
tframetest -w 4k -n 10000 -t 8 /mnt/storage/frametest

# Read them back and measure performance
tframetest -r -n 10000 -t 8 /mnt/storage/frametest
```

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
