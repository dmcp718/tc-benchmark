# tfbench Windows Setup Guide

## Prerequisites

### 1. Install Python 3.10+

Download from [python.org](https://www.python.org/downloads/) or use Windows Package Manager:

```powershell
# Using winget
winget install Python.Python.3.12

# Verify installation
python --version
```

**Important:** During installation, check "Add Python to PATH"

### 2. Install tframetest

Extract the Windows build:

```powershell
# Extract the ZIP
Expand-Archive tframetest-3025.1.1-win64.zip -DestinationPath C:\Tools

# Add to PATH (optional but recommended)
$env:PATH += ";C:\Tools\tframetest-win-x86_64-w64-mingw32-3025.1.1"
[Environment]::SetEnvironmentVariable("Path", $env:PATH, [System.EnvironmentVariableTarget]::User)

# Verify
tframetest.exe --version
```

### 3. Install Python Dependencies

```powershell
# Install Rich library
pip install rich
```

## Using tfbench on Windows

### Download tfbench-win.py

Place `tfbench-win.py` in your working directory or add to PATH.

### Basic Usage

```powershell
# Create test directory
New-Item -ItemType Directory -Path C:\Temp\tftest -Force

# Run benchmark
python tfbench-win.py -w 4k -n 500 -t 8 C:\Temp\tftest

# With CSV export
python tfbench-win.py -w 4k -n 500 -t 8 C:\Temp\tftest --csv results.csv
```

### Windows-Specific Notes

**Path Format:**
- Use Windows paths: `C:\Temp\tftest` or `D:\storage\test`
- Forward slashes also work: `C:/Temp/tftest`
- Avoid spaces in paths or use quotes: `"C:\Program Files\test"`

**Performance:**
- Windows Defender may scan files during write tests (slower performance)
- Temporarily disable real-time protection for accurate benchmarks
- Run PowerShell/CMD as Administrator for best performance

**Firewall:**
- No network access required - all local operations

## Example Workflow

```powershell
# 1. Create test directory on different drives
New-Item -ItemType Directory -Path C:\Temp\tftest -Force
New-Item -ItemType Directory -Path D:\Temp\tftest -Force

# 2. Benchmark C: drive (system SSD)
python tfbench-win.py -w 4k -n 500 -t 8 C:\Temp\tftest --csv c_drive.csv

# 3. Benchmark D: drive (data drive)
python tfbench-win.py -w 4k -n 500 -t 8 D:\Temp\tftest --csv d_drive.csv

# 4. Compare results in Excel
start excel.exe c_drive.csv d_drive.csv
```

## Terminal Recommendations

### Windows Terminal (Recommended)

Install from Microsoft Store or:

```powershell
winget install Microsoft.WindowsTerminal
```

Supports full color output and Unicode characters.

### PowerShell 7+

```powershell
winget install Microsoft.PowerShell
```

Better performance and features than Windows PowerShell 5.1.

### Command Prompt

Works but limited color support. Use Windows Terminal instead.

## Troubleshooting

### "tframetest.exe not found"

**Solution:**
```powershell
# Option 1: Add to PATH (see Prerequisites)
# Option 2: Copy to same directory as tfbench-win.py
Copy-Item "C:\Tools\tframetest-win-x86_64-w64-mingw32-3025.1.1\tframetest.exe" .
Copy-Item "C:\Tools\tframetest-win-x86_64-w64-mingw32-3025.1.1\libwinpthread-1.dll" .

# Option 3: Run from tframetest directory
cd C:\Tools\tframetest-win-x86_64-w64-mingw32-3025.1.1
python C:\path\to\tfbench-win.py -w 4k -n 500 -t 8 C:\Temp\tftest
```

### "Python not found"

**Solution:**
```powershell
# Ensure Python is in PATH
python --version

# If not found, reinstall Python with "Add to PATH" checked
# Or use full path:
C:\Users\YourName\AppData\Local\Programs\Python\Python312\python.exe tfbench-win.py
```

### "Rich module not found"

**Solution:**
```powershell
pip install rich
# Or if multiple Python versions:
python -m pip install rich
```

### Colors not showing properly

**Solution:**
- Use Windows Terminal instead of CMD
- Enable ANSI color support:
```powershell
Set-ItemProperty HKCU:\Console VirtualTerminalLevel -Type DWORD 1
```

### Access Denied errors

**Solution:**
```powershell
# Run PowerShell as Administrator
Start-Process powershell -Verb runAs

# Or test in user-accessible directory
python tfbench-win.py -w 4k -n 100 -t 4 $env:TEMP\tftest
```

### Very slow write performance

**Possible causes:**
1. **Windows Defender scanning** - Disable real-time protection temporarily
2. **Disk fragmentation** - Defragment HDD (not needed for SSD)
3. **Background processes** - Close unnecessary applications
4. **USB drive** - USB drives are typically much slower

**Check:**
```powershell
# Disk performance info
Get-PhysicalDisk | Format-Table DeviceID, MediaType, Size, Usage

# Running processes
Get-Process | Sort-Object CPU -Descending | Select-Object -First 10
```

## Advanced Usage

### Batch Testing Multiple Drives

Create `test-all-drives.ps1`:

```powershell
# Test all available drives
$drives = Get-PSDrive -PSProvider FileSystem | Where-Object { $_.Used -gt 0 }

foreach ($drive in $drives) {
    $testPath = Join-Path $drive.Root "Temp\tftest"
    New-Item -ItemType Directory -Path $testPath -Force -ErrorAction SilentlyContinue

    Write-Host "Testing $($drive.Name): drive..." -ForegroundColor Cyan
    python tfbench-win.py -w 4k -n 500 -t 8 $testPath --csv "results_$($drive.Name).csv"

    Remove-Item -Path $testPath -Recurse -Force -ErrorAction SilentlyContinue
}
```

Run:
```powershell
.\test-all-drives.ps1
```

### Scheduled Benchmarking

Create a scheduled task to run benchmarks regularly:

```powershell
$action = New-ScheduledTaskAction -Execute "python" -Argument "C:\Tools\tfbench-win.py -w 4k -n 500 -t 8 C:\Temp\tftest --csv C:\Logs\benchmark_$(Get-Date -Format 'yyyyMMdd').csv"
$trigger = New-ScheduledTaskTrigger -Daily -At 2am
Register-ScheduledTask -Action $action -Trigger $trigger -TaskName "DailyStorageBenchmark" -Description "Daily storage performance benchmark"
```

## Requirements Summary

| Component | Version | Required |
|-----------|---------|----------|
| Windows   | 10/11 or Server 2016+ | Yes |
| Python    | 3.10+ | Yes |
| Rich      | 13.7.0+ | Yes |
| tframetest.exe | 3025.1.1 | Yes |

## Support

For issues specific to:
- **tfbench-win.py**: Check this repository
- **tframetest.exe**: See [tuxera/tframetest](https://github.com/tuxera/tframetest)
- **Python/Rich**: See respective project documentation
