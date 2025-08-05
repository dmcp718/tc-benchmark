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
├── CLAUDE.md             # AI assistant documentation
├── README.md             # This file
└── README-DEPLOYMENT.md  # End-user deployment guide
```

### Running the Setup Script

1. Clone the repository to `/opt/teamcache/`
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

#### Create a Deployment Bundle
To create a portable deployment package:

```bash
./scripts/create-bundle.sh
```

This creates `teamcache-bundle-YYYYMMDD.tar.gz` containing all necessary files for deployment.

#### Build Standalone Executable
To create a single executable file (no Python required):

```bash
./scripts/build-standalone.py
```

This uses PyInstaller to create a self-contained executable in the `dist/` directory.

#### Build Portable Package
For a portable package with bundled Python:

```bash
./scripts/build-portable.sh
```

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
