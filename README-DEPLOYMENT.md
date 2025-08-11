# TeamCache Deployment Guide

## Quick Start

This bundle contains everything needed to deploy TeamCache - a high-performance caching solution for LucidLink.

### Prerequisites

- Ubuntu 20.04 or later (recommended)
- Python 3.6 or later (if not using standalone executable)
- Docker and Docker Compose installed
- Root privileges (sudo)
- Your `varnish-enterprise.lic` license file
- Available block devices for cache storage (or use file-based storage)

### Installation Steps

1. **Extract the bundle**:
   ```bash
   sudo mkdir -p /opt/teamcache
   cd /opt/teamcache
   sudo tar -xzf /path/to/teamcache-bundle-*.tar.gz
   ```

2. **Add your license file**:
   ```bash
   # Copy your varnish-enterprise.lic to /opt/teamcache/
   sudo cp /path/to/varnish-enterprise.lic /opt/teamcache/
   ```

3. **Run the setup**:
   ```bash
   sudo ./setup.sh
   ```

### What the Setup Does

The interactive setup will guide you through:

1. **Device Selection**: Choose which block devices to use for cache storage
   - The tool safely identifies available devices
   - Only unmounted devices are shown for selection
   - Option to skip and use file-based storage

2. **Formatting**: Selected devices are formatted with XFS filesystem
   - Optimized for large file performance
   - Mount points created under `/cache/disk*`
   - Automatic `/etc/fstab` entries for persistence

3. **Configuration**: Generates required configuration files
   - `mse4.conf` - Storage engine configuration
   - `compose.yaml` - Docker stack definition
   - Service endpoint configuration

4. **Service Installation**: Deploys and starts TeamCache
   - Creates systemd service `teamcache.service`
   - Starts Docker containers automatically
   - Validates service health

### Post-Installation

After successful setup:

- **Grafana Dashboard**: `http://<server-ip>:3000`
  - Default user: `admin`
  - Password: Set during setup
  - Metrics and performance monitoring

- **Cache Endpoint**: `http://<server-ip>:80`
  - Configure LucidLink clients to use this endpoint

- **Service Management**:
  ```bash
  # Check status
  sudo systemctl status teamcache.service
  
  # View logs
  sudo docker compose logs -f
  
  # Stop service
  sudo systemctl stop teamcache.service
  ```

### Troubleshooting

**IMPORTANT**: After setup completes, always verify the service is actually running:
```bash
sleep 10  # Wait for Docker to pull/build images
sudo systemctl status teamcache.service
# Should show "Active: active (running)" not "failed"
```

1. **Service fails to start**:
   - Check logs: `sudo journalctl -u teamcache.service -n 100`
   - Verify Docker is running: `sudo systemctl status docker`
   - Check license file exists: `ls -la /opt/teamcache/varnish-enterprise.lic`

2. **No devices available**:
   - The setup will offer file-based storage as an alternative
   - You can add block devices later and re-run the setup

3. **Grafana shows "No data"**:
   - Wait 1-2 minutes for metrics to populate
   - Check Prometheus is scraping: `curl http://localhost:9090/metrics`

### Client Configuration

Configure globally for the filespace:
```bash
lucid3 config --fs <filespace.domain> --global --set \
  --ObjectScheduler.SiteCacheEndpoint http://<cache-server-ip>:80
```

