# tfbench Examples and Usage Guide

## Quick Reference

### Basic Usage

```bash
# Run standard benchmark (1 write + 3 reads, 500 frames)
uv run tfbench.py -w 4k -n 500 -t 8 /media/tc-mngr/tftest

# Fast test (fewer frames for quick checks)
uv run tfbench.py -w 4k -n 100 -t 4 /tmp/test

# Intensive test (more frames with extended timeout)
uv run tfbench.py -w 4k -n 2000 -t 16 /mnt/storage --timeout 3600

# Run with CSV export for analysis
uv run tfbench.py -w 4k -n 500 -t 8 /mnt/storage --csv results.csv
```

### Advanced Options

```bash
# Test with different frame sizes
uv run tfbench.py -w 2k -n 500 -t 8 /media/storage   # 2KB frames
uv run tfbench.py -w 1m -n 200 -t 8 /media/storage   # 1MB frames (fewer frames, larger size)

# Multiple read iterations (to see cache stabilization)
uv run tfbench.py -w 4k -n 500 -t 8 /media/storage --reads 3
uv run tfbench.py -w 4k -n 500 -t 8 /media/storage --reads 5

# Thread scaling tests
uv run tfbench.py -w 4k -n 500 -t 1 /media/storage   # Single thread
uv run tfbench.py -w 4k -n 500 -t 32 /media/storage  # 32 threads

# Slow storage with extended timeout
uv run tfbench.py -w 4k -n 1000 -t 8 /media/slow-storage --timeout 7200  # 2 hour timeout

# Flag results that exceed your link's real capacity (1 Gbps ≈ 119 MiB/s)
uv run tfbench.py -w 4k -n 500 -t 8 /media/storage --link-speed 1000

# Cloud filesystem: measure end-to-end write speed by polling the
# filesystem's pending-upload counter until it drains to zero
uv run tfbench.py -w 4k -n 500 -t 8 /mnt/cloudfs/bench \
    --flush-cmd 'mycloudfs stats --pending-upload-bytes' --flush-timeout 300

# Use a specific tframetest build; check which binary would run
uv run tfbench.py -w 4k -n 500 -t 8 /media/storage --binary ./build/tframetest
uv run tfbench.py --version
```

## Understanding the Output

### 1. Throughput Comparison

Shows visual bar chart of MiB/s for each test:
- **Write** (green) - Initial write performance
- **Read #1** (blue), **Read #2** (cyan), ... - Neutral labels; tfbench doesn't assume any
  read is "cold". Files were just written, so they're already warm in any local/OS cache —
  consecutive reads mostly show run-to-run repeatability, not a cache warm-up effect
- **⚡ RAM CACHE** (yellow) - Read speeds >10 GB/s (data served from RAM, not disk); always
  checked, and takes precedence when the link-speed condition also applies
- **⚡ LOCAL CACHE** (yellow) - Shown when `--link-speed` is given and a read or write
  exceeds what that link could physically sustain

The bar length is proportional to throughput, making it easy to compare at a glance.

**Important:** If you see a "⚡ RAM CACHE" or "⚡ LOCAL CACHE" indicator, that result represents
the speed of a local cache (system RAM, or a local disk cache on a WAN-backed mount), not the
real storage/network path. This is valuable for understanding cache behavior but doesn't reflect
true storage or network I/O performance. Pass `--link-speed MBPS` with your actual link's
bandwidth to catch local-disk-cache cases the 10 GB/s RAM heuristic alone would miss.

### 2. Performance Insights

Automatically calculated metrics:

