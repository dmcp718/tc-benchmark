#!/usr/bin/env python3
"""
Build a standalone executable for TeamCache Setup
This creates a single file that includes all dependencies
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

def main():
    # Colors for output
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    RED = '\033[0;31m'
    NC = '\033[0m'  # No Color
    
    print(f"{YELLOW}Building standalone TeamCache setup application...{NC}")
    
    # Check if we're in the right directory
    if not Path("teamcache-setup.py").exists():
        print(f"{RED}Error: teamcache-setup.py not found in current directory{NC}")
        print("Please run this script from the /opt/teamcache directory")
        sys.exit(1)
    
    # Check for PyInstaller
    try:
        import PyInstaller
    except ImportError:
        print(f"{YELLOW}PyInstaller not found. Installing...{NC}")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)
    
    # Clean previous builds
    print("Cleaning previous builds...")
    for dir in ["build", "dist", "__pycache__"]:
        if Path(dir).exists():
            shutil.rmtree(dir)
    
    # Create a simple one-file build command
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", "teamcache-setup",
        "--distpath", "dist",
        "--workpath", "build",
        "--specpath", ".",
        "--clean",
        "--noconfirm",
        # Add data files
        "--add-data", "conf:conf",
        "--add-data", "entrypoint.sh:.",
        "--add-data", "teamcache.service:.",
        # Hidden imports for Rich
        "--hidden-import", "rich",
        "--hidden-import", "rich.console",
        "--hidden-import", "rich.table",
        "--hidden-import", "rich.progress",
        "--hidden-import", "rich.prompt",
        "--hidden-import", "rich.panel",
        "--hidden-import", "rich.layout",
        "--hidden-import", "rich.text",
        "--hidden-import", "rich.box",
        "--hidden-import", "rich.traceback",
        "teamcache-setup.py"
    ]
    
    # Build the application
    print("Building application (this may take a few minutes)...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"{RED}Build failed!{NC}")
        print("Error output:")
        print(result.stderr)
        sys.exit(1)
    
    # Check if build was successful
    exe_path = Path("dist/teamcache-setup")
    if exe_path.exists():
        print(f"{GREEN}✓ Build successful!{NC}")
        print()
        print("The standalone application is located at:")
        print(f"  {exe_path.absolute()}")
        print()
        print("To deploy:")
        print("  1. Copy dist/teamcache-setup to your target system")
        print("  2. Copy these required files to the same directory:")
        print("     - varnish-enterprise.lic (license file)")
        print("     - conf/ directory (contains Grafana/Prometheus configs)")
        print("  3. Make it executable: chmod +x teamcache-setup")
        print("  4. Run with sudo: sudo ./teamcache-setup")
        print()
        
        # Show file size
        size_mb = exe_path.stat().st_size / (1024 * 1024)
        print(f"Application size: {size_mb:.1f} MB")
        
        # Create a deployment package
        print(f"\n{YELLOW}Creating deployment package...{NC}")
        deploy_dir = Path("teamcache-deploy")
        if deploy_dir.exists():
            shutil.rmtree(deploy_dir)
        deploy_dir.mkdir()
        
        # Copy executable
        shutil.copy2(exe_path, deploy_dir)
        
        # Copy required directories and files
        shutil.copytree("conf", deploy_dir / "conf")
        for file in ["entrypoint.sh", "teamcache.service"]:
            if Path(file).exists():
                shutil.copy2(file, deploy_dir)
        
        # Create deployment instructions
        with open(deploy_dir / "DEPLOY.txt", "w") as f:
            f.write("""TeamCache Setup Deployment Instructions
=====================================

1. Copy this entire directory to your target system
2. Add your varnish-enterprise.lic file to this directory
3. Run as root:
   sudo chmod +x teamcache-setup
   sudo ./teamcache-setup

Required files:
- teamcache-setup (main executable)
- varnish-enterprise.lic (you must provide this)
- conf/ directory (included)
- entrypoint.sh (included)
- teamcache.service (included)

The setup will:
- Format selected block devices with XFS
- Create mount points and update /etc/fstab
- Generate configuration files
- Install and start the Docker Compose stack
""")
        
        # Create tarball
        tarball = "teamcache-deploy.tar.gz"
        subprocess.run(["tar", "-czf", tarball, "teamcache-deploy"], check=True)
        
        print(f"{GREEN}✓ Deployment package created: {tarball}{NC}")
        print(f"  Extract with: tar -xzf {tarball}")
        
    else:
        print(f"{RED}✗ Build failed - executable not found{NC}")
        sys.exit(1)

if __name__ == "__main__":
    main()