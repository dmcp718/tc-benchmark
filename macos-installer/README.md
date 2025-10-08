# tframetest macOS Installer

This directory contains the macOS installer package for tframetest.

## What's Included

- **tframetest-3025.1.1-macos-arm64.pkg** - Ready-to-install package for macOS
- Native ARM64 binary optimized for Apple Silicon (M1/M2/M3)
- Also compatible with Intel Macs via Rosetta 2

## Installation

### GUI Installation (Recommended)
1. Double-click `tframetest-3025.1.1-macos-arm64.pkg`
2. Follow the on-screen instructions
3. Enter your administrator password when prompted
4. The installer will place `tframetest` in `/usr/local/bin/`

### Command-Line Installation
```bash
sudo installer -pkg build/tframetest-3025.1.1-macos-arm64.pkg -target /
```

## Verification

After installation, verify tframetest is working:
```bash
tframetest --version
```

You should see:
```
tframetest 3025.1.1
```

## Usage

Basic examples:
```bash
# Create test directory
mkdir tst

# Write test: 1000 frames of 2k size with 4 threads
tframetest -w 2k -n 1000 -t 4 tst

# Read test
tframetest -r -n 1000 -t 4 tst

# Get help
tframetest --help
```

## Uninstallation

To uninstall tframetest:
```bash
sudo rm /usr/local/bin/tframetest
```

## Building the Installer

If you need to rebuild the installer package:

1. Ensure you have the binary:
   ```bash
   ls -l payload/usr/local/bin/tframetest
   ```

2. Run the build script:
   ```bash
   ./build-installer.sh
   ```

3. The installer will be created at:
   ```
   build/tframetest-3025.1.1-macos-arm64.pkg
   ```

## System Requirements

- macOS 10.13 (High Sierra) or later
- Apple Silicon (M1/M2/M3) recommended for best performance
- Intel processors supported via Rosetta 2

## Directory Structure

```
macos-installer/
├── build-installer.sh          # Build script
├── Distribution.xml            # Product archive configuration
├── LICENSE.txt                 # GPL v2 license
├── readme.txt                  # Installer readme
├── welcome.txt                 # Welcome screen text
├── payload/
│   └── usr/local/bin/
│       └── tframetest         # The binary
├── scripts/
│   └── postinstall            # Post-installation script
└── build/
    └── tframetest-3025.1.1-macos-arm64.pkg  # Final installer
```

## License

tframetest is distributed under the GNU General Public License v2.0 or later.

## Source Code

- Upstream: https://github.com/tuxera/tframetest
