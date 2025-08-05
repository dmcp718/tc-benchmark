# TeamCache Development Guide

## Overview

TeamCache (formerly LucidLink Site Cache) is a high-performance caching solution built on Varnish Plus Enterprise with MSE4 (Massive Storage Engine). This repository contains the setup tools and configuration for deploying TeamCache.

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
├── create-bundle.sh        # Bundle creation script for deployment
├── conf/                   # Configuration templates
│   ├── default.vcl         # Varnish VCL configuration
│   ├── prometheus.yml      # Prometheus scrape configuration
│   └── grafana/            # Grafana dashboards and provisioning
├── entrypoint.sh          # Docker container entrypoint
├── testing/               # Test scripts and tools
└── CLAUDE.md             # AI assistant documentation
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

### Building a Deployment Bundle

To create a portable deployment package:

```bash
./create-bundle.sh
```

This creates `teamcache-bundle-YYYYMMDD.tar.gz` containing all necessary files for deployment.

### Testing

Test scripts are available in the `testing/` directory:
- Device detection tests
- Password dialog tests
- Service validation tests

### Development Notes

- The setup script uses Python's `rich` library for the TUI
- All logging goes to `/tmp/teamcache-setup-*.log`
- Docker images are built inline to avoid Docker Hub authentication
- The service runs as `lucid-site-cache.service` via systemd

## Manual Configuration (Legacy)

For manual setup without the interactive script, follow these steps:

1. Edit `mse4.conf` to configure storage:
   ```
   env: {
       books = ( {
           id = "book";
           filename = "/cache/disk1/book";
           size = "512M";
           stores = ( {
               id = "store";
               filename = "/cache/disk1/store";
               size = "1G";
           } );
       } );
   };
   ```

2. Configure Grafana credentials in `conf/grafana/grafana.ini`
3. Run Docker Compose:
   ```bash
   docker compose up -d
   ```

## Configuring Lucid Clients

### For Linux Users

Once our Clients are connected to the Lucid Filespace, we simply want to reroute them to go to our Site Cache first, and disable the local LucidLink Cache. 

We can do so by first running `sudo systemctl edit --full lucid.service` and editing to add a `LUCID_S3_PROXY` variable like so:

```
[Unit]
Description=lucid
Wants=network-online.target
After=network.target network-online.target

[Service]
Environment=LUCID_S3_PROXY=http://<IP_of_the_site_cache>:80/
ExecStart=/usr/local/bin/lucid --instance 2000 daemon
#PrivateTmp=true
User=root
Group=root

[Install]
WantedBy=multi-user.target
```

After that we will need to restart the `lucid.service` with `sudo systemctl restart lucid.service`, reconnect our filespace, and turn off the LucidLink cache with `lucid --instance <your_instance_ID> cache --off`.

### For Mac Users

To connect Mac users to the Site Cache, we need the users to install the provided `.pkg` file. 

Once installed, the filespace Admin needs to run:

```
lucid3 config  --fs <name_of_filespace.domain> --global --set --ObjectScheduler.SiteCacheEndpoint http://<IP_of_your_site_cache>:80
```

You will then be promted for your Admin password. Note, using `--global` will make all users connecting to the filespace use the Site Cache. Users should reconnect to their filespace once this has been made, and they will pull from the Site Cache.

If you have further questions please reach out to your LucidLink Account Manager.