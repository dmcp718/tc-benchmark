# TeamCache Automated Deployment

`teamcache-auto.py` provides non-interactive, programmatic deployment of TeamCache for use in CI/CD pipelines, Infrastructure-as-Code, and automation workflows.

## Quick Start

```bash
# Create configuration file
cat > .env << EOF
DEPLOYMENT_MODE=hybrid
ENABLE_MONITORING=true
DEVICES=/dev/sdb,/dev/sdc
DEVICE_MODE=format
SERVER_IP=192.168.1.100
VARNISH_PORT=80
GRAFANA_PASSWORD=SecurePassword123
LICENSE_FILE=./varnish-enterprise.lic
AUTO_CONFIRM=true
EOF

# Test configuration (dry-run)
sudo python3 teamcache-auto.py --env-file .env --dry-run

# Deploy
sudo python3 teamcache-auto.py --env-file .env
```

## Configuration Reference

All configuration is provided via environment variables in a `.env` file.

### Required Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `DEPLOYMENT_MODE` | Deployment mode: `hybrid` or `docker` | `hybrid` |
| `DEVICES` | Comma-separated list of block devices | `/dev/sdb,/dev/sdc` |
| `DEVICE_MODE` | How to handle devices: `format` or `reuse` | `format` |
| `SERVER_IP` | IP address for TeamCache to listen on | `192.168.1.100` |

### Optional Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `ENABLE_MONITORING` | `true` | Enable Grafana/Prometheus monitoring stack |
| `VARNISH_PORT` | `80` | Port for Varnish to listen on |
| `GRAFANA_PASSWORD` | (required if monitoring enabled) | Password for Grafana admin user |
| `LICENSE_FILE` | `./varnish-enterprise.lic` | Path to Varnish Enterprise license file |
| `AUTO_CONFIRM` | `false` | **Required to be `true` when using `DEVICE_MODE=format`** |

## Deployment Modes

### Hybrid Mode (Recommended for Production)

```bash
DEPLOYMENT_MODE=hybrid
```

- Installs Varnish Enterprise natively via package manager (apt/dnf/yum)
- Creates systemd service: `teamcache.service`
- Optional monitoring stack runs in Docker: `tc-grafana.service`
- Best performance, native process management

**Services:**
- `sudo systemctl status teamcache.service` - Varnish service
- `sudo systemctl status tc-grafana.service` - Monitoring (if enabled)

### Docker Mode

```bash
DEPLOYMENT_MODE=docker
```

- All-in-one Docker Compose deployment
- Single systemd service: `teamcache.service`
- Varnish + monitoring in containers

**Services:**
- `sudo systemctl status teamcache.service` - Entire stack
- `sudo docker compose -f /opt/teamcache/compose.yaml logs -f`

## Device Management

### Format Mode (Destructive)

```bash
DEVICE_MODE=format
AUTO_CONFIRM=true  # REQUIRED for safety
```

- Formats devices with XFS filesystem
- **DESTROYS ALL DATA** on specified devices
- Requires `AUTO_CONFIRM=true` as safety check

### Reuse Mode (Non-Destructive)

```bash
DEVICE_MODE=reuse
```

- Uses existing XFS filesystems on devices
- Devices must already be formatted with XFS
- No data loss, but cache data will be overwritten during use

## Usage Examples

### Basic Hybrid Deployment

```bash
cat > .env << 'EOF'
DEPLOYMENT_MODE=hybrid
DEVICES=/dev/sdb
DEVICE_MODE=reuse
SERVER_IP=192.168.1.100
VARNISH_PORT=80
ENABLE_MONITORING=false
LICENSE_FILE=/opt/licenses/varnish-enterprise.lic
EOF

sudo python3 teamcache-auto.py --env-file .env
```

### Multi-Device with Monitoring

```bash
cat > .env << 'EOF'
DEPLOYMENT_MODE=hybrid
DEVICES=/dev/sdb,/dev/sdc,/dev/sdd
DEVICE_MODE=format
SERVER_IP=10.0.1.50
VARNISH_PORT=80
ENABLE_MONITORING=true
GRAFANA_PASSWORD=MySecurePassword123
LICENSE_FILE=./varnish-enterprise.lic
AUTO_CONFIRM=true
EOF

sudo python3 teamcache-auto.py --env-file .env
```

### Docker All-in-One

```bash
cat > .env << 'EOF'
DEPLOYMENT_MODE=docker
DEVICES=/dev/nvme0n1
DEVICE_MODE=reuse
SERVER_IP=192.168.100.10
VARNISH_PORT=8080
ENABLE_MONITORING=true
GRAFANA_PASSWORD=grafana123
EOF

sudo python3 teamcache-auto.py --env-file .env
```

### Dry Run (Test Configuration)

```bash
sudo python3 teamcache-auto.py --env-file .env --dry-run
```

Shows what would be done without making any changes:
- Device validation
- Configuration file generation
- Service installation steps

## Validation and Safety

The script performs extensive validation before making changes:

1. **Root privileges check** - Must run with sudo
2. **Device existence** - All specified devices must exist
3. **Configuration completeness** - All required parameters present
4. **Format safety check** - `AUTO_CONFIRM=true` required for destructive operations
5. **License file check** - Warns if license file missing (not fatal)

### Common Validation Errors

**Missing AUTO_CONFIRM:**
```
DEVICE_MODE=format requires AUTO_CONFIRM=true (destructive operation)
```
Fix: Add `AUTO_CONFIRM=true` to your `.env` file

**Device not found:**
```
Device not found: /dev/sdb
```
Fix: Verify device path with `lsblk` and update `.env`

**Missing GRAFANA_PASSWORD:**
```
GRAFANA_PASSWORD is required when ENABLE_MONITORING=true
```
Fix: Add `GRAFANA_PASSWORD=<password>` or set `ENABLE_MONITORING=false`

