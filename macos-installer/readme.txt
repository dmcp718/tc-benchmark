tframetest - Media Frame Testing Tool

Version: 3025.1.1
Platform: macOS (ARM64)

INSTALLATION

This installer will place the tframetest binary in:
  /usr/local/bin/tframetest

After installation, you can run tframetest from any terminal window.

USAGE

Basic usage examples:

1. Write 1000 frames of 2k size with 4 threads:
   mkdir tst
   tframetest -w 2k -n 1000 -t 4 tst

2. Read those frames:
   tframetest -r -n 1000 -t 4 tst

3. Get help:
   tframetest --help

4. Check version:
   tframetest --version

SYSTEM REQUIREMENTS

- macOS 10.13 (High Sierra) or later
- Apple Silicon (M1/M2/M3) or Intel processor

UNINSTALLATION

To uninstall tframetest, simply remove the binary:
  sudo rm /usr/local/bin/tframetest

LICENSE

This program is distributed under the terms of the GNU General Public License
version 2 or later.

SOURCE CODE

Source code is available at: https://github.com/tuxera/tframetest
