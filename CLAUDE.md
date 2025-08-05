# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Prerequisites

### Docker Login for Varnish Plus
```bash
# REQUIRED: Login to Varnish Software Docker registry
# You need credentials from your LucidLink Account Manager
docker login -u <username> -p <password> registry.varnish-software.com

# Verify authentication
docker pull varnish-software/varnish-plus:6.0.13r15
```

## Commands

### Running the Setup Script (Python Version)
```bash
# Install dependencies
pip3 install -r requirements.txt
# or
pip3 install rich

# Run the interactive setup (requires root)
sudo python3 teamcache-setup.py

# View setup logs
tail -f /tmp/teamcache-setup-*.log
```

### Docker Commands
```bash
# Start the TeamCache stack after setup (generates compose.yaml)
docker compose up -d

# View container logs
docker compose logs -f varnish
docker compose logs -f grafana
docker compose logs -f prometheus

# Stop services
docker compose down

# Check container status
docker compose ps
```

### Service Management
```bash
# The setup script installs a systemd service
sudo systemctl status lucid-site-cache.service
sudo systemctl start lucid-site-cache.service
sudo systemctl stop lucid-site-cache.service
sudo systemctl restart lucid-site-cache.service

# View service logs
journalctl -u lucid-site-cache.service -f

# Common issues:
# - "pull access denied for varnish-software/varnish-plus" = Need Docker login (see Prerequisites)
# - Service shows "failed" = Check logs for Docker authentication or compose.yaml issues
```

### Testing and Validation
```bash
# CRITICAL: DO NOT TRUST THE SETUP SCRIPT'S "Service is running successfully!" message
# The script has a race condition bug - always manually verify after waiting a few seconds

# Proper service check sequence:
sleep 10  # Wait for Docker Compose to actually try pulling images
sudo systemctl status lucid-site-cache
# MUST show "Active: active (running)" - NOT "Active: failed"
# MUST NOT show "code=exited, status=1/FAILURE"

# The setup script should be using this command and parsing the output!
# Not just checking systemctl is-active

# Check Docker containers are actually running
docker compose ps
# Should show all containers as "Up" not "Exited"

# Check if Varnish is responding (only works if containers are running)
curl -I http://localhost:6081  # Note: setup shows port 6081, not 80
# Or from remote:
curl -I http://$SERVER_IP:$PORT  # e.g., curl -I http://192.168.8.14:6081

# IMPORTANT: "503 Backend fetch failed" response actually indicates SUCCESS
# This means Varnish is running and responsive, just no backend configured yet
# This is expected behavior for a cache proxy without active client requests
# Example successful response:
#   HTTP/1.1 503 Backend fetch failed
#   Date: Mon, 04 Aug 2025 13:35:00 GMT
#   Server: Varnish
#   Content-Type: text/html; charset=utf-8

# Access Grafana dashboard
# URL: http://localhost:3000
# Default user: admin
# Password: (set during setup or in conf/grafana/grafana.ini)

# Check Prometheus metrics from Varnish
curl http://localhost/metrics

# Check Prometheus server
curl http://localhost:9090/metrics
```

### Client Configuration
```bash
# For Linux clients - edit lucid service
sudo systemctl edit --full lucid.service
# Add: Environment=LUCID_S3_PROXY=http://<site-cache-ip>:80/

# For Mac clients - use global config
lucid3 config --fs <filespace.domain> --global --set --ObjectScheduler.SiteCacheEndpoint http://<site-cache-ip>:80
```

## Architecture

This is a LucidLink Site Cache deployment system (branded as TeamCache) that uses:

1. **Varnish Plus 6.0.13r15 with MSE4** - Enterprise HTTP cache with Massive Storage Engine for persistent caching across XFS-formatted block devices
2. **Prometheus** - Time-series database for collecting Varnish performance metrics (5s scrape interval)
3. **Grafana** - Visualization platform with pre-configured dashboards for cache metrics and logs

The Python setup script (`teamcache-setup.py`) provides an interactive Rich-based TUI that:
- Discovers block devices using `lsblk` JSON output
- Validates devices are safe to format (no mounted partitions)
- Formats selected devices with XFS filesystem
- Creates mount points under `/cache/disk*`
- Updates `/etc/fstab` for persistence
- Generates all configuration files dynamically based on device selection
- Optionally installs and starts the systemd service

## Key Configuration Files

### Pre-existing Files (in repo)
- **conf/default.vcl** - Varnish VCL with AWSv4 signature support, range request handling, and dynamic backend selection
- **conf/prometheus.yml** - Prometheus configuration targeting varnish:80 for metrics
- **conf/grafana/provisioning/** - Grafana datasources (Prometheus, Loki, Tempo) and dashboards
- **lucid-site-cache.service** - Systemd service definition

### Generated Files (by setup script)
- **mse4.conf** - MSE storage configuration with book/store hierarchy based on selected devices
- **compose.yaml** - Docker Compose stack with device-specific volume mounts
- Mount configurations in `/etc/fstab`

## Important VCL Details

The Varnish configuration (`conf/default.vcl`) includes:
- URI decoding and accounting namespace for LucidLink
- Special handling for AWS S3 signatures (preserves Range headers)
- Dynamic TLS backend creation using `goto.dns_backend()`
- 10-year TTL for successful responses (200, 206, 304)
- Prometheus metrics endpoint at `/metrics`

## Troubleshooting

### CRITICAL: Setup Script False Success Bug
**The Python setup script has a bug where it reports "✓ Service is running successfully!" even when the service will immediately fail.**

The script uses `systemctl is-active` which is insufficient. It should use `systemctl status lucid-site-cache` and parse the output properly.

**The script MUST check for:**
```bash
# Proper service verification command:
systemctl status lucid-site-cache

# Parse for BOTH conditions:
# 1. "Active: active (running)" - NOT just "active"
# 2. No "code=exited, status=1/FAILURE" in the output

# Current bug: Script shows success even when status shows:
# × lucid-site-cache.service - LucidLink Site Cache Docker Compose Service
#      Active: failed (Result: exit-code)
#      Main PID: 27571 (code=exited, status=1/FAILURE)
```

**ALWAYS manually verify after setup:**
```bash
# Wait a few seconds after setup completes, then check
sleep 10
sudo systemctl status lucid-site-cache

# Look for "Active: active (running)" without any failure codes
```

### Docker Authentication Required
Even if you successfully run `docker login`, the issue persists because:
1. You need to login to the specific Varnish registry: `registry.varnish-software.com`
2. The image path in compose.yaml might need the full registry URL

```bash
# Correct login command
docker login registry.varnish-software.com -u <username> -p <password>

# Verify you can pull manually
docker pull varnish-software/varnish-plus:6.0.13r15
```

### Configuration Changes
Note that the setup script generates different MSE4 configuration formats:
- Old format: Uses `env:` with nested books/stores
- New format: Uses `mse4` with flattened structure and explicit paths
Both formats are valid but ensure consistency if manually editing.