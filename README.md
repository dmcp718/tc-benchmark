# TeamCache Setup Tool

Automated deployment tool for LucidLink TeamCache

## Overview

TeamCache Setup provides an interactive TUI to configure and deploy TeamCache with two deployment options:

1. **Docker Compose** - All-in-one containerized deployment (Varnish + Monitoring)
2. **Hybrid** - Native Varnish installation + optional monitoring stack (recommended)

## Prerequisites

- **Operating System**: Ubuntu 20.04+, Debian 11+, RHEL 8+, Rocky Linux, AlmaLinux, Fedora, or CentOS 7
- **Privileges**: Root access (sudo)
- **Python**: 3.8 or later (installed by default on most systems)
- **Storage**: Available block devices for cache storage (NVMe/SSD recommended)
- **License**: Varnish Enterprise license file (`varnish-enterprise.lic`)
- **Network**: Internet access for package installation

## Quick Start

```bash
# 1. Clone or download this repository
cd /path/to/teamcache-setup

# 2. Add your Varnish Enterprise license file
cp /path/to/varnish-enterprise.lic .

# 3. (Optional) Install uv for faster dependency management
curl -LsSf https://astral.sh/uv/install.sh | sh

# 4. Run the setup (requires root)
sudo uv run python teamcache-setup.py
# OR if uv is not installed:
sudo python3 teamcache-setup.py
```

## Deployment Modes

### Option 1: Docker Compose (All-in-one)

**What it does:**
- Runs Varnish, Prometheus, and Grafana in Docker containers
- Single service: `teamcache.service`
- Easier to manage, portable across systems

**Best for:**
- Quick testing and evaluation
- Environments where native packages can't be installed
- Simplified management

### Option 2: Hybrid (Recommended)

**What it does:**
- Installs Varnish **natively** via package manager (`varnish-plus`)
- Runs Varnish as `teamcache.service` via systemd (not Docker)
- Optional Prometheus/Grafana monitoring via `tc-grafana.service`

**Best for:**
- Production deployments
- Better performance (native vs containerized)
- Full systemd integration
- Flexibility to run Varnish without Docker

**Services created:**
- `teamcache.service` - Native Varnish cache
- `tc-grafana.service` - Monitoring stack (optional)

## Installation Workflow

The interactive setup guides you through:

### 1. Deployment Mode Selection
Choose between Docker Compose or Hybrid deployment.

### 2. Device Selection
- Automatically detects available block devices
- Option to format new devices with XFS
- Option to reuse existing XFS-formatted devices
- Only shows unmounted devices (safe)

### 3. Network Configuration
- Select server IP address
- Configure Varnish listening port (default: 80)
- Set Grafana admin password

### 4. Installation
**Docker Mode:**
- Generates Docker Compose configuration
- Installs `teamcache.service` (runs Docker Compose)
- Deploys all services in containers

**Hybrid Mode:**
- Installs Varnish Enterprise natively (apt/dnf/yum)
- Generates `/etc/varnish/default.vcl` and `/etc/varnish/mse4.conf`
- Creates native `teamcache.service`
- Optionally installs monitoring stack via `tc-grafana.service`

## Generated Files

### Docker Mode
```
/opt/teamcache/
├── compose.yaml              # Docker Compose configuration
├── mse4.conf                 # MSE4 storage configuration
├── varnish-enterprise.lic    # License file
└── conf/
    ├── default.vcl           # Varnish VCL configuration
    ├── grafana/              # Grafana dashboards & config
    └── prometheus.yml        # Prometheus scrape config
```

### Hybrid Mode
```
/etc/varnish/
├── default.vcl               # Varnish VCL configuration
├── mse4.conf                 # MSE4 storage configuration
└── varnish-enterprise.lic    # License file

/etc/systemd/system/
├── teamcache.service         # Native Varnish service
└── tc-grafana.service        # Monitoring service (optional)

/opt/teamcache/               # Only if monitoring enabled
├── monitoring-compose.yaml   # Monitoring stack compose
└── conf/
    ├── grafana/
    └── prometheus.yml
```

### Mount Points
```
/cache/disk1/                 # First device mount point
/cache/disk2/                 # Second device mount point
...
```

## Post-Installation

### Access Points

**TeamCache Endpoint:**
```
http://<server-ip>:80
```

**Grafana Dashboard** (if monitoring enabled):
```
http://<server-ip>:3000
User: admin
Password: <set during setup>
```

**Prometheus** (hybrid mode with monitoring):
```
http://<server-ip>:9090
```

### Service Management

**Docker Mode:**
```bash
# Check status
sudo systemctl status teamcache.service

# View logs
sudo journalctl -u teamcache.service -f
sudo docker compose -f /opt/teamcache/compose.yaml logs -f

# Restart
sudo systemctl restart teamcache.service

# Stop
sudo systemctl stop teamcache.service
```

