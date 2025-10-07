#!/usr/bin/env python3
"""
TeamCache Auto - Non-interactive automated deployment for TeamCache

This script provides programmatic deployment without user interaction:
- Reads configuration from .env file
- Validates all parameters upfront
- Deploys TeamCache in docker or hybrid mode
- Designed for CI/CD, IaC, and automation workflows

Run with: sudo python3 teamcache-auto.py --env-file .env
"""

import os
import sys
import json
import subprocess
import shutil
import argparse
import time
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

# Setup logging
import logging
log_file = f"/tmp/teamcache-auto-{datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class TeamCacheAuto:
    def __init__(self, config: Dict[str, str], dry_run: bool = False):
        self.config = config
        self.dry_run = dry_run
        self.script_dir = Path(__file__).parent.absolute()

        # Parse configuration
        self.deployment_mode = config.get('DEPLOYMENT_MODE', 'hybrid').lower()
        self.enable_monitoring = config.get('ENABLE_MONITORING', 'true').lower() == 'true'
        self.device_paths = [d.strip() for d in config.get('DEVICES', '').split(',') if d.strip()]
        self.device_mode = config.get('DEVICE_MODE', 'format').lower()
        self.storage_mode = config.get('STORAGE_MODE', 'raw_disk').lower()
        self.server_ip = config.get('SERVER_IP', '')
        self.varnish_port = int(config.get('VARNISH_PORT', '80'))
        self.grafana_password = config.get('GRAFANA_PASSWORD', '')
        self.license_file = config.get('LICENSE_FILE', './varnish-enterprise.lic')
        self.auto_confirm = config.get('AUTO_CONFIRM', 'false').lower() == 'true'

        # Runtime state
        self.selected_devices = []
        self.mount_points = []

    def validate_config(self) -> bool:
        """Validate all required configuration is present"""
        logger.info("Validating configuration...")
        errors = []

        # Required fields
        if not self.device_paths:
            errors.append("DEVICES is required (comma-separated device paths)")

        if not self.server_ip:
            errors.append("SERVER_IP is required")

        if self.enable_monitoring and not self.grafana_password:
            errors.append("GRAFANA_PASSWORD is required when ENABLE_MONITORING=true")

        # Validate deployment mode
        if self.deployment_mode not in ['docker', 'hybrid']:
            errors.append(f"DEPLOYMENT_MODE must be 'docker' or 'hybrid', got '{self.deployment_mode}'")

        # Validate storage mode
        if self.storage_mode not in ['raw_disk', 'filepath']:
            errors.append(f"STORAGE_MODE must be 'raw_disk' or 'filepath', got '{self.storage_mode}'")

        # Validate device mode (only for raw_disk)
        if self.storage_mode == 'raw_disk':
            if self.device_mode not in ['format', 'reuse']:
                errors.append(f"DEVICE_MODE must be 'format' or 'reuse', got '{self.device_mode}'")

        # Check devices/paths exist
        if self.storage_mode == 'raw_disk':
            for device_path in self.device_paths:
                if not Path(device_path).exists():
                    errors.append(f"Device not found: {device_path}")
        else:
            # Filepath mode - check parent directories exist
            for path_str in self.device_paths:
                path = Path(path_str)
                if not path.is_absolute():
                    errors.append(f"Path must be absolute: {path_str}")
                elif not path.exists() and not path.parent.exists():
                    errors.append(f"Parent directory does not exist for: {path_str}")

        # Check license file
        license_path = Path(self.license_file)
        if not license_path.exists():
            logger.warning(f"License file not found: {self.license_file}")
            logger.warning("Service may fail to start without valid license")

        # Safety check for format mode (only for raw_disk)
        if self.storage_mode == 'raw_disk' and self.device_mode == 'format' and not self.auto_confirm:
            errors.append("DEVICE_MODE=format requires AUTO_CONFIRM=true (destructive operation)")

        if errors:
            logger.error("Configuration validation failed:")
            for error in errors:
                logger.error(f"  - {error}")
            return False

        logger.info("✓ Configuration validated successfully")
        return True

    def check_root_privileges(self) -> bool:
        """Check if running as root"""
        if os.geteuid() != 0:
            logger.error("This script must be run as root")
            logger.error("Please run: sudo python3 teamcache-auto.py --env-file .env")
            return False
        return True

    def get_device_info(self, device_path: str) -> Optional[Dict]:
        """Get device information"""
        try:
            # Get device size
            size_result = subprocess.run(
                ['lsblk', '-dbno', 'SIZE', device_path],
                capture_output=True, text=True, check=True
            )
            size_bytes = int(size_result.stdout.strip())

            # Get device size in human readable format
            size_result_hr = subprocess.run(
                ['lsblk', '-hno', 'SIZE', device_path],
                capture_output=True, text=True, check=True
            )
            size_hr = size_result_hr.stdout.strip()

            # Get filesystem type
            fs_result = subprocess.run(
                ['lsblk', '-no', 'FSTYPE', device_path],
                capture_output=True, text=True
            )
            fstype = fs_result.stdout.strip()

            # Get UUID if formatted
            uuid = None
            if fstype:
                uuid_result = subprocess.run(
                    ['blkid', '-s', 'UUID', '-o', 'value', device_path],
                    capture_output=True, text=True
                )
                uuid = uuid_result.stdout.strip()

            return {
                'path': device_path,
                'size': size_hr,
                'size_bytes': size_bytes,
                'fstype': fstype,
                'uuid': uuid
            }
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to get info for {device_path}: {e}")
            return None

    def format_device_xfs(self, device_path: str) -> bool:
        """Format a device with XFS"""
        if self.dry_run:
            logger.info(f"[DRY RUN] Would format {device_path} with XFS")
            return True

        logger.info(f"Formatting {device_path} with XFS...")
        try:
            result = subprocess.run(
                ['mkfs.xfs', '-f', device_path],
                capture_output=True, text=True, check=True
            )
            logger.info(f"✓ Formatted {device_path}")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to format {device_path}: {e.stderr}")
            return False

    def mount_device(self, device_info: Dict, mount_point: str) -> bool:
        """Mount a device"""
        if self.dry_run:
            logger.info(f"[DRY RUN] Would mount {device_info['path']} at {mount_point}")
            return True

        # Create mount point
        Path(mount_point).mkdir(parents=True, exist_ok=True)

        # Add to fstab
        with open('/etc/fstab', 'a') as f:
            f.write(f"UUID={device_info['uuid']} {mount_point} xfs defaults,noatime 0 2\n")

        # Reload systemd
        subprocess.run(['systemctl', 'daemon-reload'], capture_output=True)

        # Mount
        result = subprocess.run(
            ['mount', mount_point],
            capture_output=True, text=True
        )

        if result.returncode == 0:
            logger.info(f"✓ Mounted {device_info['path']} at {mount_point}")

            # Set ownership and SELinux context for hybrid mode
            if self.deployment_mode == 'hybrid':
                subprocess.run(['chown', '-R', 'varnish:varnish', mount_point], capture_output=True)
                subprocess.run(['semanage', 'fcontext', '-a', '-t', 'varnishd_var_lib_t', f'{mount_point}(/.*)?'], capture_output=True)
                subprocess.run(['restorecon', '-R', mount_point], capture_output=True)

            return True
        else:
            logger.error(f"Failed to mount {mount_point}: {result.stderr}")
            return False

    def generate_mse4_config(self) -> bool:
        """Generate MSE4 configuration"""
        if self.deployment_mode == "hybrid":
            config_path = Path('/etc/varnish/mse4.conf')
            config_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            config_path = self.script_dir / "mse4.conf"

        if self.dry_run:
            logger.info(f"[DRY RUN] Would generate MSE4 config at {config_path}")
            return True

        book_size = "8G"
        config_content = f"""# MSE4 Configuration
# Generated by teamcache-auto on {datetime.now()}
# Number of devices: {len(self.selected_devices)}

env: {{
        books = ( {{
"""

        for i, device in enumerate(self.selected_devices, 1):
            disk_size_gb = device['size_bytes'] / (1024**3)
            store_size_gb = int((disk_size_gb - 8) * 0.98)

            # Use different paths based on storage mode and deployment mode
            if self.storage_mode == 'filepath':
                base_path = device['path']
            elif self.deployment_mode == "hybrid":
                base_path = f"/cache/disk{i}"
            else:
                base_path = f"/mnt/disk{i}"

            config_content += f"""                id = "book{i}";
                filename = "{base_path}/book";
                size = "{book_size}";

                stores = ( {{
                        id = "store{i}";
                        filename = "{base_path}/store";
                        size = "{store_size_gb}G";
                }} );
"""
            if i < len(self.selected_devices):
                config_content += """        }, {
"""

        config_content += """        } );
   };
"""

        with open(config_path, 'w') as f:
            f.write(config_content)

        logger.info(f"✓ Generated MSE4 config at {config_path}")
        return True

    def generate_varnish_service(self) -> bool:
        """Generate teamcache.service for hybrid mode"""
        if self.deployment_mode != "hybrid":
            return True

        service_path = Path('/etc/systemd/system/teamcache.service')

        if self.dry_run:
            logger.info(f"[DRY RUN] Would generate service file at {service_path}")
            return True

        # Build the ownership/SELinux command for all mount points
        if self.mount_points:
            # Create explicit list of directories to fix
            dir_list = ' '.join([f'"{mp}"' for mp in self.mount_points])
            ownership_cmd = f"for dir in {dir_list}; do [ -d \"$dir\" ] && chown -R varnish:varnish \"$dir\" && restorecon -R \"$dir\"; done"
        else:
            # Fallback to pattern matching (raw disk mode default)
            ownership_cmd = 'for dir in /cache/disk*; do [ -d "$dir" ] && chown -R varnish:varnish "$dir" && restorecon -R "$dir"; done'

        service_content = f"""[Unit]
Description=Varnish Cache Plus, a high-performance HTTP accelerator
After=network-online.target nss-lookup.target

[Service]
Type=forking
KillMode=process

LimitNOFILE=131072
LimitMEMLOCK=100M
TasksMax=infinity
LimitCORE=infinity
LimitNPROC=infinity
TimeoutStartSec=720
TimeoutStopSec=300

# Configure MSE4 storage (creates book and store files as root)
ExecStartPre=/usr/bin/mkfs.mse4 -c /etc/varnish/mse4.conf configure
# Fix ownership and SELinux context after mkfs.mse4 creates files
ExecStartPre=/usr/bin/bash -c '{ownership_cmd}'

ExecStart=/usr/sbin/varnishd \\
	  -a :{self.varnish_port} \\
	  -T localhost:6082 \\
	  -S /etc/varnish/secret \\
	  -L /etc/varnish/varnish-enterprise.lic \\
	  -p feature=+http2 \\
	  -p thread_pool_max=1000 \\
	  -p thread_pool_min=50 \\
	  -r vcc_allow_inline_c \\
	  -r allow_exec \\
	  -f /etc/varnish/default.vcl \\
	  -s mse4,/etc/varnish/mse4.conf
ExecReload=/usr/sbin/varnishreload

[Install]
WantedBy=multi-user.target
"""

        with open(service_path, 'w') as f:
            f.write(service_content)

        logger.info(f"✓ Generated service file at {service_path}")
        return True

    def install_varnish_native(self) -> bool:
        """Install Varnish Plus for hybrid mode"""
        if self.deployment_mode != "hybrid":
            return True

        # Check if already installed
        if shutil.which('varnishd'):
            logger.info("✓ Varnish already installed, skipping")
            return True

        if self.dry_run:
            logger.info("[DRY RUN] Would install Varnish Enterprise")
            return True

        logger.info("Installing Varnish Enterprise...")

        try:
            if shutil.which('dnf'):
                # RHEL/Rocky/AlmaLinux
                subprocess.run(['dnf', '-y', 'install', 'curl', 'gnupg2', 'yum-utils', 'epel-release'], check=True, capture_output=True)
                subprocess.run(['dnf', '-y', 'install', 'libunwind', 'isa-l'], check=True, capture_output=True)
                subprocess.run('curl -s https://packagecloud.io/install/repositories/varnishplus/60-enterprise/script.rpm.sh | bash', shell=True, check=True, capture_output=True)
                subprocess.run(['dnf', '-y', 'install', 'varnish-plus', '--allowerasing'], check=True, capture_output=True)
            elif shutil.which('apt-get'):
                # Debian/Ubuntu
                subprocess.run(['apt-get', 'update'], check=True, capture_output=True)
                subprocess.run(['apt-get', 'install', '-y', 'curl', 'gnupg', 'apt-transport-https'], check=True, capture_output=True)
                subprocess.run('curl -s https://packagecloud.io/install/repositories/varnishplus/60-enterprise/script.deb.sh | bash', shell=True, check=True, capture_output=True)
                subprocess.run(['apt-get', 'install', '-y', 'varnish-plus'], check=True, capture_output=True)
            else:
                logger.error("Unsupported package manager")
                return False

            logger.info("✓ Varnish Enterprise installed")

            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to install Varnish: {e}")
            return False

    def copy_vcl_config(self) -> bool:
        """Copy VCL configuration for hybrid mode"""
        if self.deployment_mode != "hybrid":
            return True

        vcl_source = self.script_dir / "conf" / "default.vcl"
        vcl_dest = Path('/etc/varnish/default.vcl')

        if self.dry_run:
            logger.info(f"[DRY RUN] Would copy VCL from {vcl_source} to {vcl_dest}")
            return True

        if not vcl_source.exists():
            logger.error(f"VCL source file not found: {vcl_source}")
            return False

        vcl_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(vcl_source, vcl_dest)
        logger.info(f"✓ Copied VCL config to {vcl_dest}")
        return True

    def copy_license_file(self) -> bool:
        """Copy license file"""
        license_source = Path(self.license_file)

        if self.deployment_mode == "hybrid":
            license_dest = Path('/etc/varnish/varnish-enterprise.lic')
        else:
            license_dest = self.script_dir / "varnish-enterprise.lic"

        if self.dry_run:
            logger.info(f"[DRY RUN] Would copy license from {license_source} to {license_dest}")
            return True

        if not license_source.exists():
            logger.warning(f"License file not found: {license_source}")
            return True  # Don't fail, just warn

        license_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(license_source, license_dest)
        logger.info(f"✓ Copied license file to {license_dest}")
        return True

    def start_service(self) -> bool:
        """Enable and start the TeamCache service"""
        if self.dry_run:
            logger.info("[DRY RUN] Would enable and start teamcache.service")
            return True

        try:
            subprocess.run(['systemctl', 'daemon-reload'], check=True)
            subprocess.run(['systemctl', 'enable', 'teamcache.service'], check=True)
            subprocess.run(['systemctl', 'start', 'teamcache.service'], check=True)

            # Wait and check status
            time.sleep(2)
            result = subprocess.run(['systemctl', 'is-active', 'teamcache.service'], capture_output=True, text=True)

            if result.stdout.strip() == 'active':
                logger.info("✓ TeamCache service is running")
                return True
            else:
                logger.error("TeamCache service failed to start")
                logger.error("Check logs with: sudo journalctl -u teamcache.service -n 50")
                return False
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to start service: {e}")
            return False

    def run(self) -> bool:
        """Main deployment workflow"""
        logger.info("=" * 60)
        logger.info("TeamCache Automated Deployment")
        logger.info("=" * 60)

        # Validate
        if not self.check_root_privileges():
            return False

        if not self.validate_config():
            return False

        # Prepare storage
        if self.storage_mode == 'filepath':
            logger.info(f"\nPreparing {len(self.device_paths)} storage path(s)...")
            for i, path_str in enumerate(self.device_paths, 1):
                path = Path(path_str)

                # Create directory if it doesn't exist
                if not path.exists():
                    if self.dry_run:
                        logger.info(f"[DRY RUN] Would create directory {path}")
                    else:
                        try:
                            path.mkdir(parents=True, exist_ok=True)
                            logger.info(f"✓ Created directory {path}")
                        except Exception as e:
                            logger.error(f"Failed to create directory {path}: {e}")
                            return False
                else:
                    logger.info(f"✓ Using existing directory {path}")

                # Get available space
                stat = os.statvfs(path if path.exists() else path.parent)
                available_bytes = stat.f_bavail * stat.f_frsize

                storage_info = {
                    'path': str(path),
                    'size': f"{available_bytes / (1024**3):.1f}G",
                    'size_bytes': available_bytes,
                    'type': 'filepath'
                }

                self.selected_devices.append(storage_info)
                self.mount_points.append(str(path))

                # Set ownership for hybrid mode
                if self.deployment_mode == "hybrid" and not self.dry_run:
                    subprocess.run(['chown', '-R', 'varnish:varnish', str(path)], capture_output=True)

                    # Add SELinux file context rule for this path AND its parent directories
                    # This ensures varnishd can traverse the directory tree
                    parent_path = path.parent
                    subprocess.run(['semanage', 'fcontext', '-a', '-t', 'varnishd_var_lib_t', f'{parent_path}(/.*)?'], capture_output=True)
                    subprocess.run(['semanage', 'fcontext', '-a', '-t', 'varnishd_var_lib_t', f'{path}(/.*)?'], capture_output=True)

                    # Apply the context to parent and path
                    subprocess.run(['restorecon', '-R', str(parent_path)], capture_output=True)
                    subprocess.run(['restorecon', '-R', str(path)], capture_output=True)

        else:
            # Raw disk mode
            logger.info(f"\nPreparing {len(self.device_paths)} device(s)...")
            for i, device_path in enumerate(self.device_paths, 1):
                device_info = self.get_device_info(device_path)
                if not device_info:
                    return False

                # Format if requested
                if self.device_mode == 'format':
                    if not self.format_device_xfs(device_path):
                        return False
                    # Refresh device info after format
                    device_info = self.get_device_info(device_path)

                self.selected_devices.append(device_info)

                # Mount
                mount_point = f"/cache/disk{i}"
                self.mount_points.append(mount_point)
                if not self.mount_device(device_info, mount_point):
                    return False

        # Generate configs
        logger.info("\nGenerating configuration files...")
        if not self.generate_mse4_config():
            return False

        if not self.copy_vcl_config():
            return False

        if not self.copy_license_file():
            return False

        if not self.generate_varnish_service():
            return False

        # Install and start
        if self.deployment_mode == "hybrid":
            logger.info("\nInstalling Varnish Enterprise...")
            if not self.install_varnish_native():
                return False

            logger.info("\nStarting TeamCache service...")
            if not self.start_service():
                return False

        # Summary
        logger.info("\n" + "=" * 60)
        logger.info("Deployment Complete!")
        logger.info("=" * 60)
        logger.info(f"Mode: {self.deployment_mode}")
        logger.info(f"Devices: {len(self.selected_devices)}")
        logger.info(f"TeamCache endpoint: http://{self.server_ip}:{self.varnish_port}")
        if self.enable_monitoring:
            logger.info(f"Grafana: http://{self.server_ip}:3000")
        logger.info(f"Log file: {log_file}")

        return True


def load_env_file(env_path: str) -> Dict[str, str]:
    """Load configuration from .env file"""
    config = {}
    env_file = Path(env_path)

    if not env_file.exists():
        logger.error(f"Environment file not found: {env_path}")
        sys.exit(1)

    with open(env_file, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                if '=' in line:
                    key, value = line.split('=', 1)
                    config[key.strip()] = value.strip()

    return config


def main():
    parser = argparse.ArgumentParser(description='TeamCache Automated Deployment')
    parser.add_argument('--env-file', default='.env', help='Path to .env configuration file (default: .env)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without making changes')
    args = parser.parse_args()

    # Load configuration
    config = load_env_file(args.env_file)

    # Run deployment
    deployer = TeamCacheAuto(config, dry_run=args.dry_run)
    success = deployer.run()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
