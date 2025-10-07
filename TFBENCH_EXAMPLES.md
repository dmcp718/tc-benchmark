# tfbench Examples and Usage Guide

## Quick Reference

### Basic Usage

```bash
# Run standard benchmark (1 write + 2 reads, 500 frames)
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
```

## Understanding the Output

### 1. Throughput Comparison

Shows visual bar chart of MiB/s for each test:
- **Write** (green) - Initial write performance
- **Read #1** (blue) - First read, typically shows "cold cache" performance
- **Read #2** (cyan) - Second read, typically shows "warm cache" performance

The bar length is proportional to throughput, making it easy to compare at a glance.

### 2. Performance Insights

Automatically calculated metrics:

- **Cache speedup** - How much faster Read #2 is compared to Read #1
  - Example: `3.63x` means cached reads are 3.63 times faster
  - Values > 2x indicate effective caching
  - Values near 1x may indicate cache limitations or different access patterns

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

1. **Metadata** - Timestamp, target directory, frame size, threads
2. **Benchmark Results** - Complete metrics for each test:
   - test_name, operation, profile, frames, bytes
   - time_ns, time_seconds, fps, bytes_per_sec, mib_per_sec
   - min_ms, avg_ms, max_ms, range_ms
3. **Performance Insights** - Calculated metrics:
   - cache_speedup_ratio
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

### Cache Behavior Analysis

Run with multiple reads to see cache warming:

```bash
uv run tfbench.py -w 4k -n 500 -t 8 /media/storage --reads 4
```

Watch how performance improves across successive reads.

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
sudo dpkg -i tframetest_3025.1.1_amd64.deb

# RHEL/Rocky/AlmaLinux
sudo rpm -ivh tframetest-3025.1.1-1.el9.x86_64.rpm
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
