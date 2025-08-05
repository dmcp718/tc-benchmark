#!/bin/bash
# Create a portable bundle for TeamCache setup

set -euo pipefail

echo "Creating TeamCache portable bundle..."

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Create bundle directory
BUNDLE_DIR="teamcache-bundle"
rm -rf "$BUNDLE_DIR"
mkdir -p "$BUNDLE_DIR"

# Copy main script
cp teamcache-setup.py "$BUNDLE_DIR/"

# Copy required files and directories
cp -r conf "$BUNDLE_DIR/"
cp entrypoint.sh "$BUNDLE_DIR/"
cp lucid-site-cache.service "$BUNDLE_DIR/"
cp README-DEPLOYMENT.md "$BUNDLE_DIR/README.md"

# Create requirements file
cat > "$BUNDLE_DIR/requirements.txt" << EOF
rich>=13.0.0
EOF

# Create setup script
cat > "$BUNDLE_DIR/setup.sh" << 'EOF'
#!/bin/bash
# TeamCache Setup Launcher

set -euo pipefail

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}This script must be run as root${NC}"
   echo "Please run: sudo ./setup.sh"
   exit 1
fi

# Check Python 3
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Python 3 is required but not installed${NC}"
    exit 1
fi

# Check if Rich is installed
if ! python3 -c "import rich" 2>/dev/null; then
    echo -e "${YELLOW}Installing required Python packages...${NC}"
    
    # Try pip3 first
    if command -v pip3 &> /dev/null; then
        pip3 install -r requirements.txt || {
            echo -e "${YELLOW}Trying with --break-system-packages flag...${NC}"
            pip3 install --break-system-packages -r requirements.txt
        }
    else
        echo -e "${RED}pip3 not found. Please install python3-pip${NC}"
        echo "Run: apt-get install python3-pip"
        exit 1
    fi
fi

# Run the setup
echo -e "${GREEN}Starting TeamCache Setup...${NC}"
python3 teamcache-setup.py "$@"
EOF

chmod +x "$BUNDLE_DIR/setup.sh"

# No need to create README.txt as we're copying README-DEPLOYMENT.md as README.md

# Create tarball that extracts directly to current directory
TARBALL="teamcache-bundle-$(date +%Y%m%d).tar.gz"
# Use -C to change directory and . to include all files without parent directory
tar -czf "$TARBALL" -C "$BUNDLE_DIR" .

echo -e "${GREEN}✓ Bundle created successfully!${NC}"
echo ""
echo "Bundle location: $TARBALL"
echo "Size: $(ls -lh $TARBALL | awk '{print $5}')"
echo ""
echo "To deploy:"
echo "  1. Copy $TARBALL to target system"
echo "  2. Create directory: mkdir -p /opt/sitecache"
echo "  3. Extract: cd /opt/sitecache && tar -xzf /path/to/$TARBALL"
echo "  4. Add your varnish-enterprise.lic file"
echo "  5. Run: sudo ./setup.sh"