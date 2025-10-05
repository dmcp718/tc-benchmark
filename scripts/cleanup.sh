#!/bin/bash
#
# TeamCache Cleanup Script
# Removes all TeamCache deployments and configurations for testing
#
# Usage: sudo ./scripts/cleanup.sh [--keep-data]
#
# Options:
#   --keep-data    Keep mounted filesystems and data (only remove services/containers)
#

set -e

KEEP_DATA=false
if [[ "$1" == "--keep-data" ]]; then
    KEEP_DATA=true
    echo "Running in --keep-data mode (preserving mounted filesystems)"
fi

echo "============================================================"
echo "TeamCache Cleanup Script"
echo "============================================================"
echo ""

# Check root
if [ "$EUID" -ne 0 ]; then
    echo "ERROR: This script must be run as root"
    echo "Please run: sudo ./scripts/cleanup.sh"
    exit 1
fi

# 1. Stop and remove systemd services
echo "[1/6] Stopping and removing systemd services..."

if systemctl is-active --quiet teamcache.service 2>/dev/null; then
    echo "  - Stopping teamcache.service..."
    systemctl stop teamcache.service || true
fi

if systemctl is-enabled --quiet teamcache.service 2>/dev/null; then
    echo "  - Disabling teamcache.service..."
    systemctl disable teamcache.service || true
fi

if [ -f /etc/systemd/system/teamcache.service ]; then
    echo "  - Removing teamcache.service..."
    rm -f /etc/systemd/system/teamcache.service
fi

if systemctl is-active --quiet tc-grafana.service 2>/dev/null; then
    echo "  - Stopping tc-grafana.service..."
    systemctl stop tc-grafana.service || true
fi

if systemctl is-enabled --quiet tc-grafana.service 2>/dev/null; then
    echo "  - Disabling tc-grafana.service..."
    systemctl disable tc-grafana.service || true
fi

if [ -f /etc/systemd/system/tc-grafana.service ]; then
    echo "  - Removing tc-grafana.service..."
    rm -f /etc/systemd/system/tc-grafana.service
fi

systemctl daemon-reload
echo "  ✓ Systemd services removed"
echo ""

# 2. Stop and remove Docker containers and images
echo "[2/6] Stopping and removing Docker containers..."

if command -v docker &> /dev/null; then
    # Stop containers with teamcache in the name
    if [ "$(docker ps -aq -f name=teamcache 2>/dev/null)" ]; then
        echo "  - Stopping TeamCache containers..."
        docker ps -aq -f name=teamcache | xargs -r docker stop || true
        docker ps -aq -f name=teamcache | xargs -r docker rm || true
    fi

    # Stop containers from compose files
    if [ -f /opt/teamcache/compose.yaml ]; then
        echo "  - Stopping Docker Compose stack (compose.yaml)..."
        docker compose -f /opt/teamcache/compose.yaml down -v 2>/dev/null || true
    fi

    if [ -f /opt/teamcache/monitoring-compose.yaml ]; then
        echo "  - Stopping monitoring stack (monitoring-compose.yaml)..."
        docker compose -f /opt/teamcache/monitoring-compose.yaml down -v 2>/dev/null || true
    fi

    # Remove TeamCache-related images
    echo "  - Removing TeamCache Docker images..."
    docker images --format "{{.Repository}}:{{.Tag}}" | grep -E "(varnish|prometheus|grafana)" | xargs -r docker rmi -f 2>/dev/null || true

    echo "  ✓ Docker containers and images removed"
else
    echo "  - Docker not installed, skipping"
fi
echo ""

# 3. Remove Varnish processes (if running outside systemd)
echo "[3/6] Stopping any running Varnish processes..."
if pgrep varnishd > /dev/null 2>&1; then
    echo "  - Killing varnishd processes..."
    pkill -9 varnishd || true
    echo "  ✓ Varnish processes stopped"
else
    echo "  - No Varnish processes running"
