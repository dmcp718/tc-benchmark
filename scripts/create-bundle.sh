#!/bin/bash
# Create a portable bundle for TeamCache setup

set -euo pipefail

echo "Creating TeamCache portable bundle..."

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Get the project root directory (parent of scripts/)
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Change to project root to ensure all paths work correctly
cd "$PROJECT_ROOT"

# Create bundle directory
BUNDLE_DIR="teamcache-bundle"
rm -rf "$BUNDLE_DIR"
mkdir -p "$BUNDLE_DIR"

# Copy main script or executable
if [ -f "dist/teamcache-setup" ]; then
    # PyInstaller executable exists
    cp dist/teamcache-setup "$BUNDLE_DIR/"
    USING_PYINSTALLER=true
else
    # Fall back to Python script
    cp teamcache-setup.py "$BUNDLE_DIR/"
    USING_PYINSTALLER=false
fi

# Copy required files and directories
echo "Copying files..."

# Check and copy each required file
for file in conf entrypoint.sh teamcache.service README-DEPLOYMENT.md; do
    if [ ! -e "$file" ]; then
        echo -e "${RED}Error: Required file '$file' not found!${NC}"
        echo "Make sure you're running this script from the project root or use:"
        echo "  cd /opt/tc-setup-app && ./scripts/create-bundle.sh"
        exit 1
    fi
done

cp -r conf "$BUNDLE_DIR/"
echo "  ✓ Copied conf/"
cp entrypoint.sh "$BUNDLE_DIR/"
echo "  ✓ Copied entrypoint.sh"
cp teamcache.service "$BUNDLE_DIR/"
echo "  ✓ Copied teamcache.service"
cp README-DEPLOYMENT.md "$BUNDLE_DIR/README.md"
echo "  ✓ Copied README-DEPLOYMENT.md as README.md"

# Only create requirements file if not using PyInstaller
if [ "$USING_PYINSTALLER" = false ]; then
    cat > "$BUNDLE_DIR/requirements.txt" << EOF
rich>=13.0.0
EOF
fi

# Create setup script based on whether we're using PyInstaller
if [ "$USING_PYINSTALLER" = true ]; then
    # Create setup script for PyInstaller executable
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

# Check Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Docker is required but not installed${NC}"
    echo "Please install Docker: https://docs.docker.com/engine/install/"
    exit 1
fi

# Check Docker service is running
if ! systemctl is-active --quiet docker; then
    echo -e "${RED}Docker service is not running${NC}"
    echo "Please start Docker: sudo systemctl start docker"
    exit 1
fi

# Check Docker Compose
if ! docker compose version &> /dev/null; then
    echo -e "${RED}Docker Compose is required but not installed${NC}"
    echo "Please install Docker Compose plugin for Docker"
    exit 1
fi

# Check for license file (warning only, don't exit)
if [ ! -f "varnish-enterprise.lic" ]; then
    echo -e "${YELLOW}⚠ Warning: varnish-enterprise.lic not found${NC}"
    echo "You will need to add your Varnish Enterprise license file before the service can start"
    echo ""
fi

# Run the setup (PyInstaller executable)
echo -e "${GREEN}Starting TeamCache Setup...${NC}"
./teamcache-setup "$@"
EOF

else
    # Create setup script for Python version
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

# Check Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Docker is required but not installed${NC}"
    echo "Please install Docker: https://docs.docker.com/engine/install/"
    exit 1
fi

# Check Docker service is running
if ! systemctl is-active --quiet docker; then
    echo -e "${RED}Docker service is not running${NC}"
    echo "Please start Docker: sudo systemctl start docker"
    exit 1
fi

# Check Docker Compose
if ! docker compose version &> /dev/null; then
    echo -e "${RED}Docker Compose is required but not installed${NC}"
    echo "Please install Docker Compose plugin for Docker"
    exit 1
fi

# Check for license file (warning only, don't exit)
if [ ! -f "varnish-enterprise.lic" ]; then
    echo -e "${YELLOW}⚠ Warning: varnish-enterprise.lic not found${NC}"
    echo "You will need to add your Varnish Enterprise license file before the service can start"
    echo ""
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

# Run the setup (Python version)
echo -e "${GREEN}Starting TeamCache Setup...${NC}"
python3 teamcache-setup.py "$@"
EOF

fi

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
echo "  2. Create directory: mkdir -p /opt/teamcache"
echo "  3. Extract: cd /opt/teamcache && tar -xzf /path/to/$TARBALL"
echo "  4. Add your varnish-enterprise.lic file"
echo "  5. Run: sudo ./setup.sh"