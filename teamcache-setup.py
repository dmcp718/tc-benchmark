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
        # Handle PyInstaller bundle vs regular Python script
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            # Running as PyInstaller bundle - files are extracted to _MEIPASS
            self.script_dir = Path(sys._MEIPASS)
        else:
            # Running as normal Python script
            self.script_dir = Path(__file__).parent.absolute()
        self.selected_devices = []
        self.mount_points = []
        self.grafana_password = ""
        self.server_ip = ""
        self.varnish_port = 80
        self.deployment_mode = "docker"  # "docker" or "hybrid"
        self.enable_monitoring = False
        self.storage_mode = "raw_disk"  # "raw_disk" or "filepath"

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
        for cmd in ['lsblk', 'mkfs.xfs', 'blkid', 'systemctl', 'docker']:
            if not shutil.which(cmd):
                missing.append(cmd)
        
        if missing:
            console.print(f"[bold #ef4444]Missing required dependencies:[/bold #ef4444] {', '.join(missing)}")
            
            # Detect the package manager
            pkg_manager = None
            install_cmd = None
            packages = []
            
            if shutil.which('apt-get'):
                pkg_manager = 'apt-get'
                install_cmd = ['apt-get', 'install', '-y']
                if 'mkfs.xfs' in missing:
                    packages.append('xfsprogs')
                if 'lsblk' in missing or 'blkid' in missing:
                    packages.append('util-linux')
            elif shutil.which('yum'):
                pkg_manager = 'yum'
                install_cmd = ['yum', 'install', '-y']
                if 'mkfs.xfs' in missing:
                    packages.append('xfsprogs')
                if 'lsblk' in missing or 'blkid' in missing:
                    packages.append('util-linux')
            elif shutil.which('dnf'):
                pkg_manager = 'dnf'
                install_cmd = ['dnf', 'install', '-y']
                if 'mkfs.xfs' in missing:
                    packages.append('xfsprogs')
                if 'lsblk' in missing or 'blkid' in missing:
                    packages.append('util-linux')
            
            if pkg_manager and packages:
                console.print(f"\n[bold #f59e0b]Would you like to install the missing packages?[/bold #f59e0b]")
                console.print(f"Command: [#3b82f6]{pkg_manager} install {' '.join(packages)}[/#3b82f6]\n")
                
                if Confirm.ask("Install missing dependencies?", default=True):
                    try:
                        console.print(f"[bold]Installing {', '.join(packages)}...[/bold]")
                        result = subprocess.run(
                            install_cmd + packages,
                            capture_output=True,
                            text=True,
                            check=True
                        )
                        console.print("[#10b981]✓ Dependencies installed successfully![/#10b981]")
                        console.print("[#f59e0b]Continuing with setup...[/#f59e0b]\n")
                        
                        # Re-check dependencies after installation
                        still_missing = []
                        for cmd in missing:
                            if not shutil.which(cmd):
                                still_missing.append(cmd)
                        
                        if still_missing:
                            console.print(f"[bold #ef4444]Warning: Some dependencies are still missing:[/bold #ef4444] {', '.join(still_missing)}")
                            console.print("You may need to restart your shell or add the commands to your PATH.")
                            sys.exit(1)
                        
                        return  # All good, continue with setup
                        
                    except subprocess.CalledProcessError as e:
                        console.print(f"[bold #ef4444]Failed to install dependencies:[/bold #ef4444]")
                        console.print(f"[#ef4444]{e.stderr}[/#ef4444]")
                        console.print("\nPlease install manually and run the setup again.")
                        sys.exit(1)
                else:
                    console.print("\n[bold]Manual installation required:[/bold]")
                    console.print(f"  [#3b82f6]sudo {pkg_manager} install {' '.join(packages)}[/#3b82f6]")
                    console.print("\nPlease install the dependencies and run the setup again.")
                    sys.exit(1)
            else:
                # No known package manager or couldn't determine packages
                console.print("\n[bold #f59e0b]Please install the missing dependencies manually:[/bold #f59e0b]")
                if 'mkfs.xfs' in missing:
                    console.print("  • xfsprogs package (provides mkfs.xfs)")
                if 'lsblk' in missing or 'blkid' in missing:
                    console.print("  • util-linux package (provides lsblk and blkid)")
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

        # Ask if user wants to format or use existing
        console.print("[bold]Device Preparation Options:[/bold]")
        console.print("  1. Format selected devices with XFS (ERASES ALL DATA)")
        console.print("  2. Use existing XFS-formatted devices (preserves data)\n")

        format_choice = Prompt.ask(
            "Select option",
            choices=["1", "2"],
            default="1"
        )

        skip_format = (format_choice == "2")

        while True:
            if skip_format:
                selection = Prompt.ask(
                    "\nSelect existing XFS devices to use (comma-separated numbers, e.g., 1,3)",
                    default="1"
                )
            else:
                console.print("\n[bold #f59e0b]WARNING: Selected devices will be COMPLETELY ERASED![/bold #f59e0b]\n")
                selection = Prompt.ask(
                    "Select devices to format (comma-separated numbers, e.g., 1,3)",
                    default="1"
                )
            
            try:
                indices = [int(x.strip()) - 1 for x in selection.split(',')]
                selected = []
                
                for idx in indices:
                    if 0 <= idx < len(devices):
                        device = devices[idx].copy()
                        # If skipping format, verify device has XFS filesystem
                        if skip_format and device.get('fstype') != 'xfs':
                            console.print(f"[#ef4444]Error: {device['path']} does not have XFS filesystem (found: {device.get('fstype', 'none')})[/#ef4444]")
                            console.print("[#f59e0b]Please select only XFS-formatted devices or choose option 1 to format them.[/#f59e0b]")
                            selected = []
                            break
                        device['skip_format'] = skip_format
                        selected.append(device)
                    else:
                        raise ValueError(f"Invalid device number: {idx + 1}")

                if selected:
                    return selected
                    
            except (ValueError, IndexError) as e:
                console.print(f"[#ef4444]Invalid selection: {e}[/#ef4444]")

    def get_filepath_storage(self) -> List[Dict]:
        """Get filepath-based storage paths from user"""
        console.print("\n[bold]Filepath Storage Mode[/bold]\n")
        console.print("Enter directory paths to use for cache storage.")
        console.print("Each path will be used for a separate MSE4 book+store.")
        console.print("Example: /storage/cache/disk1,/storage/cache/disk2\n")

        while True:
            filepath_input = Prompt.ask(
                "Enter comma-separated directory paths",
                default="/cache/disk1"
            )

            try:
                paths = [p.strip() for p in filepath_input.split(',') if p.strip()]

                if not paths:
                    console.print("[#ef4444]Error: At least one path is required[/#ef4444]")
                    continue

                # Validate and prepare paths
                storage_entries = []
                for path_str in paths:
                    path = Path(path_str)

                    # Check if path is absolute
                    if not path.is_absolute():
                        console.print(f"[#ef4444]Error: {path_str} is not an absolute path[/#ef4444]")
                        storage_entries = []
                        break

                    # Check if path exists
                    if path.exists():
                        if not path.is_dir():
                            console.print(f"[#ef4444]Error: {path_str} exists but is not a directory[/#ef4444]")
                            storage_entries = []
                            break

                        # Get available space
                        stat = os.statvfs(path)
                        available_bytes = stat.f_bavail * stat.f_frsize
                        available_gb = available_bytes / (1024**3)

                        if available_bytes < 10 * 1024**3:  # Less than 10GB
                            console.print(f"[#ef4444]Error: {path_str} has less than 10GB available ({available_gb:.1f}GB)[/#ef4444]")
                            storage_entries = []
                            break

                        storage_entries.append({
                            'path': str(path),
                            'size': f"{available_gb:.1f}G",
                            'size_bytes': available_bytes,
                            'exists': True,
                            'type': 'filepath'
                        })
                    else:
                        # Path doesn't exist - check if parent exists
                        parent = path.parent
                        if not parent.exists():
                            console.print(f"[#ef4444]Error: Parent directory {parent} does not exist[/#ef4444]")
                            storage_entries = []
                            break

                        # Get available space from parent
                        stat = os.statvfs(parent)
                        available_bytes = stat.f_bavail * stat.f_frsize
                        available_gb = available_bytes / (1024**3)

                        if available_bytes < 10 * 1024**3:
                            console.print(f"[#ef4444]Error: Parent directory {parent} has less than 10GB available ({available_gb:.1f}GB)[/#ef4444]")
                            storage_entries = []
                            break

                        storage_entries.append({
                            'path': str(path),
                            'size': f"{available_gb:.1f}G",
                            'size_bytes': available_bytes,
                            'exists': False,
                            'type': 'filepath'
                        })

                if storage_entries:
                    # Display what we found
                    table = Table(
                        title="Filepath Storage Configuration",
                        box=box.ROUNDED,
                        title_style="#3b82f6",
                        header_style="#1e3a8a",
                        border_style="#9ca3af"
                    )

                    table.add_column("Path", style="#1e3a8a")
                    table.add_column("Available Space", style="#6b7280", justify="right")
                    table.add_column("Status", style="#6b7280")

                    for entry in storage_entries:
                        status = "[#10b981]Exists[/#10b981]" if entry['exists'] else "[#f59e0b]Will be created[/#f59e0b]"
                        table.add_row(entry['path'], entry['size'], status)

                    console.print("\n")
                    console.print(table)
                    console.print("\n")

                    if Confirm.ask("Use these paths?", default=True):
                        return storage_entries

            except Exception as e:
                console.print(f"[#ef4444]Error: {e}[/#ef4444]")

    def check_mounted_devices(self, devices: List[Dict]) -> List[Dict]:
        """Check if any selected devices are currently mounted"""
        mounted_devices = []
        
        for device in devices:
            # Check if device is mounted
            result = subprocess.run(
                ['mount'],
                capture_output=True, text=True
            )
            
            if device['path'] in result.stdout:
                # Get mount point
                for line in result.stdout.split('\n'):
                    if device['path'] in line:
                        parts = line.split(' on ')
                        if len(parts) >= 2:
                            mount_point = parts[1].split(' type ')[0]
                            device['mount_point'] = mount_point
                            mounted_devices.append(device)
                            break
        
        return mounted_devices
    
    def handle_mounted_devices(self, mounted_devices: List[Dict], skip_format: bool = False) -> bool:
        """Handle mounted devices - offer to unmount or reuse"""
        if not mounted_devices:
            return True

        # Check if devices are mounted at TeamCache locations (/cache/disk*)
        teamcache_mounts = []
        other_mounts = []

        for device in mounted_devices:
            mount_point = device.get('mount_point', '')
            if mount_point.startswith('/cache/disk'):
                teamcache_mounts.append(device)
            else:
                other_mounts.append(device)

        # If using existing XFS and all devices are at TeamCache mount points, offer to reuse
        if skip_format and teamcache_mounts and not other_mounts:
            console.print("\n[bold #3b82f6]ℹ️  TeamCache Mounts Detected[/bold #3b82f6]\n")
            console.print("The following devices are already mounted at TeamCache locations:\n")

            for device in teamcache_mounts:
                mount_point = device.get('mount_point', 'unknown')
                console.print(f"  • {device['path']} mounted at [#3b82f6]{mount_point}[/#3b82f6]")

            console.print("\n[bold]Options:[/bold]")
            console.print("  1. Reuse existing mounts (recommended)")
            console.print("  2. Unmount and remount")
            console.print("  3. Cancel operation")

            choice = Prompt.ask("\nSelect option", choices=["1", "2", "3"], default="1")

            if choice == "1":
                # Mark devices as already mounted - skip mounting step
                for device in teamcache_mounts:
                    device['already_mounted'] = True
                console.print("\n[#10b981]✓ Will reuse existing mounts[/#10b981]")
                return True
            elif choice != "2":
                console.print("\n[#ef4444]Operation cancelled.[/#ef4444]")
                return False
            # If choice == "2", fall through to unmount logic below

        # Show standard unmount options
        console.print("\n[bold #f59e0b]⚠ Mounted Devices Detected[/bold #f59e0b]\n")
        console.print("The following selected devices are currently mounted:\n")

        for device in mounted_devices:
            mount_point = device.get('mount_point', 'unknown')
            console.print(f"  • {device['path']} mounted at [#3b82f6]{mount_point}[/#3b82f6]")

        console.print("\n[bold]Options:[/bold]")
        console.print("  1. Automatically unmount these devices")
        console.print("  2. Manually unmount and retry")
        console.print("  3. Cancel operation")

        choice = Prompt.ask("\nSelect option", choices=["1", "2", "3"], default="3")
        
        if choice == "1":
            # Try to unmount automatically
            console.print("\n[bold]Unmounting devices...[/bold]")
            
            # First, stop the teamcache service if it's using these mounts
            if any('/cache/disk' in d.get('mount_point', '') for d in mounted_devices):
                try:
                    result = subprocess.run(
                        ['systemctl', 'is-active', 'teamcache.service'],
                        capture_output=True, text=True
                    )
                    if result.stdout.strip() == 'active':
                        console.print("  • Stopping teamcache service...")
                        subprocess.run(['systemctl', 'stop', 'teamcache.service'], check=True)
                        console.print("    [#10b981]✓[/#10b981] Service stopped")
                        time.sleep(2)  # Give time for processes to release
                except:
                    pass
            
            success = True
            for device in mounted_devices:
                try:
                    mount_point = device.get('mount_point', '')
                    if mount_point:
                        console.print(f"  • Unmounting {mount_point}...")
                        subprocess.run(['umount', mount_point], check=True, capture_output=True)
                        console.print(f"    [#10b981]✓[/#10b981] Unmounted successfully")
                except subprocess.CalledProcessError as e:
                    console.print(f"    [#ef4444]✗[/#ef4444] Failed to unmount: {e}")
                    success = False
            
            if success:
                console.print("\n[#10b981]All devices unmounted successfully![/#10b981]")
                return True
            else:
                console.print("\n[#ef4444]Some devices could not be unmounted.[/#ef4444]")
                console.print("Please unmount manually and retry.")
                return False
                
        elif choice == "2":
            console.print("\n[bold]Manual unmount required:[/bold]")
            console.print("\nRun these commands to unmount:")
            
            if any('/cache/disk' in d.get('mount_point', '') for d in mounted_devices):
                console.print("  [#3b82f6]sudo systemctl stop teamcache[/#3b82f6]")
            
            for device in mounted_devices:
                mount_point = device.get('mount_point', '')
                if mount_point:
                    console.print(f"  [#3b82f6]sudo umount {mount_point}[/#3b82f6]")
            
            console.print("\nThen run the setup again.")
            return False
        else:
            console.print("\n[#ef4444]Operation cancelled.[/#ef4444]")
            return False
    
    def confirm_device_selection(self, devices: List[Dict]) -> bool:
        """Show confirmation dialog for device selection"""
        console.print("\n")

        # Filepath mode - simple confirmation
        if self.storage_mode == "filepath":
            device_list = "Selected storage paths:\n\n"
            for device in devices:
                status = "exists" if device.get('exists') else "will be created"
                device_list += f"  • {device['path']} [#9ca3af]({device['size']} available, {status})[/#9ca3af]\n"

            console.print(Panel(
                device_list,
                title="Storage Path Selection",
                border_style="#9ca3af",
                padding=(1, 2)
            ))

            info_panel = Panel(
                "[bold #3b82f6]ℹ️  Filepath Storage Mode[/bold #3b82f6]\n\n"
                "Storage directories will be created (if needed) and used for cache storage.\n"
                "No device formatting required.\n\n"
                "[#9ca3af]Directories will be created with appropriate permissions.[/#9ca3af]",
                border_style="#3b82f6",
                title="Information",
                padding=(1, 2)
            )
            console.print(info_panel)
            console.print("\n")
            return Confirm.ask("[bold]Continue with these paths?[/bold]", default=True)

        # Raw disk mode
        # Check if we're skipping format (using existing disks)
        skip_format = devices[0].get('skip_format', False) if devices else False

        # Check for mounted devices first
        mounted_devices = self.check_mounted_devices(devices)
        if mounted_devices:
            if not self.handle_mounted_devices(mounted_devices, skip_format):
                return False

            # Re-check after unmount attempt (unless we're reusing existing mounts)
            # If devices are marked as already_mounted, skip the re-check
            if not any(d.get('already_mounted', False) for d in devices):
                mounted_devices = self.check_mounted_devices(devices)
                if mounted_devices:
                    console.print("\n[#ef4444]Error: Some devices are still mounted.[/#ef4444]")
                    return False

        # Create device list content
        if skip_format:
            device_list = "Selected devices (using existing XFS formatting):\n\n"
        else:
            device_list = "Selected devices for formatting:\n\n"

        for device in devices:
            fs_info = f"Current FS: {device.get('fstype', 'none')}" if skip_format else f"Size: {device['size']}, Model: {device.get('model', 'Unknown')}"
            device_list += f"  • {device['path']} [#9ca3af]({fs_info})[/#9ca3af]\n"

        console.print(Panel(
            device_list,
            title="Device Selection",
            border_style="#9ca3af",
            padding=(1, 2)
        ))

        console.print("\n")

        if skip_format:
            # Just confirm we're using existing disks
            info_panel = Panel(
                "[bold #3b82f6]ℹ️  Using Existing Disks[/bold #3b82f6]\n\n"
                "Selected devices will be mounted and used with their existing XFS filesystems.\n"
                "No data will be erased.\n\n"
                "[#9ca3af]The devices will be mounted and added to /etc/fstab.[/#9ca3af]",
                border_style="#3b82f6",
                title="Information",
                padding=(1, 2)
            )
            console.print(info_panel)
            console.print("\n")
            return Confirm.ask("[bold]Continue with these devices?[/bold]", default=True)
        else:
            # Show warning for formatting
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
        """Format devices with XFS filesystem or verify existing XFS"""
        # Skip formatting entirely for filepath mode
        if self.storage_mode == "filepath":
            console.print("\n[#9ca3af]Skipping device formatting (filepath mode)[/#9ca3af]\n")
            return True

        # Check if we're skipping format
        skip_format = devices[0].get('skip_format', False) if devices else False

        if skip_format:
            # Verify existing XFS and get UUIDs
            console.print("\n")
            console.print(Panel(
                "Verifying Existing XFS Filesystems\n\n"
                "[#9ca3af]Checking selected devices...[/#9ca3af]",
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

                task = progress.add_task("Verifying devices", total=len(devices))

                for device in devices:
                    progress.update(task, description=f"Checking {device['path']}...")

                    # Get UUID from existing filesystem
                    uuid_result = subprocess.run(
                        ['blkid', '-s', 'UUID', '-o', 'value', device['path']],
                        capture_output=True, text=True
                    )

                    uuid = uuid_result.stdout.strip()
                    if not uuid:
                        console.print(f"[#ef4444]Failed to get UUID from {device['path']}[/#ef4444]")
                        return False

                    device['uuid'] = uuid
                    logger.info(f"Using existing XFS filesystem on {device['path']} with UUID={uuid}")

                    progress.advance(task)
                    time.sleep(0.3)

            console.print("")
            console.print("[#10b981]✓ All devices verified successfully![/#10b981]\n")
            return True

        else:
            # Format devices with XFS
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
        """Create mount points and update /etc/fstab (or create directories for filepath mode)"""
        if self.storage_mode == "filepath":
            console.print(Panel(
                "Setting Up Storage Directories\n\n"
                "[#9ca3af]Creating cache storage directories...[/#9ca3af]",
                border_style="#9ca3af",
                padding=(0, 2)
            ))
            console.print("\n")

            self.mount_points = []

            for i, entry in enumerate(self.selected_devices, 1):
                path = Path(entry['path'])
                self.mount_points.append(str(path))

                if not path.exists():
                    try:
                        path.mkdir(parents=True, exist_ok=True)
                        console.print(f"  [#10b981]✓[/#10b981] Created directory {path}")
                        logger.info(f"Created storage directory: {path}")
                    except Exception as e:
                        console.print(f"  [#ef4444]✗[/#ef4444] Failed to create {path}: {e}")
                        logger.error(f"Failed to create directory {path}: {e}")
                        return False
                else:
                    console.print(f"  [#3b82f6]✓[/#3b82f6] Using existing directory {path}")
                    logger.info(f"Using existing storage directory: {path}")

                # Set ownership and SELinux context for Varnish user (hybrid mode only)
                if self.deployment_mode == "hybrid":
                    subprocess.run(['chown', '-R', 'varnish:varnish', str(path)], capture_output=True)

                    # Add SELinux file context rule for this path AND its parent directories
                    # This ensures varnishd can traverse the directory tree
                    parent_path = path.parent
                    subprocess.run(['semanage', 'fcontext', '-a', '-t', 'varnishd_var_lib_t', f'{parent_path}(/.*)?'], capture_output=True)
                    subprocess.run(['semanage', 'fcontext', '-a', '-t', 'varnishd_var_lib_t', f'{path}(/.*)?'], capture_output=True)

                    # Apply the context to parent and path
                    subprocess.run(['restorecon', '-R', str(parent_path)], capture_output=True)
                    subprocess.run(['restorecon', '-R', str(path)], capture_output=True)
                    logger.info(f"Set ownership and SELinux context for {path}")

            console.print("")
            return True

        # Raw disk mode - original mount point logic
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

            # Check if device is already mounted at this location
            if device.get('already_mounted', False):
                console.print(f"  [#3b82f6]✓[/#3b82f6] Reusing {device['path']} already mounted at {mount_point}")
                logger.info(f"Reusing existing mount: {device['path']} at {mount_point}")

                # Set ownership and SELinux context for Varnish user (hybrid mode only)
                if self.deployment_mode == "hybrid":
                    subprocess.run(['chown', '-R', 'varnish:varnish', mount_point], capture_output=True)
                    # Add SELinux file context rule for this mount point
                    subprocess.run(['semanage', 'fcontext', '-a', '-t', 'varnishd_var_lib_t', f'{mount_point}(/.*)?'], capture_output=True)
                    # Apply the context
                    subprocess.run(['restorecon', '-R', mount_point], capture_output=True)
                    logger.info(f"Set ownership and SELinux context for {mount_point}")
                continue

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

                # Set ownership and SELinux context for Varnish user (hybrid mode only)
                if self.deployment_mode == "hybrid":
                    subprocess.run(['chown', '-R', 'varnish:varnish', mount_point], capture_output=True)
                    # Add SELinux file context rule for this mount point
                    subprocess.run(['semanage', 'fcontext', '-a', '-t', 'varnishd_var_lib_t', f'{mount_point}(/.*)?'], capture_output=True)
                    # Apply the context
                    subprocess.run(['restorecon', '-R', mount_point], capture_output=True)
                    logger.info(f"Set ownership and SELinux context for {mount_point}")
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
    
    def install_varnish_native(self) -> bool:
        """Install Varnish Plus natively via package manager"""
        # Check if Varnish is already installed
        if shutil.which('varnishd'):
            version_result = subprocess.run(
                ['varnishd', '-V'],
                capture_output=True,
                text=True
            )
            if version_result.returncode == 0:
                version_info = version_result.stderr.splitlines()[0] if version_result.stderr else "Unknown version"
                console.print("\n")
                console.print(Panel(
                    f"Varnish Enterprise Already Installed\n\n"
                    f"[#9ca3af]{version_info}[/#9ca3af]\n\n"
                    f"[#10b981]Skipping installation...[/#10b981]",
                    border_style="#10b981",
                    padding=(0, 2)
                ))
                console.print("\n")
                return True

        console.print("\n")
        console.print(Panel(
            "Installing Varnish Enterprise\n\n"
            "[#9ca3af]Installing varnish-plus package from packagecloud.io...[/#9ca3af]",
            border_style="#9ca3af",
            padding=(0, 2)
        ))
        console.print("\n")

        try:
            # Detect package manager
            if shutil.which('apt-get'):
                # Debian/Ubuntu
                console.print("[bold]Detected Debian/Ubuntu system[/bold]")
                commands = [
                    (['apt-get', 'update'], "Updating package lists"),
                    (['apt-get', 'install', '-y', 'curl', 'gnupg', 'apt-transport-https'], "Installing prerequisites"),
                ]

                # Add repository
                console.print("  • Adding Varnish Plus repository...")
                result = subprocess.run(
                    'curl -s https://packagecloud.io/install/repositories/varnishplus/60-enterprise/script.deb.sh | bash',
                    shell=True,
                    capture_output=True,
                    text=True
                )
                if result.returncode != 0:
                    console.print(f"[#ef4444]Failed to add repository: {result.stderr}[/#ef4444]")
                    return False
                console.print("    [#10b981]✓[/#10b981] Repository added")

                # Install Varnish
                console.print("  • Installing varnish-plus...")
                result = subprocess.run(
                    ['apt-get', 'install', '-y', 'varnish-plus', '-o', 'Dpkg::Options::=--force-confold'],
                    capture_output=True,
                    text=True
                )

            elif shutil.which('dnf'):
                # RHEL/Rocky/AlmaLinux/Fedora
                console.print("[bold]Detected RHEL/Rocky/Fedora system[/bold]")

                # Install prerequisites
                console.print("  • Installing prerequisites...")
                subprocess.run(
                    ['dnf', '-y', 'install', 'curl', 'gnupg2', 'yum-utils', 'epel-release'],
                    capture_output=True,
                    text=True
                )
                # Install Varnish dependencies (required for EL9)
                subprocess.run(
                    ['dnf', '-y', 'install', 'libunwind', 'isa-l'],
                    capture_output=True,
                    text=True
                )
                console.print("    [#10b981]✓[/#10b981] Prerequisites installed")

                # Add repository
                console.print("  • Adding Varnish Plus repository...")
                result = subprocess.run(
                    'curl -s https://packagecloud.io/install/repositories/varnishplus/60-enterprise/script.rpm.sh | bash',
                    shell=True,
                    capture_output=True,
                    text=True
                )
                if result.returncode != 0:
                    console.print(f"[#ef4444]Failed to add repository: {result.stderr}[/#ef4444]")
                    return False
                console.print("    [#10b981]✓[/#10b981] Repository added")

                # Install Varnish
                console.print("  • Installing varnish-plus...")
                result = subprocess.run(
                    ['dnf', '-y', 'install', 'varnish-plus', '--allowerasing'],
                    capture_output=True,
                    text=True
                )

            elif shutil.which('yum'):
                # CentOS 7
                console.print("[bold]Detected CentOS 7 system[/bold]")

                # Install prerequisites
                console.print("  • Installing prerequisites...")
                subprocess.run(
                    ['yum', '-y', 'install', 'curl', 'gnupg2', 'yum-utils', 'epel-release'],
                    capture_output=True,
                    text=True
                )
                console.print("    [#10b981]✓[/#10b981] Prerequisites installed")

                # Add repository
                console.print("  • Adding Varnish Plus repository...")
                result = subprocess.run(
                    'curl -s https://packagecloud.io/install/repositories/varnishplus/60-enterprise/script.rpm.sh | bash',
                    shell=True,
                    capture_output=True,
                    text=True
                )
                if result.returncode != 0:
                    console.print(f"[#ef4444]Failed to add repository: {result.stderr}[/#ef4444]")
                    return False
                console.print("    [#10b981]✓[/#10b981] Repository added")

                # Install Varnish
                console.print("  • Installing varnish-plus...")
                result = subprocess.run(
                    ['yum', '-y', 'install', 'varnish-plus'],
                    capture_output=True,
                    text=True
                )
            else:
                console.print("[#ef4444]Unsupported package manager[/#ef4444]")
                return False

            if result.returncode != 0:
                console.print(f"[#ef4444]Failed to install varnish-plus: {result.stderr}[/#ef4444]")
                return False

            console.print("    [#10b981]✓[/#10b981] varnish-plus installed successfully")
            console.print("\n[#10b981]✓ Varnish Enterprise installed![/#10b981]\n")

            # Verify installation
            if shutil.which('varnishd'):
                version_result = subprocess.run(
                    ['varnishd', '-V'],
                    capture_output=True,
                    text=True
                )
                if version_result.returncode == 0:
                    console.print(f"[#9ca3af]{version_result.stderr.splitlines()[0]}[/#9ca3af]\n")

            # Generate secret file if it doesn't exist
            self.generate_varnish_secret()

            return True

        except Exception as e:
            console.print(f"[#ef4444]Error installing Varnish: {e}[/#ef4444]")
            return False

    def generate_varnish_secret(self) -> bool:
        """Generate Varnish secret file for admin CLI authentication"""
        secret_path = Path('/etc/varnish/secret')

        # Skip if already exists
        if secret_path.exists():
            logger.info("Varnish secret file already exists, skipping")
            return True

        # Ensure directory exists
        secret_path.parent.mkdir(parents=True, exist_ok=True)

        # Generate random secret (UUID format)
        import uuid
        secret = str(uuid.uuid4())

        # Write secret file
        with open(secret_path, 'w') as f:
            f.write(secret + '\n')

        # Set proper permissions (readable by root and varnish user only)
        os.chmod(secret_path, 0o640)

        # Set ownership to varnish user if it exists
        try:
            subprocess.run(['chown', 'varnish:varnish', str(secret_path)], capture_output=True)
        except:
            pass  # varnish user may not exist yet

        logger.info(f"Generated Varnish secret file at {secret_path}")
        return True

    def generate_default_vcl(self) -> bool:
        """Generate default.vcl for native Varnish deployment"""
        vcl_path = Path('/etc/varnish/default.vcl')
        vcl_path.parent.mkdir(parents=True, exist_ok=True)

        vcl_content = """vcl 4.1;
import uri;
import std;
import utils;
import goto;
import accounting;
import stat;

backend default none;

sub vcl_init {
	accounting.create_namespace("lucid");
}

sub vcl_recv {
	set req.url = uri.decode(req.url);
	accounting.set_namespace("lucid");

	if (req.method != "GET" &&
		req.method != "HEAD" &&
		req.method != "PUT" &&
		req.method != "POST" &&
		req.method != "TRACE" &&
		req.method != "OPTIONS" &&
		req.method != "DELETE" &&
		req.method != "PATCH") {
		return (synth(405));
	}

	if (req.url == "/metrics") {
		return(pass);
	}

	unset req.http.x-method;
	set req.http.x-method = req.method;

	accounting.add_keys(req.method);

	# Only cache GET requests
	if (req.method != "GET") {
		return (pass);
	}

	# Save the range and reuse it on the backend
	# request. This because AWSv4 includes the
	# range header in the signature, which means
	# that it cannot be changed without re-signing
	# the request.
	unset req.http.x-range;
	if (req.http.Range) {
		set req.http.x-range = req.http.Range;
		unset req.http.Range;
	}
	return (hash);
}

sub vcl_hash {
	hash_data(req.method);

	# It would be better to use vmod-slicer to normalize byte ranges, but we
	# cannot do that currently because the range header is part of the AWSv4
	# signature and cannot be changed.
	hash_data(req.http.x-range);
}

sub vcl_backend_fetch {
	if (bereq.url == "/metrics") {
		set bereq.backend = stat.backend_prometheus();
		return(fetch);
	}

	if (bereq.http.x-method) {
		set bereq.method = bereq.http.x-method;
		unset bereq.http.x-method;
	}

	if (bereq.http.x-range) {
		set bereq.http.range = bereq.http.x-range;
		unset bereq.http.x-range;
	}

	# Create a TLS backend using the incoming host header.
	set bereq.backend = goto.dns_backend(bereq.http.host, ssl=true);
}

sub vcl_backend_response {
	if (beresp.status == 200 || beresp.status == 206 || beresp.status == 304) {
		unset beresp.http.cache-control;
		unset beresp.http.expires;
		set beresp.ttl = 10y;
	}
}
"""

        with open(vcl_path, 'w') as f:
            f.write(vcl_content)

        logger.info(f"Generated default.vcl at {vcl_path}")
        return True

    def generate_native_varnish_service(self) -> bool:
        """Generate teamcache.service for native Varnish deployment"""
        service_path = Path('/etc/systemd/system/teamcache.service')

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

# Maximum number of open files (for ulimit -n)
LimitNOFILE=131072

# Shared memory (VSM) segments are tentatively locked in memory. The
# default value for vsl_space (or shorthand varnishd -l option) is 80MB.
# The default value for vst_space is 10MB, leaving 10MB of headroom.
# There are other types of segments that would benefit from allowing
# more memory to be locked.
LimitMEMLOCK=100M

# Enable this to avoid "fork failed" on reload.
TasksMax=infinity

# Maximum size of the corefile.
LimitCORE=infinity

# Maximum number of threads (for ulimit -u)
LimitNPROC=infinity

# The time to wait for start-up. If Varnish start-up does not complete within
# the configured time, the Varnish service will be considered failed. The
# default value for this timeout is not sufficient for certain setups with
# persisted caches with large number of objects and ykeys.
TimeoutStartSec=720

# The time to wait for Varnish to stop gracefully.
TimeoutStopSec=300

# Configure MSE4 storage (creates book and store files as root)
ExecStartPre=/usr/bin/mkfs.mse4 -c /etc/varnish/mse4.conf configure
# Fix ownership and SELinux context after mkfs.mse4 creates files
ExecStartPre=/usr/bin/bash -c '{ownership_cmd}'

ExecStart=/usr/sbin/varnishd \\
	  -a :{self.varnish_port} \\
	  -T localhost:6082 \\
	  -S /etc/varnish/secret \\
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

        logger.info(f"Generated teamcache.service at {service_path}")
        return True

    def generate_mse4_config(self) -> bool:
        """Generate MSE4 configuration file"""
        num_devices = len(self.selected_devices)
        if num_devices == 0:
            return False

        # For hybrid mode, write to /etc/varnish/; for Docker mode, write to script dir
        if self.deployment_mode == "hybrid":
            config_path = Path('/etc/varnish/mse4.conf')
            config_path.parent.mkdir(parents=True, exist_ok=True)
        else:
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

            # Use different paths based on storage mode and deployment mode
            if self.storage_mode == "filepath":
                # Use the actual filepath from selected_devices
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

    def generate_monitoring_compose(self) -> bool:
        """Generate monitoring-only Docker Compose configuration (Prometheus + Grafana)"""
        config_path = self.script_dir / "monitoring-compose.yaml"

        content = f"""# Monitoring Stack Compose Configuration
# Generated by teamcache-setup on {datetime.now()}
# Prometheus and Grafana for TeamCache monitoring

services:
  prometheus:
    image: prom/prometheus:latest
    container_name: prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./conf/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--web.console.libraries=/usr/share/prometheus/console_libraries'
      - '--web.console.templates=/usr/share/prometheus/consoles'
    restart: unless-stopped

  grafana:
    image: grafana/grafana:latest
    container_name: grafana
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD={self.grafana_password}
      - GF_SERVER_ROOT_URL=http://{self.server_ip}:3000
    volumes:
      - ./conf/grafana/grafana.ini:/etc/grafana/grafana.ini:ro
      - ./conf/grafana/provisioning:/etc/grafana/provisioning:ro
      - grafana_data:/var/lib/grafana
    depends_on:
      - prometheus
    restart: unless-stopped

volumes:
  prometheus_data:
  grafana_data:
"""

        with open(config_path, 'w') as f:
            f.write(content)

        logger.info(f"Generated monitoring-compose.yaml at {config_path}")
        return True

    def generate_tc_grafana_service(self) -> bool:
        """Generate tc-grafana.service for monitoring stack"""
        service_path = self.script_dir / "tc-grafana.service"

        service_content = """[Unit]
Description=TeamCache Monitoring Stack (Prometheus + Grafana)
After=network.target docker.service
Requires=docker.service

[Service]
Type=simple
RemainAfterExit=true
WorkingDirectory=/opt/teamcache
ExecStart=/usr/bin/env docker compose -f monitoring-compose.yaml up
ExecStop=/usr/bin/env docker compose -f monitoring-compose.yaml down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
"""

        with open(service_path, 'w') as f:
            f.write(service_content)

        logger.info(f"Generated tc-grafana.service at {service_path}")
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
    build:
      dockerfile_inline: |
        FROM debian:bookworm-slim
        RUN set -ex; \\
          apt-get update; \\
          apt-get install -y curl; \\
          curl -s https://packagecloud.io/install/repositories/varnishplus/60-enterprise/script.deb.sh | bash; \\
          apt-get install -y varnish-plus
    volumes:
      - ./mse4.conf:/etc/varnish/mse4.conf
      - ./varnish-enterprise.lic:/etc/varnish/varnish-enterprise.lic
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
    
    def check_docker(self) -> bool:
        """Check if Docker and Docker Compose are available and running"""
        # Check Docker command
        if not shutil.which('docker'):
            console.print("[bold #ef4444]Docker is not installed[/bold #ef4444]\n")
            console.print("[bold]Would you like to install Docker automatically?[/bold]")
            console.print("[#9ca3af]This will download and run the official Docker installation script from https://get.docker.com[/#9ca3af]\n")

            if Confirm.ask("Install Docker now?", default=True):
                try:
                    console.print("\n[bold]Downloading Docker installation script...[/bold]")

                    # Download the official Docker installation script
                    download_result = subprocess.run(
                        ['curl', '-fsSL', 'https://get.docker.com', '-o', '/tmp/get-docker.sh'],
                        capture_output=True, text=True, check=True
                    )

                    console.print("[bold]Installing Docker (this may take a few minutes)...[/bold]\n")

                    # Run the installation script
                    install_result = subprocess.run(
                        ['sh', '/tmp/get-docker.sh'],
                        capture_output=True, text=True
                    )

                    if install_result.returncode != 0:
                        console.print(f"[bold #ef4444]Docker installation failed:[/bold #ef4444]")
                        console.print(f"[#ef4444]{install_result.stderr}[/#ef4444]")
                        console.print("\nPlease install Docker manually: https://docs.docker.com/engine/install/")
                        return False

                    # Clean up
                    subprocess.run(['rm', '-f', '/tmp/get-docker.sh'], capture_output=True)

                    # Start and enable Docker service
                    console.print("[bold]Starting Docker service...[/bold]")
                    subprocess.run(['systemctl', 'start', 'docker'], check=True, capture_output=True)
                    subprocess.run(['systemctl', 'enable', 'docker'], check=True, capture_output=True)

                    console.print("[#10b981]✓ Docker installed and started successfully![/#10b981]\n")

                    # Verify installation
                    version_result = subprocess.run(
                        ['docker', '--version'],
                        capture_output=True, text=True
                    )
                    if version_result.returncode == 0:
                        console.print(f"[#9ca3af]{version_result.stdout.strip()}[/#9ca3af]\n")

                except subprocess.CalledProcessError as e:
                    console.print(f"[bold #ef4444]Failed to install Docker:[/bold #ef4444]")
                    console.print(f"[#ef4444]{e.stderr if e.stderr else str(e)}[/#ef4444]")
                    console.print("\nPlease install Docker manually: https://docs.docker.com/engine/install/")
                    return False
                except Exception as e:
                    console.print(f"[bold #ef4444]Unexpected error during Docker installation:[/bold #ef4444]")
                    console.print(f"[#ef4444]{str(e)}[/#ef4444]")
                    console.print("\nPlease install Docker manually: https://docs.docker.com/engine/install/")
                    return False
            else:
                console.print("\n[bold]Manual installation required:[/bold]")
                console.print("  Visit: https://docs.docker.com/engine/install/")
                console.print("\nPlease install Docker and run the setup again.")
                return False

        # Check if Docker daemon is running
        try:
            result = subprocess.run(
                ['systemctl', 'is-active', 'docker'],
                capture_output=True, text=True
            )
            if result.stdout.strip() != 'active':
                console.print("[bold #ef4444]Docker service is not running[/bold #ef4444]")

                if Confirm.ask("Would you like to start the Docker service?", default=True):
                    try:
                        subprocess.run(['systemctl', 'start', 'docker'], check=True, capture_output=True)
                        subprocess.run(['systemctl', 'enable', 'docker'], check=True, capture_output=True)
                        console.print("[#10b981]✓ Docker service started successfully![/#10b981]\n")
                    except subprocess.CalledProcessError as e:
                        console.print(f"[#ef4444]Failed to start Docker service: {e}[/#ef4444]")
                        console.print("Please start Docker manually: [#3b82f6]sudo systemctl start docker[/#3b82f6]")
                        return False
                else:
                    console.print("Please start Docker: [#3b82f6]sudo systemctl start docker[/#3b82f6]")
                    return False
        except subprocess.CalledProcessError:
            console.print("[bold #ef4444]Error: Could not check Docker service status[/bold #ef4444]")
            return False

        # Check Docker Compose
        try:
            result = subprocess.run(
                ['docker', 'compose', 'version'],
                capture_output=True, text=True
            )
            if result.returncode != 0:
                console.print("[bold #ef4444]Error: Docker Compose is not installed[/bold #ef4444]")
                console.print("Docker Compose should have been installed with Docker.")
                console.print("Please reinstall Docker or install the Docker Compose plugin manually.")
                return False
        except (subprocess.CalledProcessError, FileNotFoundError):
            console.print("[bold #ef4444]Error: Docker Compose is not available[/bold #ef4444]")
            console.print("Docker Compose should have been installed with Docker.")
            console.print("Please reinstall Docker or install the Docker Compose plugin manually.")
            return False

        return True
    
    def install_systemd_service(self) -> bool:
        """Install and start the systemd service(s) based on deployment mode"""

        if self.deployment_mode == "hybrid":
            return self.install_hybrid_services()
        else:
            return self.install_docker_service()

    def install_hybrid_services(self) -> bool:
        """Install native Varnish service and optionally monitoring service"""
        try:
            console.print("\n[bold]Installing TeamCache Services...[/bold]\n")

            # Install native Varnish service (teamcache.service)
            console.print("[bold]1. Installing Varnish service (teamcache.service)[/bold]")

            # Service file was already generated, now install it
            service_path = Path('/etc/systemd/system/teamcache.service')
            if not service_path.exists():
                console.print("[#ef4444]  Error: teamcache.service not found at /etc/systemd/system/[/#ef4444]")
                return False

            # Reload systemd
            subprocess.run(['systemctl', 'daemon-reload'], check=True)
            console.print("  ✓ Reloaded systemd daemon")

            # Enable and start Varnish service
            subprocess.run(['systemctl', 'enable', 'teamcache.service'], check=True)
            console.print("  ✓ Enabled teamcache.service")

            subprocess.run(['systemctl', 'start', 'teamcache.service'], check=True)
            console.print("  ✓ Started teamcache.service")

            # Verify Varnish is running
            time.sleep(2)
            result = subprocess.run(
                ['systemctl', 'is-active', 'teamcache.service'],
                capture_output=True, text=True
            )

            if result.stdout.strip() == 'active':
                console.print("  [#10b981]✓ Varnish is running[/#10b981]\n")
            else:
                console.print("  [#ef4444]✗ Varnish failed to start[/#ef4444]")
                console.print("  Run: sudo systemctl status teamcache.service\n")
                return False

            # Install monitoring stack if enabled
            if self.enable_monitoring:
                # Check Docker for monitoring stack
                if not self.check_docker():
                    console.print("[#f59e0b]Warning: Docker not available for monitoring stack[/#f59e0b]")
                    console.print("[#f59e0b]Varnish is running, but monitoring will not be deployed[/#f59e0b]\n")
                    return True

                console.print("[bold]2. Installing Monitoring Stack (tc-grafana.service)[/bold]")

                # Create /opt/teamcache for monitoring files
                install_dir = Path('/opt/teamcache')
                install_dir.mkdir(parents=True, exist_ok=True)
                console.print(f"  ✓ Created {install_dir}")

                # Copy monitoring files
                files_to_copy = ['monitoring-compose.yaml']
                for filename in files_to_copy:
                    src = self.script_dir / filename
                    if src.exists():
                        shutil.copy2(src, install_dir / filename)
                        logger.info(f"Copied {filename} to {install_dir}")

                # Copy conf directory for Grafana/Prometheus
                src_conf = self.script_dir / "conf"
                dst_conf = install_dir / "conf"
                if src_conf.exists():
                    if dst_conf.exists():
                        shutil.rmtree(dst_conf)
                    shutil.copytree(src_conf, dst_conf)
                    logger.info(f"Copied conf/ directory to {install_dir}")

                console.print(f"  ✓ Copied monitoring configuration files")

                # Install tc-grafana.service
                service_src = self.script_dir / "tc-grafana.service"
                if service_src.exists():
                    shutil.copy2(service_src, '/etc/systemd/system/')
                    console.print("  ✓ Installed tc-grafana.service")

                    subprocess.run(['systemctl', 'daemon-reload'], check=True)
                    subprocess.run(['systemctl', 'enable', 'tc-grafana.service'], check=True)
                    console.print("  ✓ Enabled tc-grafana.service")

                    subprocess.run(['systemctl', 'start', 'tc-grafana.service'], check=True)
                    console.print("  ✓ Started tc-grafana.service")

                    time.sleep(2)
                    result = subprocess.run(
                        ['systemctl', 'is-active', 'tc-grafana.service'],
                        capture_output=True, text=True
                    )

                    if result.stdout.strip() == 'active':
                        console.print("  [#10b981]✓ Monitoring stack is running[/#10b981]\n")
                    else:
                        console.print("  [#f59e0b]⚠ Monitoring stack failed to start[/#f59e0b]")
                        console.print("  Run: sudo systemctl status tc-grafana.service\n")

            console.print("[#10b981]✓ Installation complete![/#10b981]\n")
            console.print(f"[bold]Access points:[/bold]")
            console.print(f"  • TeamCache endpoint: http://{self.server_ip}:{self.varnish_port}")
            if self.enable_monitoring:
                console.print(f"  • Grafana Dashboard: http://{self.server_ip}:3000")
                console.print(f"  • Prometheus: http://{self.server_ip}:9090")

            return True

        except Exception as e:
            console.print(f"[#ef4444]Error installing services: {e}[/#ef4444]")
            return False

    def install_docker_service(self) -> bool:
        """Install Docker Compose service (original behavior)"""
        # Check Docker before proceeding
        if not self.check_docker():
            console.print("\n[bold #ef4444]Cannot install service without Docker[/bold #ef4444]")
            return False

        service_path = self.script_dir / "teamcache.service"

        if not service_path.exists():
            console.print("[#f59e0b]Warning: teamcache.service not found[/#f59e0b]")
            return False

        try:
            # Create /opt/teamcache directory
            install_dir = Path('/opt/teamcache')
            install_dir.mkdir(parents=True, exist_ok=True)
            console.print(f"  ✓ Created installation directory: {install_dir}")

            # Copy generated files to /opt/teamcache
            files_to_copy = [
                'compose.yaml',
                'mse4.conf',
                'entrypoint.sh',
            ]

            for filename in files_to_copy:
                src = self.script_dir / filename
                if src.exists():
                    shutil.copy2(src, install_dir / filename)
                    # Make entrypoint.sh executable
                    if filename == 'entrypoint.sh':
                        (install_dir / filename).chmod(0o755)
                    logger.info(f"Copied {filename} to {install_dir}")

            # Copy license file to both /opt/teamcache and /etc/varnish
            license_src = None
            cwd_license = Path.cwd() / "varnish-enterprise.lic"
            script_license = self.script_dir / "varnish-enterprise.lic"

            if cwd_license.exists():
                license_src = cwd_license
            elif script_license.exists():
                license_src = script_license

            if license_src:
                # Copy to /opt/teamcache for Docker Compose
                shutil.copy2(license_src, install_dir / "varnish-enterprise.lic")
                logger.info(f"Copied license to {install_dir}")

                # Copy to /etc/varnish for native Varnish
                varnish_etc = Path('/etc/varnish')
                varnish_etc.mkdir(parents=True, exist_ok=True)
                shutil.copy2(license_src, varnish_etc / "varnish-enterprise.lic")
                logger.info(f"Copied license to {varnish_etc}")
                console.print(f"  ✓ Copied license file to /etc/varnish/")

            # Copy conf directory
            src_conf = self.script_dir / "conf"
            dst_conf = install_dir / "conf"
            if src_conf.exists():
                if dst_conf.exists():
                    shutil.rmtree(dst_conf)
                shutil.copytree(src_conf, dst_conf)
                logger.info(f"Copied conf/ directory to {install_dir}")

            console.print(f"  ✓ Copied configuration files to {install_dir}")

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
        service_installed = False
        service_path = self.script_dir / "teamcache.service"
        if service_path.exists():
            console.print("\n")
            if Confirm.ask("Would you like to install and start the TeamCache systemd service?"):
                console.print("\n[bold]Installing systemd service...[/bold]\n")
                service_installed = self.install_systemd_service()
                if not service_installed:
                    console.print("\n[#ef4444]Service installation failed. Please check the logs above.[/#ef4444]")
                    self.show_manual_steps()
                    return
            else:
                self.show_manual_steps()
                return
        else:
            self.show_manual_steps()
            return

        # Then show the summary panel (only if service installed successfully)
        console.print("\n")

        # Check if we skipped formatting
        skip_format = self.selected_devices[0].get('skip_format', False) if self.selected_devices else False
        format_msg = f"Used {len(self.selected_devices)} existing XFS device(s)" if skip_format else f"Formatted {len(self.selected_devices)} device(s) with XFS"

        summary_content = f"""[bold #10b981]Setup completed successfully![/bold #10b981]

[bold]Steps executed:[/bold]
  • {format_msg}
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

        # Select deployment mode
        console.print("\n[bold]Deployment Mode Selection[/bold]\n")
        console.print("Choose how to deploy TeamCache:\n")
        console.print("  [bold]1. Docker Compose[/bold] (All-in-one)")
        console.print("     • Varnish, Prometheus, and Grafana in Docker containers")
        console.print("     • Easier to manage, single service\n")
        console.print("  [bold]2. Hybrid[/bold] (Native + Optional Monitoring)")
        console.print("     • Varnish installed natively via package manager")
        console.print("     • Better performance, runs as systemd service")
        console.print("     • Optional Prometheus/Grafana monitoring stack\n")

        deployment_choice = Prompt.ask(
            "Select deployment mode",
            choices=["1", "2"],
            default="2"
        )

        if deployment_choice == "2":
            self.deployment_mode = "hybrid"
            console.print("\n[#3b82f6]Selected: Hybrid deployment (Native Varnish)[/#3b82f6]")

            # Ask about monitoring
            self.enable_monitoring = Confirm.ask(
                "\nWould you like to enable Prometheus/Grafana monitoring?",
                default=True
            )
            if self.enable_monitoring:
                console.print("[#3b82f6]Monitoring stack will be deployed[/#3b82f6]\n")
            else:
                console.print("[#9ca3af]Monitoring stack will be skipped[/#9ca3af]\n")
        else:
            self.deployment_mode = "docker"
            self.enable_monitoring = True  # Always enabled in Docker mode
            console.print("\n[#3b82f6]Selected: Full Docker Compose deployment[/#3b82f6]\n")

        # Select storage mode
        console.print("\n[bold]Storage Mode Selection[/bold]\n")
        console.print("Choose how to configure cache storage:\n")
        console.print("  [bold]1. Raw Disk Mode[/bold]")
        console.print("     • Use entire block devices (/dev/sdb, /dev/sdc, etc.)")
        console.print("     • Devices will be formatted with XFS")
        console.print("     • Mounted at /cache/disk1, /cache/disk2, etc.\n")
        console.print("  [bold]2. Filepath Mode[/bold]")
        console.print("     • Use directory paths on existing mounted filesystems")
        console.print("     • No device formatting required")
        console.print("     • Example: /storage/cache/disk1, /storage/cache/disk2\n")

        storage_choice = Prompt.ask(
            "Select storage mode",
            choices=["1", "2"],
            default="1"
        )

        if storage_choice == "2":
            self.storage_mode = "filepath"
            console.print("\n[#3b82f6]Selected: Filepath mode[/#3b82f6]\n")
            # Get filepath storage paths
            self.selected_devices = self.get_filepath_storage()
            if not self.selected_devices:
                console.print("[#f59e0b]No storage paths configured. Exiting.[/#f59e0b]")
                return
        else:
            self.storage_mode = "raw_disk"
            console.print("\n[#3b82f6]Selected: Raw disk mode[/#3b82f6]\n")
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
        
        # Check for license file - try current directory first (for PyInstaller compatibility)
        cwd_license = Path.cwd() / "varnish-enterprise.lic"
        script_license = self.script_dir / "varnish-enterprise.lic"
        
        license_found = False
        if cwd_license.exists():
            console.print(f"[#10b981]✓[/#10b981] Found license file at: {cwd_license}\n")
            license_found = True
        elif script_license.exists():
            console.print(f"[#10b981]✓[/#10b981] Found license file at: {script_license}\n")
            license_found = True
            
        if not license_found:
            console.print("\n[bold #f59e0b]⚠ Varnish Enterprise License Required[/bold #f59e0b]\n")
            console.print("The file [#3b82f6]varnish-enterprise.lic[/#3b82f6] was not found.")
            console.print("Please obtain your license file from your LucidLink Account Manager")
            console.print("and place it in the current directory: [#93bbfc]./varnish-enterprise.lic[/#93bbfc]\n")
            
            if not Confirm.ask("Do you want to continue without the license file?", default=False):
                console.print("\n[#ef4444]Setup cancelled. Please add the license file and run again.[/#ef4444]")
                return
            else:
                console.print("\n[#f59e0b]Warning: The service will fail to start without a valid license file.[/#f59e0b]\n")
        
        # Generate configurations based on deployment mode
        console.print(Panel(
            "Generating Configuration Files\n\n"
            "[#9ca3af]Creating TeamCache deployment configuration...[/#9ca3af]",
            border_style="#9ca3af",
            padding=(0, 2)
        ))
        console.print("")

        if self.deployment_mode == "hybrid":
            # Hybrid mode: Native Varnish + Optional Monitoring
            steps = []

            # Always generate VCL and MSE4 config
            steps.append(("Generate default.vcl", self.generate_default_vcl))
            steps.append(("Generate mse4.conf", self.generate_mse4_config))
            steps.append(("Generate teamcache.service", self.generate_native_varnish_service))

            # Optionally generate monitoring configs
            if self.enable_monitoring:
                steps.append(("Generate Grafana config", self.generate_grafana_config))
                steps.append(("Generate Prometheus config", self.generate_prometheus_config))
                steps.append(("Generate monitoring compose", self.generate_monitoring_compose))
                steps.append(("Generate tc-grafana.service", self.generate_tc_grafana_service))

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                transient=True
            ) as progress:
                task = progress.add_task("Generating configurations...", total=len(steps))

                for desc, func in steps:
                    func()
                    progress.update(task, advance=1, description=desc)
                    time.sleep(0.2)

            # Install Varnish natively
            if not self.install_varnish_native():
                console.print("[#ef4444]Failed to install Varnish[/#ef4444]")
                return

        else:
            # Docker mode: Everything in Docker Compose
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