fi
echo ""

# 4. Unmount cache disks and clean fstab
if [ "$KEEP_DATA" = false ]; then
    echo "[4/6] Unmounting cache disks..."

    # Find all /cache/disk* mounts
    CACHE_MOUNTS=$(mount | grep -E '/cache/disk[0-9]+' | awk '{print $3}' || true)

    if [ -n "$CACHE_MOUNTS" ]; then
        for mount_point in $CACHE_MOUNTS; do
            echo "  - Unmounting $mount_point..."
            umount "$mount_point" 2>/dev/null || umount -l "$mount_point" 2>/dev/null || true
        done
        echo "  ✓ Cache disks unmounted"
    else
        echo "  - No cache disks mounted"
    fi

    # Remove /cache/disk* entries from /etc/fstab
    if grep -q '/cache/disk' /etc/fstab 2>/dev/null; then
        echo "  - Removing cache disk entries from /etc/fstab..."
        cp /etc/fstab /etc/fstab.backup.$(date +%Y%m%d-%H%M%S)
        grep -v '/cache/disk' /etc/fstab > /etc/fstab.tmp || true
        mv /etc/fstab.tmp /etc/fstab
        echo "  ✓ Cleaned /etc/fstab (backup created)"
    fi

    # Remove mount point directories
    if [ -d /cache ]; then
        echo "  - Removing /cache directories..."
        rm -rf /cache/disk* 2>/dev/null || true
        # Remove /cache only if it's empty
        rmdir /cache 2>/dev/null || true
    fi
else
    echo "[4/6] Skipping unmount (--keep-data mode)"
fi
echo ""

# 5. Remove configuration files
echo "[5/6] Removing configuration files..."

# Hybrid mode configs
if [ -d /etc/varnish ]; then
    echo "  - Removing /etc/varnish..."
    rm -rf /etc/varnish
fi

# Docker mode configs
if [ -d /opt/teamcache ]; then
    echo "  - Removing /opt/teamcache..."
    rm -rf /opt/teamcache
fi

echo "  ✓ Configuration files removed"
echo ""

# 6. Remove SELinux contexts (RHEL/Rocky/CentOS)
if command -v semanage &> /dev/null && [ "$KEEP_DATA" = false ]; then
    echo "[6/6] Cleaning SELinux contexts..."

    # Remove custom file contexts for cache directories
    semanage fcontext -l | grep -E '/cache/disk[0-9]+' | while read -r line; do
        context_path=$(echo "$line" | awk '{print $1}')
        echo "  - Removing SELinux context for $context_path..."
        semanage fcontext -d "$context_path" 2>/dev/null || true
    done

    echo "  ✓ SELinux contexts cleaned"
else
    echo "[6/6] Skipping SELinux cleanup (not applicable or --keep-data mode)"
fi
echo ""

# Summary
echo "============================================================"
echo "Cleanup Complete!"
echo "============================================================"
echo ""
echo "Removed:"
echo "  - Systemd services (teamcache.service, tc-grafana.service)"
echo "  - Docker containers and images"
echo "  - Varnish processes"
if [ "$KEEP_DATA" = false ]; then
    echo "  - Mounted cache disks"
    echo "  - /etc/fstab entries"
    echo "  - /cache directories"
fi
echo "  - Configuration files (/etc/varnish, /opt/teamcache)"
if command -v semanage &> /dev/null && [ "$KEEP_DATA" = false ]; then
    echo "  - SELinux contexts"
fi
echo ""

if [ "$KEEP_DATA" = true ]; then
    echo "NOTE: Cache disks remain mounted (--keep-data mode)"
    echo "To unmount manually, run: sudo ./scripts/cleanup.sh"
    echo ""
fi

echo "You can now run a fresh deployment:"
echo "  sudo uv run python teamcache-setup.py"
echo "  OR"
echo "  sudo python3 teamcache-auto.py --env-file .env"
echo ""
