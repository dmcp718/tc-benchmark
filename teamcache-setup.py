#!/usr/bin/env python3
"""
TeamCache Setup - Interactive TUI for TeamCache deployment configuration

This script provides an interactive interface to:
1. Select block devices for TeamCache storage
2. Format them with XFS
3. Generate mse4.conf and compose.yaml files
4. Install and start the systemd service

Run with: sudo python3 teamcache-setup.py
"""

import os
import sys
import json
import subprocess
import shutil
import time
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple, Optional

# Rich imports for TUI
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.prompt import Prompt, Confirm
from rich.panel import Panel
from rich.layout import Layout
from rich.text import Text
from rich import box
import logging

# Setup logging to file only (no console output to avoid interfering with UI)
log_file = f"/tmp/teamcache-setup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_file)
    ]
)
logger = logging.getLogger(__name__)
console = Console()

class TeamCacheSetup:
    def __init__(self):
        self.script_dir = Path(__file__).parent.absolute()
        self.selected_devices = []
        self.mount_points = []
        self.grafana_password = ""
        self.server_ip = ""
        self.varnish_port = 80
        
        # Modern blue color palette - subtle and professional
        self.colors = {
            'primary': '#3b82f6',      # Medium blue (main brand color)
            'primary_light': '#93bbfc', # Light blue (subtle highlights)
            'primary_dark': '#1e3a8a',  # Dark blue (emphasis)
            'accent': '#93bbfc',        # Light blue (interactive elements)
            'success': '#10b981',       # Muted green
            'warning': '#f59e0b',       # Muted amber
            'error': '#ef4444',         # Muted red
            'info': '#6b7280',          # Gray (informational text)
            'muted': '#9ca3af',         # Light gray (secondary text)
            'border': '#e5e7eb',        # Very light gray (borders)
        }
        
    def check_root_privileges(self):
        """Check if running as root"""
        if os.geteuid() != 0:
            console.print("[bold #ef4444]Error: This script must be run as root[/bold #ef4444]")
            console.print("[#f59e0b]Please run: sudo python3 teamcache-setup.py[/#f59e0b]")
            sys.exit(1)
    
    def check_dependencies(self):
        """Check for required system dependencies"""
        missing = []
        for cmd in ['lsblk', 'mkfs.xfs', 'blkid', 'systemctl']:
            if not shutil.which(cmd):
                missing.append(cmd)
        
        if missing:
            console.print(f"[bold #ef4444]Error: Missing required dependencies:[/bold #ef4444] {', '.join(missing)}")
            sys.exit(1)
    
    def get_block_devices(self) -> List[Dict]:
        """Get list of block devices with details"""
        try:
            result = subprocess.run(
                ['lsblk', '-Jo', 'path,size,fstype,mountpoint,model,type'],
                capture_output=True, text=True, check=True
            )
            data = json.loads(result.stdout)
            
            devices = []
            for device in data['blockdevices']:
                # Skip if not a disk type
                if device.get('type') != 'disk':
                    continue
                    
                # Skip if device has mounted partitions
                # We'll check this differently since 'children' field might not be available
                has_mounted = False
                
                # Get partitions of this device
                part_result = subprocess.run(
                    ['lsblk', '-lno', 'PATH,MOUNTPOINT', device['path']],
                    capture_output=True, text=True
                )
                
                if part_result.returncode == 0:
                    lines = part_result.stdout.strip().split('\n')
                    # Skip the first line (the device itself) and check partitions
                    for line in lines[1:]:
                        parts = line.split(None, 1)
                        if len(parts) == 2 and parts[1]:  # Has a mountpoint
                            has_mounted = True
                            logger.info(f"Device {device['path']} has mounted partition {parts[0]} at {parts[1]}")
                            break
                
                if not has_mounted and device['path']:
                    # Get size in bytes for filtering (use -d to get only device, not partitions)
                    size_result = subprocess.run(
                        ['lsblk', '-dbno', 'SIZE', device['path']],
                        capture_output=True, text=True
                    )
                    size_bytes = int(size_result.stdout.strip()) if size_result.stdout.strip() else 0
                    
                    # Skip small devices (less than 10GB)
                    if size_bytes >= 10 * 1024 * 1024 * 1024:
                        devices.append({
                            'path': device['path'],
                            'size': device.get('size', 'Unknown'),
                            'model': device.get('model', 'Unknown').strip(),
                            'fstype': device.get('fstype', ''),
                            'size_bytes': size_bytes
                        })
                    else:
                        logger.info(f"Skipping {device['path']} - too small (< 10GB)")
                        
            return devices
            
        except subprocess.CalledProcessError as e:
            console.print(f"[bold #ef4444]Error getting block devices:[/bold #ef4444] {e}")
            return []
    
    def display_device_selector(self, devices: List[Dict]) -> List[Dict]:
        """Display device selection interface"""
        if not devices:
            console.print(Panel(
                "No suitable block devices found.\n\n"
                "Make sure you have unmounted devices available for formatting.",
                title="[bold #ef4444]No Devices Available[/bold #ef4444]",
                border_style="#ef4444"
            ))
            return []
        
        # Create device selection table with subtle blue theme
        table = Table(
            title="Available Block Devices",
            box=box.ROUNDED,
            title_style="#3b82f6",
            header_style="#1e3a8a",
            border_style="#9ca3af"
        )
        
        table.add_column("Index", style="#6b7280", justify="center")
        table.add_column("Device", style="#1e3a8a")
        table.add_column("Size", style="#6b7280", justify="right")
        table.add_column("Model", style="#6b7280")
        table.add_column("Current FS", style="#9ca3af")
        
        for i, device in enumerate(devices):
            table.add_row(
                str(i + 1),
                device['path'],
                device['size'],
                device['model'] or "Unknown",
                device['fstype'] or "None"
            )
        
        console.print("\n")
        # Display table without extra panel since it has its own borders
        console.print(table)
        console.print("\n")
        
        # Get selection
        console.print("[bold #f59e0b]WARNING: Selected devices will be COMPLETELY ERASED![/bold #f59e0b]\n")
        
        while True:
            selection = Prompt.ask(
                "Select devices to format (comma-separated numbers, e.g., 1,3)",
                default="1"
            )
            
            try:
                indices = [int(x.strip()) - 1 for x in selection.split(',')]
                selected = []
                
                for idx in indices:
                    if 0 <= idx < len(devices):
                        selected.append(devices[idx])
                    else:
                        raise ValueError(f"Invalid device number: {idx + 1}")
                
                if selected:
                    return selected
                    
            except (ValueError, IndexError) as e:
                console.print(f"[#ef4444]Invalid selection: {e}[/#ef4444]")
    
    def confirm_device_selection(self, devices: List[Dict]) -> bool:
        """Show confirmation dialog for device selection"""
        console.print("\n")
        
        # Create device list content
        device_list = "Selected devices for formatting:\n\n"
        for device in devices:
            device_list += f"  • {device['path']} [#9ca3af](Size: {device['size']}, Model: {device['model']})[/#9ca3af]\n"
        
        console.print(Panel(
            device_list,
            title="Device Selection",
            border_style="#9ca3af",
            padding=(1, 2)
        ))
        
        console.print("\n")
        
        warning_panel = Panel(
            "[bold #ef4444]⚠️  WARNING ⚠️[/bold #ef4444]\n\n"
            "ALL DATA ON THE SELECTED DEVICES WILL BE PERMANENTLY DESTROYED!\n\n"
            "[#9ca3af]This action cannot be undone. Please ensure you have selected the correct devices.[/#9ca3af]",
            border_style="#ef4444",
            title="Data Loss Warning",
            padding=(1, 2)
        )
        console.print(warning_panel)
        
        console.print("\n")
        
        return Confirm.ask("[bold]Are you absolutely sure you want to continue?[/bold]", default=False)
    
    def format_devices_xfs(self, devices: List[Dict]) -> bool:
        """Format devices with XFS filesystem"""
        console.print("\n")
        console.print(Panel(
            "Formatting Devices\n\n"
            "[#9ca3af]Creating XFS filesystems on selected devices...[/#9ca3af]",
            border_style="#9ca3af",
            padding=(0, 2)
        ))
        console.print("\n")
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console
        ) as progress:
            
            task = progress.add_task("Formatting devices", total=len(devices))
            
            for device in devices:
                progress.update(task, description=f"Formatting {device['path']}...")
                
                # Wipe existing filesystem signatures
                logger.info(f"Wiping {device['path']}...")
                wipe_result = subprocess.run(
                    ['wipefs', '-a', device['path']],
                    capture_output=True, text=True
                )
                
                if wipe_result.returncode != 0:
                    console.print(f"[#ef4444]Failed to wipe {device['path']}: {wipe_result.stderr}[/#ef4444]")
                    return False
                
                # Create XFS filesystem
                logger.info(f"Creating XFS filesystem on {device['path']}...")
                mkfs_result = subprocess.run(
                    ['mkfs.xfs', '-f', device['path']],
                    capture_output=True, text=True
                )
                
                if mkfs_result.returncode != 0:
                    console.print(f"[#ef4444]Failed to format {device['path']}: {mkfs_result.stderr}[/#ef4444]")
                    return False
                
                # Verify filesystem was created
                time.sleep(1)
                uuid_result = subprocess.run(
                    ['blkid', '-s', 'UUID', '-o', 'value', device['path']],
                    capture_output=True, text=True
                )
                
                uuid = uuid_result.stdout.strip()
                if not uuid:
                    console.print(f"[#ef4444]Failed to verify filesystem on {device['path']}[/#ef4444]")
                    return False
                
                device['uuid'] = uuid
                logger.info(f"Successfully created XFS filesystem on {device['path']} with UUID={uuid}")
                
                progress.advance(task)
                time.sleep(0.5)
        
        # Add extra newline after progress completes to separate from success message
        console.print("")
        console.print("[#10b981]✓ All devices formatted successfully![/#10b981]\n")
        return True
    
    def create_mount_points(self) -> bool:
        """Create mount points and update /etc/fstab"""
        console.print(Panel(
            "Setting Up Mount Points\n\n"
            "[#9ca3af]Creating mount directories and updating system configuration...[/#9ca3af]",
            border_style="#9ca3af",
            padding=(0, 2)
        ))
        console.print("\n")
        
        self.mount_points = []
        
        for i, device in enumerate(self.selected_devices, 1):
            mount_point = f"/cache/disk{i}"
            self.mount_points.append(mount_point)
            
            # Create mount point directory
            Path(mount_point).mkdir(parents=True, exist_ok=True)
            logger.info(f"Created mount point: {mount_point}")
            
            # Remove any existing fstab entries for this mount point
            self.cleanup_fstab_entry(mount_point)
            
            # Add to /etc/fstab
            with open('/etc/fstab', 'a') as f:
                f.write(f"UUID={device['uuid']} {mount_point} xfs defaults,noatime 0 2\n")
            logger.info(f"Added {device['path']} to /etc/fstab")
            
            # Reload systemd
            subprocess.run(['systemctl', 'daemon-reload'], capture_output=True)
            
            # Mount the device
            mount_result = subprocess.run(
                ['mount', mount_point],
                capture_output=True, text=True
            )
            
            if mount_result.returncode != 0:
                console.print(f"[#f59e0b]Warning: Failed to mount {mount_point}[/#f59e0b]")
                # Try direct mount as fallback
                mount_result = subprocess.run(
                    ['mount', device['path'], mount_point],
                    capture_output=True, text=True
                )
            
            if mount_result.returncode == 0:
                console.print(f"  [#10b981]✓[/#10b981] Mounted {device['path']} at {mount_point}")
            else:
                console.print(f"  [#ef4444]✗[/#ef4444] Failed to mount {device['path']}")
                logger.error(f"Mount failed: {mount_result.stderr}")
        
        # Add spacing after mount operations complete
        console.print("")
        return True
    
    def cleanup_fstab_entry(self, mount_point: str):
        """Remove existing fstab entries for a mount point"""
        try:
            # Backup fstab
            backup_path = f"/etc/fstab.bak.{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            shutil.copy2('/etc/fstab', backup_path)
            
            # Read and filter fstab
            with open('/etc/fstab', 'r') as f:
                lines = f.readlines()
            
            with open('/etc/fstab', 'w') as f:
                for line in lines:
                    if mount_point not in line:
                        f.write(line)
                        
            logger.info(f"Removed existing fstab entries for {mount_point}")
            
        except Exception as e:
            logger.error(f"Failed to cleanup fstab: {e}")
    
    def select_server_ip(self) -> bool:
        """Prompt user to select server IP address"""
        console.print(Panel(
            "Network Configuration\n\n"
            "[#9ca3af]Select the IP address for TeamCache endpoint access[/#9ca3af]",
            border_style="#9ca3af",
            padding=(0, 2)
        ))
        console.print("")
        
        # Get available IP addresses
        try:
            import socket
            import netifaces
            has_netifaces = True
        except ImportError:
            import socket
            has_netifaces = False
        
        if has_netifaces:
            # Get all network interfaces and their IPs
            ips = []
            for iface in netifaces.interfaces():
                addrs = netifaces.ifaddresses(iface)
                if netifaces.AF_INET in addrs:
                    for addr in addrs[netifaces.AF_INET]:
                        if 'addr' in addr:
                            ips.append((iface, addr['addr']))
        else:
            # Fallback if netifaces not available - use ip command
            ips = []
            try:
                result = subprocess.run(['ip', '-4', '-o', 'addr', 'show'], 
                                      capture_output=True, text=True)
                if result.returncode == 0:
                    for line in result.stdout.strip().split('\n'):
                        parts = line.split()
                        if len(parts) >= 4:
                            iface = parts[1].rstrip(':')
                            ip = parts[3].split('/')[0]
                            if ip != '127.0.0.1':  # Skip loopback
                                ips.append((iface, ip))
                    
                    # Add loopback as last option
                    ips.append(('lo', '127.0.0.1'))
                else:
                    # Final fallback
                    hostname = socket.gethostname()
                    try:
                        local_ip = socket.gethostbyname(hostname)
                        ips = [('default', local_ip)]
                    except:
                        ips = [('localhost', '127.0.0.1')]
            except:
                ips = [('localhost', '127.0.0.1')]
        
        if not ips:
            self.server_ip = '127.0.0.1'
            console.print("[#f59e0b]No network interfaces found. Using localhost (127.0.0.1)[/#f59e0b]")
            return True
        
        # Display available IPs
        console.print("Available network interfaces and IP addresses:\n")
        table = Table(
            box=box.ROUNDED,
            border_style="#9ca3af"
        )
        table.add_column("Index", style="#6b7280", justify="center")
        table.add_column("Interface", style="#1e3a8a")
        table.add_column("IP Address", style="#6b7280")
        
        for i, (iface, ip) in enumerate(ips, 1):
            table.add_row(str(i), iface, ip)
        
        # Wrap table in a panel for consistent styling
        console.print(Panel(
            table,
            border_style="#9ca3af",
            padding=(1, 1)
        ))
        console.print("")
        
        # Get selection
        while True:
            choice = Prompt.ask(
                "Select IP address for TeamCache endpoint",
                default="1" if ips else ""
            )
            
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(ips):
                    self.server_ip = ips[idx][1]
                    console.print(f"\n[#10b981]✓ Selected IP: {self.server_ip}[/#10b981]")
                    return True
                else:
                    console.print(f"[#ef4444]Invalid selection. Please choose 1-{len(ips)}[/#ef4444]")
            except ValueError:
                # Allow direct IP input
                if choice.count('.') == 3:  # Basic IP validation
                    self.server_ip = choice
                    console.print(f"\n[#10b981]✓ Using IP: {self.server_ip}[/#10b981]")
                    return True
                else:
                    console.print("[#ef4444]Invalid input. Enter a number or valid IP address[/#ef4444]")
    
    def prompt_varnish_port(self) -> bool:
        """Prompt for Varnish port number"""
        console.print("\n[bold]Service Configuration[/bold]\n")
        
        while True:
            port = Prompt.ask(
                "Enter port number for TeamCache endpoint (default: port 80)",
                default="80"
            )
            
            try:
                port_num = int(port)
                if 1 <= port_num <= 65535:
                    self.varnish_port = port_num
                    console.print(f"[#10b981]✓ Varnish will listen on port {self.varnish_port}[/#10b981]\n")
                    return True
                else:
                    console.print("[#ef4444]Port must be between 1 and 65535[/#ef4444]")
            except ValueError:
                console.print("[#ef4444]Invalid port number[/#ef4444]")
    
    def prompt_grafana_password(self) -> bool:
        """Prompt for Grafana admin password"""
        console.print("\n[bold]Grafana Configuration[/bold]\n")
        
        while True:
            password = Prompt.ask("Enter admin password for Grafana dashboard", password=True)
            if not password:
                console.print("[#ef4444]Password cannot be empty![/#ef4444]")
                continue
                
            password_confirm = Prompt.ask("Confirm admin password", password=True)
            
            if password != password_confirm:
                console.print("[#ef4444]Passwords do not match![/#ef4444]")
                continue
            
            self.grafana_password = password
            console.print("[#10b981]✓ Password set successfully[/#10b981]\n")
            return True
    
    def generate_mse4_config(self) -> bool:
        """Generate MSE4 configuration file"""
        num_devices = len(self.selected_devices)
        if num_devices == 0:
            return False
            
        config_path = self.script_dir / "mse4.conf"
        book_size = "8G"
        
        config_content = f"""# MSE4 Configuration
# Generated by teamcache-setup on {datetime.now()}
# Number of devices: {num_devices}

env: {{
        books = ( {{
"""
        
        # Generate books with nested stores
        for i, device in enumerate(self.selected_devices, 1):
            # Calculate store size: (disk_size - 8GB) * 0.98
            # size_bytes is in bytes, convert to GB
            disk_size_gb = device['size_bytes'] / (1024**3)
            store_size_gb = int((disk_size_gb - 8) * 0.98)
            
            config_content += f"""                id = "book{i}";
                filename = "/var/lib/mse/disk{i}/book";
                size = "{book_size}";

                stores = ( {{
                        id = "store{i}";
                        filename = "/var/lib/mse/disk{i}/store";
                        size = "{store_size_gb}G";
                }} );
"""
            if i < num_devices:
                config_content += """        }, {
"""
        
        config_content += """        } );
   };
"""
        
        with open(config_path, 'w') as f:
            f.write(config_content)
            
        logger.info(f"Generated mse4.conf at {config_path}")
        return True
    
    def generate_grafana_config(self) -> bool:
        """Generate Grafana configuration"""
        config_dir = self.script_dir / "conf" / "grafana"
        config_dir.mkdir(parents=True, exist_ok=True)
        
        # Create provisioning directories
        (config_dir / "provisioning" / "dashboards").mkdir(parents=True, exist_ok=True)
        (config_dir / "provisioning" / "datasources").mkdir(parents=True, exist_ok=True)
        
        config_content = f"""# Grafana Configuration
# Generated by teamcache-setup on {datetime.now()}

[server]
http_port = 3000

[security]
admin_user = admin
admin_password = {self.grafana_password}

[auth.anonymous]
enabled = true
org_role = Viewer

[dashboards]
default_home_dashboard_path = /etc/grafana/provisioning/dashboards/varnish_metrics.json

[paths]
provisioning = /etc/grafana/provisioning

[log]
mode = console
level = info

[alerting]
enabled = false

[users]
allow_sign_up = false
"""
        
        with open(config_dir / "grafana.ini", 'w') as f:
            f.write(config_content)
            
        logger.info(f"Generated grafana.ini at {config_dir / 'grafana.ini'}")
        return True
    
    def generate_prometheus_config(self) -> bool:
        """Generate Prometheus configuration"""
        config_dir = self.script_dir / "conf"
        config_dir.mkdir(parents=True, exist_ok=True)
        
        config_content = f"""global:
  scrape_interval: 5s # Set the scrape interval to every 5 seconds. Default is every 1 minute.

# define which exporters to scrape
scrape_configs:
  - job_name: varnish
    # 'varnish' is our varnish container in docker-compose.yml
    # metrics_path defaults to '/metrics', scheme to 'http'
    static_configs:
      - targets: ["varnish:80"]  # Internal container port, not external port
"""
        
        with open(config_dir / "prometheus.yml", 'w') as f:
            f.write(config_content)
            
        logger.info(f"Generated prometheus.yml at {config_dir / 'prometheus.yml'}")
        return True
    
    def generate_compose_yaml(self) -> bool:
        """Generate Docker Compose configuration"""
        if not self.mount_points:
            return False
            
        config_path = self.script_dir / "compose.yaml"
        
        content = f"""# Docker Compose Configuration for TeamCache
# Generated by teamcache-setup on {datetime.now()}
# Number of storage devices: {len(self.selected_devices)}

services:
  mse4_check:
    image: quay.io/varnish-software/varnish-plus:6.0.13r15
    volumes:
      - ./mse4.conf:/etc/varnish/mse4.conf
    entrypoint: []
    user: root
    command: mkfs.mse4 check-config -c /etc/varnish/mse4.conf

  varnish_pre:
    build:
      dockerfile_inline: |
        FROM debian:bookworm-slim
        RUN set -ex; \\
          apt-get update; \\
          apt-get install -y curl; \\
          curl -s https://packagecloud.io/install/repositories/varnishplus/60-enterprise/script.deb.sh | bash; \\
          apt-get install -y varnish-plus
    container_name: varnish_pre
    depends_on:
      mse4_check:
        condition: service_completed_successfully
    volumes:
"""
        
        # Add volume mounts for init container
        for i, mount_point in enumerate(self.mount_points, 1):
            content += f"      - {mount_point}:/var/lib/mse/disk{i}\n"
        
        content += """      - ./varnish-enterprise.lic:/etc/varnish/varnish-enterprise.lic
    entrypoint: []
    user: root
    command: |
      sh -c '
        echo "Setting permissions for MSE directories..."
"""
        
        # Add chown commands
        for i in range(1, len(self.mount_points) + 1):
            content += f"        chown -R varnish:varnish /var/lib/mse/disk{i}\n"
        
        content += f"""        echo "MSE permissions set"
      '

  varnish:
    depends_on:
      varnish_pre:
        condition: service_completed_successfully
    build:
      dockerfile_inline: |
        FROM debian:bookworm-slim
        RUN set -ex; \\
          apt-get update; \\
          apt-get install -y curl; \\
          curl -s https://packagecloud.io/install/repositories/varnishplus/60-enterprise/script.deb.sh | bash; \\
          apt-get install -y varnish-plus
    hostname: varnish
    container_name: varnish
    ports:
      - "{self.varnish_port}:80"
    environment:
      - MSE_CONFIG=/etc/varnish/mse.conf
      - MSE_MEMORY_TARGET=80%
      - MSE4_CONFIG=/etc/varnish/mse4.conf
      - MSE4_CACHE_FORCE_PRESERVE=0
      - VARNISH_ADMIN_LISTEN_ADDRESS=127.0.0.1
      - VARNISH_ADMIN_LISTEN_PORT=6082
      - VARNISH_EXTRA=
      - VARNISH_LISTEN_ADDRESS=
      - VARNISH_LISTEN_PORT=80
      - VARNISH_MAX_THREADS=1000
      - VARNISH_MIN_THREADS=50
      - VARNISH_SECRET_FILE=/etc/varnish/secret
      - VARNISH_STORAGE_BACKEND=
      - VARNISH_THREAD_TIMEOUT=120
      - VARNISH_TLS_CFG=
      - VARNISH_TTL=120
      - VARNISH_VCL_CONF=/etc/varnish/default.vcl
    volumes:
      - workdir:/var/lib/varnish
      - ./mse4.conf:/etc/varnish/mse4.conf:ro
      - ./conf/default.vcl:/etc/varnish/default.vcl:ro
      - ./varnish-enterprise.lic:/etc/varnish/varnish-enterprise.lic
      - ./entrypoint.sh:/entrypoint.sh
"""
        
        # Add storage volume mounts
        for i, mount_point in enumerate(self.mount_points, 1):
            content += f"      - {mount_point}:/var/lib/mse/disk{i}\n"
        
        content += f"""    ulimits:
      memlock:
        soft: -1
        hard: -1
    command: ["bash", "/entrypoint.sh"]

  prometheus:
    image: prom/prometheus:v2.53.0
    container_name: prometheus
    volumes:
      - ./conf/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - prometheus_data:/prometheus
    command: --config.file=/etc/prometheus/prometheus.yml --storage.tsdb.path=/prometheus --web.console.libraries=/usr/share/prometheus/console_libraries --web.console.templates=/usr/share/prometheus/consoles --enable-feature=native-histograms --storage.tsdb.retention.time=6d
    expose:
      - 9090
    ports:
      - "9090:9090"

  grafana:
    image: grafana/grafana-enterprise
    container_name: grafana
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD={self.grafana_password}
      - GF_SECURITY_ADMIN_USER=admin
      - GF_AUTH_ANONYMOUS_ENABLED=true
      - GF_AUTH_ANONYMOUS_ORG_ROLE=Viewer
      - GF_AUTH_DISABLE_LOGIN_FORM=false
      - GF_AUTH_BASIC_ENABLED=false
    volumes:
      - ./conf/grafana/grafana.ini:/etc/grafana/grafana.ini:ro
      - ./conf/grafana/provisioning:/etc/grafana/provisioning:ro
      - grafana_data:/var/lib/grafana

volumes:
  workdir:
    driver: local
    driver_opts:
      type: tmpfs
      device: tmpfs
  prometheus_data:
  grafana_data:
"""
        
        with open(config_path, 'w') as f:
            f.write(content)
            
        logger.info(f"Generated compose.yaml at {config_path}")
        return True
    
    def install_systemd_service(self) -> bool:
        """Install and start the systemd service"""
        service_path = self.script_dir / "teamcache.service"
        
        if not service_path.exists():
            console.print("[#f59e0b]Warning: teamcache.service not found[/#f59e0b]")
            return False
        
        try:
            # Check if service is already installed and running
            result = subprocess.run(
                ['systemctl', 'is-active', 'teamcache.service'],
                capture_output=True, text=True
            )
            
            if result.stdout.strip() == 'active':
                console.print("[#f59e0b]Service is already running[/#f59e0b]")
                if not Confirm.ask("Would you like to restart the service with new configuration?"):
                    return True
                
                # Stop the service before updating
                subprocess.run(['systemctl', 'stop', 'teamcache.service'], check=True)
                console.print("  ✓ Stopped existing service")
            
            # Check if service file exists and compare
            target_path = Path('/etc/systemd/system/teamcache.service')
            if target_path.exists():
                # Check if it's different
                with open(service_path, 'rb') as f1, open(target_path, 'rb') as f2:
                    if f1.read() != f2.read():
                        console.print("  ✓ Updating service file")
                        shutil.copy2(service_path, '/etc/systemd/system/')
                    else:
                        console.print("  ✓ Service file unchanged")
            else:
                # Copy service file
                shutil.copy2(service_path, '/etc/systemd/system/')
                console.print("  ✓ Copied service file to /etc/systemd/system/")
            
            # Reload systemd
            subprocess.run(['systemctl', 'daemon-reload'], check=True)
            console.print("  ✓ Reloaded systemd daemon")
            
            # Enable service
            subprocess.run(['systemctl', 'enable', 'teamcache.service'], check=True)
            console.print("  ✓ Enabled service to start on boot")
            
            # Start service
            subprocess.run(['systemctl', 'start', 'teamcache.service'], check=True)
            console.print("  ✓ Started teamcache.service")
            
            # Intelligent polling loop to check service status
            console.print("  ⏳ Waiting for service to initialize...")
            
            max_attempts = 30  # 30 seconds max wait
            check_interval = 1  # Check every second
            service_ready = False
            has_failure = False
            status_output = ""
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                transient=True
            ) as progress:
                task = progress.add_task("Checking service status...", total=max_attempts)
                
                for attempt in range(max_attempts):
                    # Check detailed status
                    result = subprocess.run(
                        ['systemctl', 'status', 'teamcache.service', '--no-pager'],
                        capture_output=True, text=True
                    )
                    
                    status_output = result.stdout
                    
                    # Check for definitive states
                    if "Active: active (running)" in status_output:
                        # Service is running - no need to check for specific text
                        service_ready = True
                        break
                    elif "Active: failed" in status_output or "code=exited, status=1/FAILURE" in status_output:
                        has_failure = True
                        break
                    elif "Active: activating" in status_output:
                        # Service is still starting, continue waiting
                        progress.update(task, advance=1, description=f"Service is activating... ({attempt+1}/{max_attempts})")
                    else:
                        progress.update(task, advance=1, description=f"Waiting for service... ({attempt+1}/{max_attempts})")
                    
                    time.sleep(check_interval)
                
            # Use the results from our intelligent loop
            if service_ready and not has_failure:
                # Double-check with curl to ensure Varnish is responding
                try:
                    curl_result = subprocess.run(
                        ['curl', '-I', f'http://localhost:{self.varnish_port}', '--max-time', '5'],
                        capture_output=True, text=True
                    )
                    
                    if "503 Backend fetch failed" in curl_result.stdout or "HTTP/1.1 503" in curl_result.stdout:
                        console.print("\n[#10b981]✓ Service is running successfully![/#10b981]")
                        console.print("[#10b981]✓ Varnish is responding (503 Backend fetch failed is expected)[/#10b981]")
                        console.print(f"\n[bold]Access points:[/bold]")
                        console.print(f"  • TeamCache endpoint: http://{self.server_ip}:{self.varnish_port}")
                        console.print(f"  • Grafana Dashboard: http://{self.server_ip}:3000")
                        return True
                    elif curl_result.returncode != 0:
                        # Connection refused or timeout - Varnish might still be starting
                        console.print("\n[#f59e0b]⚠ Service is running but Varnish is not yet responding[/#f59e0b]")
                        console.print("[#f59e0b]  This is normal if containers are still starting up[/#f59e0b]")
                        console.print(f"\n[bold]Access points:[/bold]")
                        console.print(f"  • TeamCache endpoint: http://{self.server_ip}:{self.varnish_port}")
                        console.print(f"  • Grafana Dashboard: http://{self.server_ip}:3000")
                        console.print("\n[#9ca3af]Tip: Wait a few moments to check the TeamCache service endpoint with:[/#9ca3af]")
                        console.print(f"  curl -I http://{self.server_ip}:{self.varnish_port}")
                        return True
                    else:
                        console.print("\n[#f59e0b]⚠ Service appears to be running but Varnish response is unexpected[/#f59e0b]")
                        console.print(f"[#f59e0b]  curl output: {curl_result.stdout[:100]}...[/#f59e0b]")
                        return True
                except Exception as e:
                    console.print(f"\n[#f59e0b]⚠ Could not verify Varnish endpoint: {e}[/#f59e0b]")
                    console.print("[#10b981]✓ Service is running (systemctl status shows active)[/#10b981]")
                    console.print(f"\n[bold]Access points:[/bold]")
                    console.print(f"  • TeamCache endpoint: http://{self.server_ip}:{self.varnish_port}")
                    console.print(f"  • Grafana Dashboard: http://{self.server_ip}:3000")
                    return True
            
            # Only show failure if we're sure it failed
            if has_failure:
                console.print("\n[#ef4444]✗ Service failed to start properly[/#ef4444]")
                console.print("[#ef4444]  Service status: FAILED[/#ef4444]")
                
                # Extract error message
                if "pull access denied" in status_output:
                    console.print("\n[#ef4444]Error: Cannot pull Varnish Plus image[/#ef4444]")
                    console.print("[#f59e0b]You need to authenticate with Varnish Software registry:[/#f59e0b]")
                    console.print("[#f59e0b]  docker login registry.varnish-software.com -u <username> -p <password>[/#f59e0b]")
                    console.print("[#f59e0b]  Contact your LucidLink Account Manager for credentials[/#f59e0b]")
                
            console.print("\n[#f59e0b]To debug, run:[/#f59e0b]")
            console.print("  sudo systemctl status lucid-site-cache")
            console.print("  sudo journalctl -u lucid-site-cache -n 50")
            return False
                
        except subprocess.CalledProcessError as e:
            console.print(f"\n[#ef4444]Error installing service: {e}[/#ef4444]")
            return False
    
    def display_summary(self):
        """Display final summary and next steps"""
        # Service installation prompt FIRST
        service_path = self.script_dir / "teamcache.service"
        if service_path.exists():
            console.print("\n")
            if Confirm.ask("Would you like to install and start the TeamCache systemd service?"):
                console.print("\n[bold]Installing systemd service...[/bold]\n")
                self.install_systemd_service()
            else:
                self.show_manual_steps()
        else:
            self.show_manual_steps()
        
        # Then show the summary panel
        console.print("\n")
        summary_content = f"""[bold #10b981]Setup completed successfully![/bold #10b981]

[bold]Steps executed:[/bold]
  • Formatted {len(self.selected_devices)} device(s) with XFS
  • Created mount points and updated /etc/fstab
  • Generated MSE4 configuration
  • Generated Docker Compose configuration
  • Set up Grafana with admin password

[bold]Mounted devices:[/bold]"""
        
        for i, device in enumerate(self.selected_devices):
            summary_content += f"\n  • {device['path']} → {self.mount_points[i]}"
        
        summary_content += f"""

[bold]Generated files:[/bold]
  • mse4.conf
  • compose.yaml
  • conf/grafana/grafana.ini
  • conf/prometheus.yml

[bold]Access points:[/bold]
  • TeamCache endpoint: http://{self.server_ip}:{self.varnish_port}
  • Grafana Dashboard: http://{self.server_ip}:3000

[bold]Log file:[/bold] {logging.getLoggerClass().root.handlers[0].baseFilename}"""
        
        console.print(Panel(summary_content, title="Setup Complete", border_style="#10b981"))
    
    def show_manual_steps(self):
        """Show manual installation steps"""
        steps_content = f"""[bold]Next Steps:[/bold]

Install and start the systemd service:
[#3b82f6]sudo cp teamcache.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable teamcache.service
sudo systemctl start teamcache.service[/#3b82f6]

Or start manually with Docker Compose:
[#3b82f6]docker compose up -d[/#3b82f6]

[bold]Access points:[/bold]
  • TeamCache endpoint: http://{self.server_ip}:{self.varnish_port}
  • Grafana Dashboard: http://{self.server_ip}:3000"""
        
        console.print(Panel(steps_content, title="Manual Installation", border_style="#f59e0b"))
    
    def run(self):
        """Main execution flow"""
        # Display welcome message
        welcome_text = """[bold #3b82f6]Welcome to TeamCache Setup[/bold #3b82f6]

This tool will help you:
  • Select block devices for MSE storage
  • Format them with XFS
  • Generate configuration files
  • Set up mount points
  • Install the systemd service"""
        
        console.print(Panel(
            welcome_text, 
            box=box.ROUNDED, 
            border_style="#9ca3af",
            title="TeamCache Setup"
        ))
        console.print("")
        
        # Initial checks
        self.check_root_privileges()
        self.check_dependencies()
        
        # Get and display available devices
        console.print("[bold]Scanning for block devices...[/bold]\n")
        devices = self.get_block_devices()
        
        # Select devices
        self.selected_devices = self.display_device_selector(devices)
        if not self.selected_devices:
            console.print("[#f59e0b]No devices selected. Exiting.[/#f59e0b]")
            return
        
        # Confirm selection
        if not self.confirm_device_selection(self.selected_devices):
            console.print("[#f59e0b]Setup cancelled by user.[/#f59e0b]")
            return
        
        # Format devices
        if not self.format_devices_xfs(self.selected_devices):
            console.print("[#ef4444]Failed to format devices. Check log for details.[/#ef4444]")
            return
        
        # Create mount points
        self.create_mount_points()
        
        # Select server IP address
        if not self.select_server_ip():
            console.print("[#f59e0b]Setup cancelled by user.[/#f59e0b]")
            return
        
        # Get Varnish port
        if not self.prompt_varnish_port():
            console.print("[#f59e0b]Setup cancelled by user.[/#f59e0b]")
            return
        
        # Get Grafana password
        if not self.prompt_grafana_password():
            console.print("[#f59e0b]Setup cancelled by user.[/#f59e0b]")
            return
        
        # Check for license file
        license_path = self.script_dir / "varnish-enterprise.lic"
        if not license_path.exists():
            console.print("\n[bold #f59e0b]⚠ Varnish Enterprise License Required[/bold #f59e0b]\n")
            console.print("The file [#3b82f6]varnish-enterprise.lic[/#3b82f6] was not found in the current directory.")
            console.print("Please obtain your license file from your LucidLink Account Manager")
            console.print("and place it in: [#93bbfc]/opt/teamcache/varnish-enterprise.lic[/#93bbfc]\n")
            
            if not Confirm.ask("Do you want to continue without the license file?", default=False):
                console.print("\n[#ef4444]Setup cancelled. Please add the license file and run again.[/#ef4444]")
                return
            else:
                console.print("\n[#f59e0b]Warning: The service will fail to start without a valid license file.[/#f59e0b]\n")
        else:
            console.print("[#10b981]✓[/#10b981] Found Varnish Enterprise license file\n")
        
        # Generate configurations
        console.print(Panel(
            "Generating Configuration Files\n\n"
            "[#9ca3af]Creating TeamCache deployment configuration...[/#9ca3af]",
            border_style="#9ca3af",
            padding=(0, 2)
        ))
        console.print("")
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True
        ) as progress:
            task = progress.add_task("Generating configurations...", total=4)
            
            self.generate_mse4_config()
            progress.update(task, advance=1, description="Generated mse4.conf")
            time.sleep(0.3)
            
            self.generate_grafana_config()
            progress.update(task, advance=1, description="Generated Grafana configuration")
            time.sleep(0.3)
            
            self.generate_prometheus_config()
            progress.update(task, advance=1, description="Generated Prometheus configuration")
            time.sleep(0.3)
            
            self.generate_compose_yaml()
            progress.update(task, advance=1, description="Generated compose.yaml")
            time.sleep(0.3)
        
        console.print("")
        console.print("[#10b981]✓ All configurations generated[/#10b981]\n")
        
        # Display summary
        self.display_summary()


def main():
    """Entry point"""
    try:
        setup = TeamCacheSetup()
        setup.run()
    except KeyboardInterrupt:
        console.print("\n[#f59e0b]Setup interrupted by user.[/#f59e0b]")
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[bold #ef4444]Unexpected error:[/bold #ef4444] {e}")
        logger.exception("Unexpected error occurred")
        sys.exit(1)


if __name__ == "__main__":
    main()