**Hybrid Mode:**
```bash
# Varnish service
sudo systemctl status teamcache.service
sudo systemctl restart teamcache.service
sudo journalctl -u teamcache.service -f

# Monitoring service (if enabled)
sudo systemctl status tc-grafana.service
sudo systemctl restart tc-grafana.service

# View Varnish logs
sudo varnishlog
sudo varnishstat
```

## LucidLink Client Configuration

Configure all LucidLink clients to use the TeamCache:

```bash
lucid3 config --fs <filespace.domain> --global --set \
  --ObjectScheduler.SiteCacheEndpoint http://<cache-server-ip>:80
```

Clients will automatically start using the cache after reconnecting.

## Advanced Configuration

### Using Existing Formatted Disks

The setup tool can reuse already-formatted XFS devices:
1. When prompted for device preparation, select option 2
2. Choose devices that already have XFS filesystems
3. Setup will verify and mount them without formatting

### Re-running Setup

You can safely re-run the setup to:
- Add or change storage devices
- Switch deployment modes
- Update configuration
- Reinstall services

### Manual MSE4 Configuration

Edit `/etc/varnish/mse4.conf` (hybrid) or `/opt/teamcache/mse4.conf` (docker):

```
env: {
    books = ( {
        id = "book1";
        filename = "/cache/disk1/book";
        size = "8G";
        stores = ( {
            id = "store1";
            filename = "/cache/disk1/store";
            size = "905G";  # (disk_size - 8G) * 0.98
        } );
    } );
};
```

After editing, restart the service:
```bash
sudo systemctl restart teamcache.service
```

## Troubleshooting

### Service fails to start

**Check service status:**
```bash
sudo systemctl status teamcache.service
sudo journalctl -u teamcache.service -n 100
```

**Common issues:**
- License file missing or invalid
- Insufficient disk space
- Port 80 already in use
- MSE4 configuration errors

### Docker issues (Docker mode only)

```bash
# Check Docker is running
sudo systemctl status docker

# View container logs
sudo docker compose -f /opt/teamcache/compose.yaml logs

# Restart containers
sudo systemctl restart teamcache.service
```

### Varnish issues (Hybrid mode)

```bash
# Check Varnish configuration
sudo varnishd -C -f /etc/varnish/default.vcl

# Check MSE4 configuration
sudo mkfs.mse4 check-config -c /etc/varnish/mse4.conf

# View live logs
sudo varnishlog
sudo varnishstat
```

### No devices detected

The setup filters out:
- Mounted devices (check `mount` output)
- Devices smaller than 10GB
- System disks with mounted partitions

Unmount devices before running setup:
```bash
sudo umount /dev/nvme0n1
```

## Platform Support

| Distribution | Package Manager | Tested |
|--------------|----------------|--------|
| Ubuntu 20.04+ | apt-get | ✅ |
| Debian 11+ | apt-get | ✅ |
| RHEL 8+ | dnf | ✅ |
| Rocky Linux 8+ | dnf | ✅ |
| AlmaLinux 8+ | dnf | ✅ |
| Fedora | dnf | ✅ |
| CentOS 7 | yum | ✅ |

## Architecture

### Docker Mode
```
┌─────────────────────────────────────┐
│     teamcache.service (systemd)     │
│  docker compose up -d (WorkDir=/opt/teamcache)
└──────────────┬──────────────────────┘
               │
       ┌───────┴───────┐
       │ Docker Compose│
       └───────┬───────┘
               │
   ┌───────────┼───────────┐
   │           │           │
┌──▼──┐   ┌───▼────┐  ┌──▼──────┐
│Varnish│  │Prometheus│ │Grafana │
└──────┘   └────────┘  └─────────┘
```

### Hybrid Mode
```
┌──────────────────────────────────────┐
│   teamcache.service (systemd)        │
│   ExecStart=/usr/sbin/varnishd       │
│   Native Varnish (no Docker)         │
└──────────────────────────────────────┘

┌──────────────────────────────────────┐
│  tc-grafana.service (systemd)        │
│  docker compose -f monitoring-compose.yaml
└──────────┬───────────────────────────┘
           │
    ┌──────┴──────┐
┌───▼────┐  ┌────▼────┐
│Prometheus│ │Grafana │
└────────┘  └─────────┘
```

## Development

### Building Standalone Executable

```bash
./scripts/build-standalone.py
```

Creates `dist/teamcache-setup` executable (no Python required on target).

### Creating Deployment Bundle

```bash
./scripts/create-bundle.sh
```

Creates `teamcache-bundle-YYYYMMDD.tar.gz` with all dependencies.

## License

This tool is provided by LucidLink for deploying Varnish Enterprise. You must have a valid Varnish Enterprise license to use this software.

## Support

For issues or questions:
- Check logs: `/tmp/teamcache-setup-*.log`
- Contact your LucidLink Account Manager
- Review Varnish documentation: https://docs.varnish-software.com/