- **Read repeatability (Read #2 / Read #1)** - How consistent repeated reads are
  - Example: `3.63x` means Read #2 was 3.63 times faster than Read #1
  - Since both reads run against files just written (already warm), a ratio far from 1x more
    often reflects a local cache draining/filling or contention than a "cache warm-up" effect
  - Values near 1x indicate consistent, repeatable throughput

- **Read/Write ratio** - Best read performance vs write performance
  - Example: `2.60x` means cached reads are 2.6 times faster than writes
  - Typical for many storage systems
  - Much higher ratios may indicate write bottlenecks

- **Latency improvement** - Percentage reduction in average latency
  - Example: `72.5%` means average latency dropped by 72.5%
  - High percentages indicate effective caching

### 3. Latency Statistics

Min/Avg/Max/Range completion times in milliseconds:
- **Min** - Best case latency (fastest operation)
- **Avg** - Average latency across all operations
- **Max** - Worst case latency (slowest operation)
- **Range** - Difference between max and min (shows consistency)

### 4. Detailed Statistics

Complete table with all metrics:
- **Profile** - tframetest profile used
- **Frames** - Number of frames tested
- **FPS** - Frames per second
- **MiB/s** - Megabytes per second (primary throughput metric)
- **Time (s)** - Total test duration

## CSV Export for Analysis

tfbench can export all results to CSV format for further processing:

```bash
# Basic export
uv run tfbench.py -w 4k -n 500 -t 8 /mnt/storage --csv results.csv

# Export with timestamp in filename
uv run tfbench.py -w 4k -n 500 -t 8 /mnt/storage --csv "results_$(date +%Y%m%d_%H%M%S).csv"

# Export for comparison across devices
uv run tfbench.py -w 4k -n 500 -t 8 /mnt/nvme --csv nvme_results.csv
uv run tfbench.py -w 4k -n 500 -t 8 /mnt/hdd --csv hdd_results.csv
```

**CSV Output Format:**

The CSV includes three sections:

1. **Metadata** - Timestamp, target directory, frame size, threads, link speed (if given)
2. **Benchmark Results** - Complete metrics for each test:
   - test_name, operation, profile, frames, bytes
   - time_ns, time_seconds, fps, bytes_per_sec, mib_per_sec
   - min_ms, avg_ms, max_ms, range_ms
   - cache_flag ("ram", "link", or empty), drain_seconds, peak_remaining_upload_mib,
     end_to_end_mib_per_sec (the last three populated for the write row when --flush-cmd is given)
3. **Performance Insights** - Calculated metrics:
   - read_repeatability_ratio
   - read_write_ratio
   - latency_improvement_percent

**Using CSV with other tools:**

```bash
# Import into Python pandas
python3 -c "import pandas as pd; df = pd.read_csv('results.csv', skiprows=6, nrows=3); print(df)"

# Extract specific values with awk
awk -F',' '/^Write,/ {print "Write throughput: " $10 " MiB/s"}' results.csv

# Compare multiple CSV files
for f in *.csv; do
  echo "$f:"
  grep "^Write," "$f" | cut -d',' -f10
done
```

## Common Scenarios

### Storage Device Comparison

Test two different storage devices:

```bash
# Test NVMe SSD
uv run tfbench.py -w 4k -n 500 -t 16 /mnt/nvme

# Test HDD (slower, so use fewer frames or increase timeout)
uv run tfbench.py -w 4k -n 500 -t 16 /mnt/hdd --timeout 3600
```

Compare the results to see performance differences.

### Read Repeatability Analysis

Run with multiple reads to check run-to-run consistency:

```bash
uv run tfbench.py -w 4k -n 500 -t 8 /media/storage --reads 4
```

Note that the frames were just written, so every read pass is warm in any
local/OS cache layer — consistent numbers across passes indicate a stable
measurement, not a cold-to-warm transition. Pass `--link-speed` to catch
reads that are being served from a local cache instead of real storage.

### Thread Scaling Study

Test how performance scales with thread count:

```bash
for threads in 1 2 4 8 16 32; do
  echo "Testing with $threads threads"
  uv run tfbench.py -w 4k -n 500 -t $threads /media/storage
done
```

### Frame Size Impact

Compare different frame sizes:

```bash
# Small frames (2KB) - Many small I/O operations
uv run tfbench.py -w 2k -n 1000 -t 8 /media/storage

# Medium frames (4KB) - Balanced
uv run tfbench.py -w 4k -n 500 -t 8 /media/storage

# Large frames (1MB) - Fewer, larger I/O operations
uv run tfbench.py -w 1m -n 100 -t 8 /media/storage
```

## Understanding Cache vs Disk Performance

### What is RAM Cache?

Modern operating systems automatically cache recently accessed file data in RAM for faster subsequent access. When tfbench detects read speeds >10 GB/s, it indicates the data is being served from RAM cache rather than the storage device.

**Typical speeds by source:**
- **RAM cache**: 50-100+ GB/s (especially on Apple Silicon)
- **NVMe SSD**: 2-7 GB/s
- **SATA SSD**: 0.5-0.6 GB/s
- **HDD**: 0.1-0.2 GB/s

### When Cache Detection Appears

You'll see "⚡ RAM CACHE" indicators when:
- Testing with small datasets that fit entirely in RAM
- Running multiple read tests without clearing cache between runs
- Your system has sufficient RAM to cache the test dataset
- Recent file access allows the OS to pre-cache data

### Measuring Actual Disk Performance

To measure true storage I/O performance instead of cache:

**Option 1: Clear cache before each test (requires sudo)**
```bash
# macOS - Clear disk cache
sudo purge

# Linux - Drop page cache
sync
echo 3 | sudo tee /proc/sys/vm/drop_caches
```

**Option 2: Use larger datasets**
```bash
# If you have 16GB RAM, use enough frames to exceed it
# Example: 4KB frames, 5 million frames = ~20GB
uv run tfbench.py -w 4k -n 5000000 -t 8 /mnt/storage --timeout 7200
```

**Option 3: Test on system with less RAM**
- Use a test system with limited RAM relative to dataset size

### Cache Performance is Still Valuable!

While cache speeds don't reflect disk performance, they ARE useful for:
- Understanding how your application will perform with cached data
- Validating that OS caching is working properly
- Comparing cache effectiveness across different systems
- Real-world workloads where data is frequently re-accessed

## Interpreting Results

### Good Performance Indicators

- **High cache speedup (>3x)** - System cache is working effectively
- **Consistent latency** - Small gap between min and max
- **High throughput** - Depends on hardware, but >1000 MiB/s is good for NVMe
- **Scaling with threads** - Performance should increase with thread count up to hardware limits

### Performance Issues

- **Low cache speedup (<1.5x)** - Cache may be ineffective or disabled
- **High max latency** - System may have I/O contention or background processes
- **Write >> Read speeds** - Unusual; may indicate write caching without read caching
- **No thread scaling** - May indicate single-threaded bottleneck

### Distinguishing Disk vs Cache Performance

- **Disk performance**: First write test and reads after cache clear (typically <10 GB/s)
- **Cache performance**: Subsequent reads without cache clear (often >10 GB/s on modern systems)
- **Mixed**: Read #1 may show partial cache (some blocks cached, some from disk)

## Tips

1. **Clean test environment** - Clear caches before testing for consistent cold-cache results:
   ```bash
   # Linux: Clear page cache (requires root)
   sync; echo 3 > /proc/sys/vm/drop_caches
   ```

2. **Sufficient test size** - Use enough frames to exceed cache size for realistic results
   - 500 frames × 4KB = ~2GB of data (good starting point)
   - 1000 frames × 4KB = ~4GB of data (more comprehensive)
   - Adjust based on your system's cache/RAM size

3. **Timeout considerations** - Set appropriate timeout for your storage speed
   - Default 30 minutes (1800s) works for most storage
   - Slow HDDs or network storage may need `--timeout 3600` or higher
   - Monitor first test to estimate required time

4. **Consistent test parameters** - Use same frame count and size when comparing devices

5. **Multiple runs** - Run tests multiple times and average results for accuracy

6. **Monitor system** - Check `htop` or `iostat` during tests to see system behavior

## Troubleshooting

### "tframetest command not found"

Install tframetest package first:
```bash
# Debian/Ubuntu
sudo dpkg -i tframetest_3025.12.0_amd64.deb

# RHEL/Rocky/AlmaLinux
sudo rpm -ivh tframetest-3025.12.0-1.el9.x86_64.rpm
```

### "Target directory does not exist"

Create the test directory first:
```bash
mkdir -p /path/to/test/directory
uv run tfbench.py -w 4k -n 1000 -t 8 /path/to/test/directory
```

### Permission errors

Ensure you have write access to the target directory:
```bash
ls -ld /path/to/test/directory
# Or run with appropriate permissions
```

### Tests running slowly or timing out

- Increase timeout: `--timeout 3600` (1 hour) or `--timeout 7200` (2 hours)
- Reduce frame count: `-n 100` instead of `-n 500`
- Reduce thread count: `-t 4` instead of `-t 8`
- Check if storage device is busy with other operations
- Some storage (network/USB/slow HDDs) may be legitimately slow
