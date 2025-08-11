# TeamCache Development Guide

## Overview

TeamCache is a high-performance S3 proxy caching solution. This repository contains the setup tools and configuration for deploying TeamCache.

## Development Setup

### Prerequisites

- Python 3.6+
- Docker and Docker Compose
- Root privileges (for disk formatting and mounting)
- Varnish Enterprise license file (`varnish-enterprise.lic`)

### Repository Structure

```
/opt/tc-setup-app/
├── teamcache-setup.py      # Main interactive setup script
├── scripts/                # Build and deployment scripts
│   ├── build-portable.sh   # Build portable bundle
│   ├── build-standalone.py # PyInstaller standalone build
│   └── create-bundle.sh    # Bundle creation for deployment
├── conf/                   # Configuration templates
│   ├── default.vcl         # Varnish VCL configuration
│   ├── prometheus.yml      # Prometheus scrape configuration
│   └── grafana/            # Grafana dashboards and provisioning
├── entrypoint.sh          # Docker container entrypoint
├── teamcache.service       # SystemD service definition
├── requirements.txt       # Python dependencies
├── README.md             # This file
└── README-DEPLOYMENT.md  # End-user deployment guide
```

### Running the Setup Script

1. Clone the repository to `/opt/tc-setup-app/`
2. Place your `varnish-enterprise.lic` file in the directory
3. Run the setup script:
   ```bash
   sudo python3 teamcache-setup.py
   ```

The setup script provides an interactive TUI that:
- Detects available block devices for cache storage
- Formats selected devices with XFS filesystem
- Creates mount points and updates `/etc/fstab`
- Generates configuration files (`mse4.conf`, `compose.yaml`)
- Installs and starts the Docker Compose stack

### Building for Deployment

#### Standard Method (Recommended)
```bash
./scripts/create-bundle.sh
```
Creates `teamcache-bundle-YYYYMMDD.tar.gz` - a complete deployment package with setup script.
- **Deploy with**: Extract and run `./setup.sh`
- **Requires**: Python 3.6+ on target system (or use standalone option below)
- **Full deployment instructions**: See `README-DEPLOYMENT.md` for detailed steps

#### Advanced Options
<details>
<summary>For systems without Python (click to expand)</summary>

**Create Bundle with Standalone Executable** (no Python required on target):
```bash
# Step 1: Build standalone executable (one-time setup)
./scripts/build-standalone.py  # Creates dist/teamcache-setup executable
                                # Also creates teamcache-deploy.tar.gz (ignore this)

# Step 2: Create deployment bundle (includes the executable)
./scripts/create-bundle.sh      # Creates teamcache-bundle-YYYYMMDD.tar.gz
                                # Now includes executable instead of Python script
```

**Use teamcache-bundle-*.tar.gz for deployment** (not teamcache-deploy.tar.gz).

After Step 1, all future bundles will include the standalone executable instead of the Python script, making them ~31MB but requiring no Python installation on target systems.

To revert to Python-based bundles: `rm dist/teamcache-setup`
</details>

### Development Workflow

1. Make changes to the setup script or configuration files
2. Test locally with: `sudo python3 teamcache-setup.py`
3. Build deployment package: `./scripts/create-bundle.sh`
4. Deploy bundle using instructions in `README-DEPLOYMENT.md`

### Development Notes

- The setup script uses Python's `rich` library for the TUI
- All logging goes to `/tmp/teamcache-setup-*.log`
- Docker images are built inline to avoid Docker Hub authentication
- The service runs as `teamcache.service` via systemd

## Manual Configuration (Legacy)

For manual setup without the interactive script, follow these steps:

1. Edit `mse4.conf` to configure storage:
   ```
   env: {
       books = ( {
           id = "book1";
           filename = "/var/lib/mse/disk1/book";
           size = "8G";
           stores = ( {
               id = "store1";
               filename = "/var/lib/mse/disk1/store";
               size = "905G";  # (disk_size - 8G) * 0.98
           } );
       } );
   };
   ```

2. The setup script will prompt for Grafana admin password
3. Run Docker Compose:
   ```bash
   docker compose up -d
   ```

## Configuring LucidLink Clients

Configure all clients to use the cache:

```bash
lucid3 config --fs <filespace.domain> --global --set \
  --ObjectScheduler.SiteCacheEndpoint http://<cache-server-ip>:80
```

Clients should reconnect to their filespace after this configuration.