## Logs and Troubleshooting

### Deployment Logs

All deployment activity is logged to:
```
/tmp/teamcache-auto-YYYYMMDD-HHMMSS.log
```

Log location is shown at the end of deployment:
```
Log file: /tmp/teamcache-auto-20251004-143022.log
```

### Service Logs

**Hybrid mode - Varnish:**
```bash
sudo journalctl -u teamcache.service -f
sudo varnishlog
sudo varnishstat
```

**Hybrid mode - Monitoring:**
```bash
sudo journalctl -u tc-grafana.service -f
```

**Docker mode:**
```bash
sudo journalctl -u teamcache.service -f
sudo docker compose -f /opt/teamcache/compose.yaml logs -f
```

### Common Issues

**Service fails to start:**
```bash
# Check service status
sudo systemctl status teamcache.service

# View recent logs
sudo journalctl -u teamcache.service -n 50

# Verify configuration syntax
sudo varnishd -C -f /etc/varnish/default.vcl
sudo mkfs.mse4 check-config -c /etc/varnish/mse4.conf
```

**Device mounting fails:**
```bash
# Check if device is already mounted
lsblk
mount | grep /cache

# Verify filesystem
sudo blkid /dev/sdb
```

**License issues:**
```bash
# Verify license file location
ls -la /etc/varnish/varnish-enterprise.lic

# Check Varnish can read it
sudo -u varnish cat /etc/varnish/varnish-enterprise.lic
```

## Platform Support

Tested on:
- **Ubuntu 22.04 / 24.04** (apt-get)
- **Rocky Linux 9** (dnf)
- **AlmaLinux 9** (dnf)
- **RHEL 9** (dnf)
- **CentOS 7** (yum - legacy)
- **Debian 11/12** (apt-get)

The script automatically detects the package manager and uses the appropriate installation method.

## Output Files and Locations

### Hybrid Mode

```
/etc/varnish/
├── default.vcl                    # VCL configuration
├── mse4.conf                      # MSE4 storage configuration
├── varnish-enterprise.lic         # License file (copied)
└── secret                         # Admin secret (auto-generated)

/etc/systemd/system/
├── teamcache.service              # Varnish service
└── tc-grafana.service             # Monitoring service (if enabled)

/cache/
├── disk1/                         # First device mount
├── disk2/                         # Second device mount
└── ...

/opt/teamcache/                    # Only if monitoring enabled
└── monitoring-compose.yaml        # Monitoring stack compose file
```

### Docker Mode

```
/opt/teamcache/
├── compose.yaml                   # Full stack Docker Compose
├── varnish-enterprise.lic         # License file (copied)
└── conf/                          # Configuration files
    ├── default.vcl
    ├── mse4.conf
    └── ...

/etc/systemd/system/
└── teamcache.service              # Docker Compose service

/cache/
├── disk1/                         # First device mount
├── disk2/                         # Second device mount
└── ...
```

## CI/CD Integration Examples

### Terraform

```hcl
resource "null_resource" "teamcache_deployment" {
  provisioner "file" {
    content = templatefile("${path.module}/teamcache.env.tpl", {
      server_ip = aws_instance.cache.private_ip
      devices   = join(",", local.cache_devices)
    })
    destination = "/tmp/teamcache.env"
  }

  provisioner "remote-exec" {
    inline = [
      "sudo python3 /opt/teamcache-setup/teamcache-auto.py --env-file /tmp/teamcache.env"
    ]
  }
}
```

### Ansible

```yaml
- name: Deploy TeamCache
  hosts: cache_servers
  become: yes
  tasks:
    - name: Create TeamCache configuration
      template:
        src: teamcache.env.j2
        dest: /tmp/teamcache.env
        mode: '0600'

    - name: Run TeamCache automation
      command: python3 /opt/teamcache-setup/teamcache-auto.py --env-file /tmp/teamcache.env
      register: deployment_result

    - name: Verify service is running
      systemd:
        name: teamcache.service
        state: started
        enabled: yes
```

### GitHub Actions

```yaml
- name: Deploy TeamCache
  run: |
    cat > .env << EOF
    DEPLOYMENT_MODE=hybrid
    DEVICES=${{ secrets.CACHE_DEVICES }}
    DEVICE_MODE=reuse
    SERVER_IP=${{ secrets.SERVER_IP }}
    ENABLE_MONITORING=false
    EOF

    sudo python3 teamcache-auto.py --env-file .env
```

## Comparison: Interactive vs Automated

| Feature | teamcache-setup.py (TUI) | teamcache-auto.py (CLI) |
|---------|--------------------------|-------------------------|
| User interaction | Interactive prompts | Environment file |
| Device selection | Visual selector | Comma-separated list |
| Validation | Real-time feedback | Upfront validation |
| Use case | Manual installation | CI/CD, automation |
| Configuration | In-app choices | .env file |
| Dry-run | No | Yes (`--dry-run`) |

## Security Considerations

1. **Environment files contain sensitive data:**
   - Store `.env` files securely
   - Use `.gitignore` to exclude from version control
   - Set appropriate file permissions: `chmod 600 .env`

2. **License file security:**
   - Keep license file in secure location
   - Limit read access to root user

3. **Grafana password:**
   - Use strong passwords
   - Store in secrets management (Vault, AWS Secrets Manager, etc.)
   - Rotate regularly

4. **AUTO_CONFIRM flag:**
   - Only set to `true` when you're certain about device formatting
   - Double-check device paths before running

## See Also

- **README.md** - Main interactive TUI documentation
- **CLAUDE.md** - Development and architecture documentation
- **conf/** - Configuration templates and examples
