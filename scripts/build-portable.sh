#!/bin/bash
# Build script for creating portable TeamCache setup application

set -euo pipefail

echo "Building portable TeamCache setup application..."

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if running in the correct directory
if [ ! -f "teamcache-setup.py" ]; then
    echo -e "${RED}Error: teamcache-setup.py not found in current directory${NC}"
    echo "Please run this script from the /opt/teamcache directory"
    exit 1
fi

# Check if pyinstaller is installed
if ! command -v pyinstaller &> /dev/null; then
    echo -e "${YELLOW}PyInstaller not found. Installing...${NC}"
    # Try with --break-system-packages flag for modern Python (PEP 668)
    if ! pip3 install --break-system-packages pyinstaller 2>/dev/null; then
        # Fallback to without flag for older Python versions
        if ! pip3 install pyinstaller 2>/dev/null; then
            echo -e "${RED}Failed to install PyInstaller.${NC}"
            echo "Please install manually with one of these commands:"
            echo "  sudo apt install python3-pyinstaller  # For system package"
            echo "  pip3 install --break-system-packages pyinstaller  # Override protection"
            echo "  pipx install pyinstaller  # Using pipx"
            exit 1
        fi
    fi
fi

# Clean previous builds
echo "Cleaning previous builds..."
rm -rf build/ dist/ __pycache__/

# Build the application
echo "Building application..."
pyinstaller teamcache-setup.spec --clean

# Check if build was successful
if [ -f "dist/teamcache-setup" ]; then
    echo -e "${GREEN}✓ Build successful!${NC}"
    echo ""
    echo "The portable application is located at:"
    echo "  dist/teamcache-setup"
    echo ""
    echo "To use it:"
    echo "  1. Copy dist/teamcache-setup to your target system"
    echo "  2. Make it executable: chmod +x teamcache-setup"
    echo "  3. Run with sudo: sudo ./teamcache-setup"
    echo ""
    
    # Show file size
    SIZE=$(ls -lh dist/teamcache-setup | awk '{print $5}')
    echo "Application size: $SIZE"
else
    echo -e "${RED}✗ Build failed!${NC}"
    echo "Check the output above for errors"
    exit 1
fi