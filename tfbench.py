#!/usr/bin/env python3
"""
tfbench - TUI visualizer for tframetest benchmark results

A tool to run and visualize tframetest benchmarks with rich TUI components.
"""

import argparse
import csv
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

# Enable UTF-8 output on Windows to support Rich Unicode characters
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.layout import Layout
from rich.live import Live
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.text import Text
from rich.bar import Bar


@dataclass
class BenchmarkResult:
    """Stores parsed tframetest output"""
    profile: str
    operation: str  # "write" or "read"
    frames: int
    bytes: int
    time_ns: int
    fps: float
    bytes_per_sec: float
    mib_per_sec: float
    min_ms: float
    avg_ms: float
    max_ms: float

    # Flush-aware write metrics (write results only; populated when the
    # target is a LucidLink mount, --no-flush wasn't given, and the drain
    # was confirmed to reach 0B before --flush-timeout). None when not
    # measured (reads, non-Lucid targets, --parse mode, --no-flush, or a
    # failed/timed-out drain poll) -- never a false zero.
    drain_seconds: Optional[float] = None
    # NOTE: polling starts only after the write test completes, so this is
    # the peak observed DURING THE DRAIN, not the true high-water mark
    # during the write itself (which may have queued more before polling
    # began, and isn't sampled).
    peak_remaining_upload_mib: Optional[float] = None
    end_to_end_mib_per_sec: Optional[float] = None


# Reads (or writes) faster than this are almost certainly served from RAM
# rather than actual disk/SSD/network I/O. Used as a fallback heuristic when
# --link-speed isn't given. Even the fastest NVMe SSDs top out around 7-8 GB/s.
CACHE_THRESHOLD_MIB_S = 10240  # 10 GB/s

# Short labels so the Throughput Comparison and Detailed Statistics panels
# still render intact at 80 columns; the fuller "exceeds link speed"/"RAM
# cache" explanation lives in the warning panel's prose, not these tags.
CACHE_FLAG_LABEL = {
    "ram": "⚡ RAM CACHE",
    "link": "⚡ LOCAL CACHE",
}


def mbps_to_mib_per_sec(link_speed_mbps: float) -> float:
    """Convert a link speed in Mbps (megabits/second) to MiB/s.

    X Mbps = X/8 MB/s (decimal megabytes) = X * 1e6 / 8 bytes/s, converted
    to MiB by dividing by 2**20.
    """
    return link_speed_mbps * 1e6 / 8 / (2 ** 20)


def classify_cache_anomaly(result: BenchmarkResult,
                            link_speed_mib_s: Optional[float] = None) -> Optional[str]:
    """Flag a result whose throughput implausibly exceeds the real capacity
    of the underlying storage/link, indicating it was served from a local
    cache rather than genuine storage or network I/O.

    Returns "link" or "ram" (a key into CACHE_FLAG_LABEL), or None if the
    result isn't flagged.

    Both criteria are always checked, independently, regardless of whether
    --link-speed was given:
      - The 10 GiB/s RAM-cache heuristic (reads only) always applies.
      - The link-speed criterion (reads and writes) applies only when
        link_speed_mib_s is given.
    If a result trips both (e.g. a read is both >10 GiB/s and above the
    configured link speed), the RAM-cache label wins, since exceeding real
    RAM bandwidth is the stronger and more specific claim.
    """
    ram_flagged = result.operation == "read" and result.mib_per_sec > CACHE_THRESHOLD_MIB_S
    if ram_flagged:
        return "ram"
    if link_speed_mib_s is not None and result.mib_per_sec > link_speed_mib_s:
        return "link"
    return None


class TframetestParser:
    """Parse tframetest output into structured data"""

    PROFILE_PATTERN = r'Profile:\s*(.+)'
    RESULTS_PATTERN = r'Results\s+(write|read):'
    FRAMES_PATTERN = r'frames:\s*(\d+)'
    BYTES_PATTERN = r'bytes\s*:\s*(\d+)'
    TIME_PATTERN = r'time\s*:\s*(\d+)'
    FPS_PATTERN = r'fps\s*:\s*([\d.]+)'
    BPS_PATTERN = r'B/s\s*:\s*([\d.]+)'
    MIBPS_PATTERN = r'MiB/s\s*:\s*([\d.]+)'
    MIN_PATTERN = r'min\s*:\s*([\d.]+)\s*ms'
    AVG_PATTERN = r'avg\s*:\s*([\d.]+)\s*ms'
    MAX_PATTERN = r'max\s*:\s*([\d.]+)\s*ms'

    @classmethod
    def parse(cls, output: str) -> Optional[BenchmarkResult]:
        """Parse tframetest output text into BenchmarkResult"""
        try:
            profile = re.search(cls.PROFILE_PATTERN, output)
            results = re.search(cls.RESULTS_PATTERN, output)
            frames = re.search(cls.FRAMES_PATTERN, output)
            bytes_match = re.search(cls.BYTES_PATTERN, output)
            time_match = re.search(cls.TIME_PATTERN, output)
            fps = re.search(cls.FPS_PATTERN, output)
            bps = re.search(cls.BPS_PATTERN, output)
            mibps = re.search(cls.MIBPS_PATTERN, output)
            min_time = re.search(cls.MIN_PATTERN, output)
            avg_time = re.search(cls.AVG_PATTERN, output)
            max_time = re.search(cls.MAX_PATTERN, output)

            if not all([profile, results, frames, bytes_match, time_match,
                       fps, bps, mibps, min_time, avg_time, max_time]):
                return None

            return BenchmarkResult(
                profile=profile.group(1).strip(),
                operation=results.group(1),
                frames=int(frames.group(1)),
                bytes=int(bytes_match.group(1)),
                time_ns=int(time_match.group(1)),
                fps=float(fps.group(1)),
                bytes_per_sec=float(bps.group(1)),
                mib_per_sec=float(mibps.group(1)),
                min_ms=float(min_time.group(1)),
                avg_ms=float(avg_time.group(1)),
                max_ms=float(max_time.group(1))
            )
        except (AttributeError, ValueError) as e:
            print(f"Parse error: {e}", file=sys.stderr)
            return None

    @classmethod
    def parse_file(cls, filepath: str) -> list[BenchmarkResult]:
        """Parse a file containing one or more tframetest outputs.

        The file can contain multiple test results concatenated together.
        Each result block starts with 'Profile:' line.

        Returns:
            List of BenchmarkResult objects parsed from the file
        """
        try:
            with open(filepath, 'r') as f:
                content = f.read()
        except (IOError, OSError) as e:
            print(f"Error reading file: {e}", file=sys.stderr)
            return []

        results = []

        # Split content into blocks starting with "Profile:"
        # We use a lookahead to keep the "Profile:" in each block
        blocks = re.split(r'(?=Profile:)', content)

        for block in blocks:
            block = block.strip()
            if not block or not block.startswith('Profile:'):
                continue

            result = cls.parse(block)
            if result:
                results.append(result)

        return results

    @classmethod
    def extract_info_from_profile(cls, profile: str) -> tuple[str, int]:
        """Extract frame size and thread count from profile string.

        Profile format examples:
            "4k-64k-header, 8 threads"
            "2k-64k-header, 16 threads"
            "1m-64k-header, 4 threads"

        Returns:
            Tuple of (frame_size, threads) with defaults if not found
        """
        frame_size = "unknown"
        threads = 0  # 0 means not found/not specified

        # Extract frame size (e.g., "4k", "2k", "1m")
        size_match = re.match(r'^(\d+[kmgKMG]?)', profile)
        if size_match:
            frame_size = size_match.group(1)

        # Extract thread count (only if present in profile)
        thread_match = re.search(r'(\d+)\s*threads?', profile, re.IGNORECASE)
        if thread_match:
            threads = int(thread_match.group(1))

        return frame_size, threads


# LucidLink mounts as a loopback SMB share (macOS/Windows) or FUSE mount
# fronted by the same loopback listener; the daemon's local port varies,
# so match the guest-loopback pattern rather than a fixed port.
LUCID_MOUNT_DF_PATTERN = re.compile(r'//guest:@127\.0\.0\.1:', re.IGNORECASE)
REMAINING_UPLOAD_PATTERN = re.compile(
    r'Remaining upload:\s*([\d.]+)\s*(B|KiB|MiB|GiB|TiB)', re.IGNORECASE)
# `lucid list` header: "INSTANCE ID   FILESPACE   PORT   MODE"; data rows
# start with the instance id followed by whitespace and more columns.
LUCID_LIST_INSTANCE_PATTERN = re.compile(r'^\s*(\d+)\s+\S', re.MULTILINE)


def find_lucid_cli() -> Optional[str]:
    """Locate the lucid CLI, preferring the current `lucid` over legacy `lucid3`."""
    for name in ("lucid", "lucid3"):
        path = shutil.which(name)
        if path:
            return path
    return None


def _is_mount_point_prefix(mount_point: str, resolved_target: str) -> bool:
    """True if resolved_target is at or under mount_point.

    Compares whole path components (not a bare string prefix), so
    /Volumes/team-us-2 does NOT match a mount point of /Volumes/team-us.
    """
    if not mount_point:
        return False
    mount_point = mount_point.rstrip(os.sep) or os.sep
    if mount_point == os.sep:
        return resolved_target.startswith(os.sep)
    return resolved_target == mount_point or resolved_target.startswith(mount_point + os.sep)


def resolve_lucid_instance(target_dir: str, lucid_cmd: Optional[str]) -> Optional[list[str]]:
    """Determine whether target_dir is on a LucidLink mount, and if so,
    which linked instance (filespace) owns it.

    Returns None if target_dir isn't on any linked LucidLink filespace, or
    the lucid CLI is unavailable — callers should skip flush measurement
    entirely (silent no-op, unchanged behavior for non-LucidLink targets).

    Otherwise returns the extra CLI args to prepend to `lucid` subcommands:
      - ["--id", "<instance id>"] when a specific linked instance's mount
        point matches target_dir. This is what correctly targets the right
        upload queue when multiple filespaces are linked at once.
      - [] for a bare invocation, used when only one filespace is linked
        (or a linked instance couldn't be individually identified but a
        LucidLink mount was still detected) — matches the pre-existing
        single-filespace behavior.
    """
    if not lucid_cmd:
        return None

    try:
        resolved = str(Path(target_dir).resolve())
    except OSError:
        return None

    # Enumerate every linked instance and match its mount point. This is
    # what disambiguates correctly when multiple filespaces are linked.
    try:
        list_result = subprocess.run(
            [lucid_cmd, "list"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        list_result = None

    if list_result and list_result.returncode == 0:
        for instance_id in LUCID_LIST_INSTANCE_PATTERN.findall(list_result.stdout):
            try:
                status_result = subprocess.run(
                    [lucid_cmd, "--id", instance_id, "status"],
                    capture_output=True, text=True, timeout=10)
            except (OSError, subprocess.SubprocessError):
                continue
            if status_result.returncode != 0:
                continue
            mount_match = re.search(r'Mount point:\s*(.+)', status_result.stdout)
            if mount_match and _is_mount_point_prefix(mount_match.group(1).strip(), resolved):
                return ["--id", instance_id]

    # Fallback for the common single-filespace case, or CLI versions
    # without `lucid list`: df reporting the LucidLink loopback SMB
    # filesystem, or a bare `lucid status`'s mount point matching.
    try:
        df_result = subprocess.run(
            ["df", resolved], capture_output=True, text=True, timeout=10)
        if df_result.returncode == 0 and LUCID_MOUNT_DF_PATTERN.search(df_result.stdout):
            return []
    except (OSError, subprocess.SubprocessError):
        pass

    try:
        status_result = subprocess.run(
            [lucid_cmd, "status"], capture_output=True, text=True, timeout=10)
        if status_result.returncode == 0:
            mount_match = re.search(r'Mount point:\s*(.+)', status_result.stdout)
            if mount_match and _is_mount_point_prefix(mount_match.group(1).strip(), resolved):
                return []
    except (OSError, subprocess.SubprocessError):
        pass

    return None


def parse_size_to_mib(value: float, unit: str) -> float:
    """Convert a `lucid cache` size like '363.09KiB' / '4.51MiB' / '1.50GiB' / '1.20TiB' to MiB."""
    unit = unit.upper()
    if unit == "B":
        return value / (1024 ** 2)
    if unit == "KIB":
        return value / 1024
    if unit == "MIB":
        return value
    if unit == "GIB":
        return value * 1024
    if unit == "TIB":
        return value * 1024 * 1024
    return 0.0


def poll_lucid_cache_drain(lucid_cmd: str, instance_args: list[str], timeout: int,
                            console: Optional[Console] = None,
                            poll_interval: float = 2.0,
                            progress_interval: float = 10.0) -> Optional[tuple[float, float]]:
    """Poll `lucid cache` for 'Remaining upload:' until it actually reaches
    0B, via a successfully parsed response.

    Returns (drain_seconds, peak_remaining_mib) ONLY after confirming the
    queue drained. Returns None on any failure — a non-zero exit code, a
    subprocess error, unparseable output, or exceeding `timeout` seconds
    without confirming drain. Callers MUST treat None as "unmeasured", not
    as an instant/zero drain: publishing zeros here would misrepresent a
    failed measurement as "nothing was queued."
    """
    start = time.monotonic()
    peak_mib = 0.0
    last_progress = start

    while True:
        elapsed = time.monotonic() - start
        if elapsed >= timeout:
            return None

        try:
            result = subprocess.run(
                [lucid_cmd, *instance_args, "cache"],
                capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            return None

        if result.returncode != 0:
            return None

        match = REMAINING_UPLOAD_PATTERN.search(result.stdout)
        if not match:
            return None

        remaining_mib = parse_size_to_mib(float(match.group(1)), match.group(2))
        peak_mib = max(peak_mib, remaining_mib)

        if remaining_mib <= 0:
            return time.monotonic() - start, peak_mib

        now = time.monotonic()
        if console and now - last_progress >= progress_interval:
            console.print(
                f"[dim]  ...still draining: {remaining_mib:.2f} MiB remaining "
                f"({now - start:.0f}s elapsed)[/dim]")
            last_progress = now

        time.sleep(poll_interval)


class BenchmarkRunner:
    """Execute tframetest and capture results"""

    def __init__(self, console: Console, binary_override: Optional[str] = None,
                 link_speed_mib_s: Optional[float] = None):
        self.console = console
        self.link_speed_mib_s = link_speed_mib_s
        self.tframetest_cmd = binary_override or self._find_tframetest()

    def _find_tframetest(self) -> str:
        """Find the appropriate tframetest binary for the current platform"""
        script_dir = Path(__file__).parent

        # On macOS, check for system-installed binary first
        if platform.system() == "Darwin":
            # Check if tframetest is installed in /usr/local/bin (via installer)
            system_binary = Path("/usr/local/bin/tframetest")
            if system_binary.exists():
                return str(system_binary)

            # Check PATH
            which_result = shutil.which("tframetest")
            if which_result:
                return which_result

            # Not installed - check if installer is available
            installer_pkg = script_dir / "macos-installer" / "build" / "tframetest-3025.12.0-macos-arm64.pkg"
            if installer_pkg.exists():
                self._prompt_install_macos(installer_pkg)
                # After prompting, check again if user installed
                if system_binary.exists():
                    return str(system_binary)

            # Fall back to local binary
            macos_binary = script_dir / "tframetest-macos"
            if macos_binary.exists():
                return str(macos_binary)

        # On Windows, check for tframetest.exe in script directory or PATH
        if platform.system() == "Windows":
            local_exe = script_dir / "tframetest.exe"
            if local_exe.exists():
                return str(local_exe)

            which_result = shutil.which("tframetest")
            if which_result:
                return which_result

        # Check for local binary
        local_binary = script_dir / "tframetest"
        if local_binary.exists() and local_binary.is_file():
            return str(local_binary)

        # Fall back to PATH
        return "tframetest"

    def _prompt_install_macos(self, installer_path: Path) -> None:
        """Prompt user to install tframetest on macOS"""
        self.console.print()
        self.console.print("[yellow]⚠ tframetest is not installed on your system[/yellow]")
        self.console.print()
        self.console.print(f"An installer package is available at:")
        self.console.print(f"  [cyan]{installer_path}[/cyan]")
        self.console.print()
        self.console.print("Would you like to install it now? This will:")
        self.console.print("  • Install tframetest to /usr/local/bin/")
        self.console.print("  • Require administrator password")
        self.console.print()

        response = input("Install now? [y/N]: ").strip().lower()

        if response in ['y', 'yes']:
            self.console.print()
            self.console.print("[cyan]Installing tframetest...[/cyan]")
            try:
                result = subprocess.run(
                    ["sudo", "installer", "-pkg", str(installer_path), "-target", "/"],
                    check=True
                )
                self.console.print("[green]✓[/green] tframetest installed successfully!")
                self.console.print()
            except subprocess.CalledProcessError as e:
                self.console.print(f"[red]✗[/red] Installation failed: {e}")
                self.console.print()
        else:
            self.console.print()
            self.console.print("[yellow]Skipping installation.[/yellow]")
            self.console.print("You can install it later by running:")
            self.console.print(f"  [dim]sudo installer -pkg {installer_path} -target /[/dim]")
            self.console.print()
            self.console.print("Or double-click the .pkg file to use the GUI installer.")
            self.console.print()

    def run_test(self, write_size: str, num_frames: int, threads: int,
                 target_dir: str, is_read: bool = False, timeout: int = 1800) -> Optional[BenchmarkResult]:
        """Run a single tframetest command and return parsed results

        Args:
            timeout: Timeout in seconds (default 1800 = 30 minutes)
        """

        # Build command
        cmd = [self.tframetest_cmd]
        if is_read:
            cmd.extend(["-r"])
        else:
            cmd.extend(["-w", write_size])
        cmd.extend(["-n", str(num_frames), "-t", str(threads), target_dir])

        # Show what we're running
        operation = "Read" if is_read else "Write"
        self.console.print(f"\n[bold cyan]Running {operation} test:[/bold cyan] {' '.join(cmd)}")
        self.console.print(f"[dim](Timeout: {timeout}s)[/dim]")

        try:
            # Execute command
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )

            if result.returncode != 0:
                # On Windows, tframetest may return non-zero exit codes even on
                # success (e.g. heap cleanup errors at process exit). If we got
                # valid output on stdout, try to parse it before giving up.
                if not result.stdout or not result.stdout.strip():
                    self.console.print(f"[bold red]Error:[/bold red] tframetest failed with code {result.returncode}")
                    self.console.print(result.stderr)
                    return None

            # Parse output
            parsed = TframetestParser.parse(result.stdout)
            if parsed:
                # Add cache/local-cache indicator when throughput exceeds
                # what real storage or the link could plausibly sustain
                anomaly = classify_cache_anomaly(parsed, self.link_speed_mib_s)
                cache_indicator = f" [yellow bold]{CACHE_FLAG_LABEL[anomaly]}[/yellow bold]" if anomaly else ""
                self.console.print(f"[green]✓[/green] {operation} test completed: {parsed.mib_per_sec:.2f} MiB/s{cache_indicator}")
                self.console.print(f"[dim]Completed {parsed.frames} frames in {parsed.time_ns / 1e9:.1f}s[/dim]")

                # Warning when flagged
                if anomaly == "ram":
                    self.console.print(f"[yellow]⚠ Speed >{parsed.mib_per_sec/1024:.1f} GB/s indicates RAM cache, not disk I/O[/yellow]")
                elif anomaly == "link":
                    self.console.print(f"[yellow]⚠ Speed {parsed.mib_per_sec:.2f} MiB/s exceeds the configured link speed — served from local cache, not the remote storage tier[/yellow]")
            else:
                self.console.print("[bold red]Error:[/bold red] Failed to parse tframetest output")
                self.console.print(result.stdout)

            return parsed

        except KeyboardInterrupt:
            self.console.print(f"\n[bold yellow]⚠ {operation} test interrupted by user[/bold yellow]")
            raise
        except subprocess.TimeoutExpired as e:
            self.console.print(f"[bold red]Error:[/bold red] Test timed out after {timeout}s")
            # Try to parse partial output if available
            if e.stdout:
                self.console.print("[yellow]Attempting to parse partial output...[/yellow]")
                parsed = TframetestParser.parse(e.stdout)
                if parsed:
                    self.console.print(f"[yellow]⚠[/yellow] Partial results: {parsed.frames} frames completed")
                    return parsed
            return None
        except FileNotFoundError:
            self.console.print("[bold red]Error:[/bold red] tframetest command not found")
            return None

    def run_benchmark_suite(self, write_size: str, num_frames: int, threads: int,
                           target_dir: str, num_reads: int = 2, timeout: int = 1800,
                           flush: bool = True, flush_timeout: int = 600) -> list[BenchmarkResult]:
        """Run full benchmark: 1 write + N reads"""
        results = []

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=self.console
        ) as progress:
            total_tests = 1 + num_reads
            task = progress.add_task("[cyan]Running benchmark suite...", total=total_tests)

            # Write test
            write_result = self.run_test(write_size, num_frames, threads, target_dir, is_read=False, timeout=timeout)
            if write_result:
                results.append(write_result)
                if flush:
                    self._measure_flush(write_result, target_dir, flush_timeout)
            progress.update(task, advance=1)

            # Read tests
            for i in range(num_reads):
                read_result = self.run_test(write_size, num_frames, threads, target_dir, is_read=True, timeout=timeout)
                if read_result:
                    results.append(read_result)
                progress.update(task, advance=1)

        return results

    def _measure_flush(self, write_result: BenchmarkResult, target_dir: str, flush_timeout: int) -> None:
        """After a write test, if the target is a LucidLink mount, poll the
        upload queue until it drains and record end-to-end throughput.

        tframetest's reported write MiB/s reflects cache-ingest speed (the
        local daemon acking the write) on write-back storage; this measures
        how long the queued bytes actually take to reach the remote object
        store, so both numbers can be reported side by side. Non-LucidLink
        targets (or missing lucid CLI) are left unchanged — this is a no-op.

        If the drain can't be confirmed (lucid CLI error, unparseable
        output, or flush_timeout exceeded), a warning is printed and no
        flush metrics are recorded — write_result's flush fields stay None
        rather than being published as a false "zero" measurement.
        """
        lucid_cmd = find_lucid_cli()
        instance_args = resolve_lucid_instance(target_dir, lucid_cmd)
        if instance_args is None:
            return

        self.console.print(
            f"[dim]Detected LucidLink mount — polling upload drain (timeout: {flush_timeout}s)...[/dim]")
        drain_result = poll_lucid_cache_drain(
            lucid_cmd, instance_args, flush_timeout, console=self.console)

        if drain_result is None:
            self.console.print(
                "[yellow]⚠ Could not confirm the upload queue drained "
                "(lucid CLI error, unparseable output, or --flush-timeout exceeded) — "
                "flush metrics omitted[/yellow]")
            return

        drain_seconds, peak_mib = drain_result
        write_time_s = write_result.time_ns / 1e9
        total_mib = write_result.bytes / (1024 ** 2)
        total_time_s = write_time_s + drain_seconds
        end_to_end = total_mib / total_time_s if total_time_s > 0 else 0.0

        write_result.drain_seconds = drain_seconds
        write_result.peak_remaining_upload_mib = peak_mib
        write_result.end_to_end_mib_per_sec = end_to_end

        self.console.print(
            f"[green]✓[/green] Flush complete: drained in {drain_seconds:.1f}s "
            f"(peak queued during drain: {peak_mib:.2f} MiB) — "
            f"end-to-end: [cyan]{end_to_end:.2f} MiB/s[/cyan] vs "
            f"cache ingest: {write_result.mib_per_sec:.2f} MiB/s"
        )


class BenchmarkVisualizer:
    """Create Rich TUI visualizations for benchmark results"""

    def __init__(self, console: Console, link_speed_mib_s: Optional[float] = None):
        self.console = console
        self.link_speed_mib_s = link_speed_mib_s

    def create_throughput_chart(self, results: list[BenchmarkResult]) -> Panel:
        """Create bar chart comparing throughput across tests"""
        BAR_CHARS = 20

        table = Table.grid(padding=(0, 1))
        table.add_column(style="bold", width=9, no_wrap=True)
        table.add_column(width=BAR_CHARS, no_wrap=True)
        table.add_column(style="cyan", justify="right", width=8, no_wrap=True)
        table.add_column(width=15, no_wrap=True)

        # Find max for scaling
        max_mib = max(r.mib_per_sec for r in results)

        colors = ["green", "blue", "cyan", "magenta", "yellow"]

        for i, result in enumerate(results):
            # Determine label (neutral — no cold/warm assumption)
            if result.operation == "write":
                label = "Write"
                color = colors[0]
            else:
                read_num = sum(1 for r in results[:i+1] if r.operation == "read")
                label = f"Read #{read_num}"
                color = colors[min(read_num, len(colors)-1)]

            anomaly = classify_cache_anomaly(result, self.link_speed_mib_s)
            flag_label = f"[yellow bold]{CACHE_FLAG_LABEL[anomaly]}[/yellow bold]" if anomaly else ""

            # Create bar
            bar_width = int((result.mib_per_sec / max_mib) * BAR_CHARS)
            bar = "█" * bar_width + "░" * (BAR_CHARS - bar_width)

            # Add row
            table.add_row(
                f"[{color}]{label}[/{color}]",
                f"[{color}]{bar}[/{color}]",
                f"{result.mib_per_sec:.2f}",
                flag_label
            )

        return Panel(table, title="[bold]Throughput Comparison (MiB/s)[/bold]", border_style="blue")

    def create_latency_chart(self, results: list[BenchmarkResult]) -> Panel:
        """Create latency comparison chart"""
        table = Table(show_header=True, header_style="bold magenta", border_style="blue")
        table.add_column("Test", style="bold")
        table.add_column("Min (ms)", justify="right")
        table.add_column("Avg (ms)", justify="right")
        table.add_column("Max (ms)", justify="right")
        table.add_column("Range (ms)", justify="right")

        for i, result in enumerate(results):
            # Determine label
            if result.operation == "write":
                label = "Write"
            else:
                read_num = sum(1 for r in results[:i+1] if r.operation == "read")
                label = f"Read #{read_num}"

            # Calculate range
            range_ms = result.max_ms - result.min_ms

            table.add_row(
                label,
                f"{result.min_ms:.1f}",
                f"{result.avg_ms:.1f}",
                f"{result.max_ms:.1f}",
                f"{range_ms:.1f}"
            )

        return Panel(table, title="[bold]Latency Statistics[/bold]", border_style="blue")

    def create_insights_panel(self, results: list[BenchmarkResult], threads: int = 1) -> Panel:
        """Calculate and display performance insights"""
        text = Text()

        # Find write and reads
        write_result = next((r for r in results if r.operation == "write"), None)
        read_results = [r for r in results if r.operation == "read"]

        # Write performance stats
        if write_result:
            text.append("Write Performance:\n", style="bold green")
            write_anomaly = classify_cache_anomaly(write_result, self.link_speed_mib_s)
            ingest_label = " (cache ingest)" if write_result.drain_seconds is not None else ""
            text.append(f"  • Throughput{ingest_label}: ", style="dim")
            text.append(f"{write_result.mib_per_sec:.2f} MiB/s ", style="green")
            text.append(f"({write_result.fps:.2f} fps)", style="dim")
            if write_anomaly:
                text.append(f"  {CACHE_FLAG_LABEL[write_anomaly]}", style="yellow bold")
            text.append("\n")
            text.append(f"  • Avg latency: ", style="dim")
            text.append(f"{write_result.avg_ms:.1f} ms", style="yellow")
            text.append(f" (min: {write_result.min_ms:.1f}, max: {write_result.max_ms:.1f})\n", style="dim")
            text.append(f"  • Total time: ", style="dim")
            text.append(f"{write_result.time_ns / 1e9:.1f}s ", style="cyan")
            text.append(f"for {write_result.frames:,} frames\n", style="dim")

            if write_result.drain_seconds is not None:
                text.append(f"  • Drain time (upload flush): ", style="dim")
                text.append(f"{write_result.drain_seconds:.1f}s ", style="yellow")
                text.append(f"(peak queued during drain: {write_result.peak_remaining_upload_mib:.2f} MiB)\n", style="dim")
                text.append(f"  • End-to-end (flushed): ", style="dim")
                text.append(f"{write_result.end_to_end_mib_per_sec:.2f} MiB/s\n", style="bold cyan")
            text.append("\n")

        # Read performance comparisons
        if read_results:
            text.append("Read Performance:\n", style="bold blue")
            if len(read_results) >= 2:
                # Read repeatability (read2 vs read1) — both reads run
                # against files that were just written, so neither is
                # meaningfully "cold"; this compares run-to-run consistency,
                # not a cache warm-up effect.
                repeatability = read_results[1].mib_per_sec / read_results[0].mib_per_sec
                text.append(f"  • Read repeatability (Read #2 / Read #1): ", style="dim")
                text.append(f"{repeatability:.2f}x\n", style="green bold")

                # Best read vs write
                if write_result:
                    best_read = max(read_results, key=lambda r: r.mib_per_sec)
                    read_write_ratio = best_read.mib_per_sec / write_result.mib_per_sec
                    text.append(f"  • Read/Write ratio: ", style="dim")
                    text.append(f"{read_write_ratio:.2f}x\n", style="cyan bold")

                # Latency improvement
                latency_improvement = (read_results[0].avg_ms - read_results[1].avg_ms) / read_results[0].avg_ms * 100
                text.append(f"  • Latency delta (Read #2 vs #1): ", style="dim")
                text.append(f"{latency_improvement:.1f}%\n", style="yellow bold")

            # Show all read results (neutral labels — no cold/warm assumption)
            for i, read_result in enumerate(read_results, 1):
                anomaly = classify_cache_anomaly(read_result, self.link_speed_mib_s)
                if anomaly:
                    label_suffix = f" {CACHE_FLAG_LABEL[anomaly]}"
                    style = "yellow bold"
                else:
                    label_suffix = ""
                    style = "dim"
                text.append(f"  • Read #{i}{label_suffix}: ", style=style)
                text.append(f"{read_result.mib_per_sec:.2f} MiB/s, ", style="cyan")
                text.append(f"{read_result.avg_ms:.1f} ms avg\n", style="dim")

        # Test configuration
        if results:
            r = results[0]
            text.append("\n")
            text.append("Configuration:\n", style="dim")
            text.append(f"  Frames: {r.frames:,} | ", style="dim")
            text.append(f"Data: {r.bytes / (1024**3):.2f} GiB", style="dim")
            if threads:
                text.append(f" | Threads: {threads}", style="dim")

        return Panel(text, title="[bold]Performance Insights[/bold]", border_style="green")

    def create_detailed_table(self, results: list[BenchmarkResult]) -> Panel:
        """Create detailed statistics table. Column widths are kept narrow
        and no_wrap so the panel renders intact at 80 columns instead of
        wrapping the Flag column across multiple lines."""
        table = Table(show_header=True, header_style="bold cyan", border_style="blue",
                     padding=(0, 1))
        table.add_column("Test", style="bold", width=8, no_wrap=True, overflow="ellipsis")
        table.add_column("Profile", width=8, no_wrap=True, overflow="ellipsis")
        table.add_column("Frames", justify="right", width=6, no_wrap=True, overflow="ellipsis")
        table.add_column("FPS", justify="right", width=5, no_wrap=True, overflow="ellipsis")
        table.add_column("MiB/s", justify="right", width=8, no_wrap=True, overflow="ellipsis")
        table.add_column("Time (s)", justify="right", width=7, no_wrap=True, overflow="ellipsis")
        table.add_column("Flag", width=15, no_wrap=True, overflow="ellipsis")

        for i, result in enumerate(results):
            # Determine label
            if result.operation == "write":
                label = "Write"
                style = "green"
            else:
                read_num = sum(1 for r in results[:i+1] if r.operation == "read")
                label = f"Read #{read_num}"
                style = "cyan" if read_num == 2 else "blue"

            anomaly = classify_cache_anomaly(result, self.link_speed_mib_s)
            flag = f"[yellow bold]{CACHE_FLAG_LABEL[anomaly]}[/yellow bold]" if anomaly else ""

            table.add_row(
                f"[{style}]{label}[/{style}]",
                result.profile,
                f"{result.frames:,}",
                f"{result.fps:.2f}",
                f"{result.mib_per_sec:.2f}",
                f"{result.time_ns / 1e9:.2f}",
                flag
            )

        return Panel(table, title="[bold]Detailed Statistics[/bold]", border_style="blue")

    def create_flush_panel(self, results: list[BenchmarkResult]) -> Optional[Panel]:
        """Create a panel summarizing LucidLink upload-flush metrics for the
        write test, if flush measurement was performed. Returns None
        otherwise (non-LucidLink target, --no-flush, or --parse mode)."""
        write_result = next((r for r in results if r.operation == "write"), None)
        if not write_result or write_result.drain_seconds is None:
            return None

        text = Text()
        text.append("Cache ingest (tframetest write): ", style="dim")
        text.append(f"{write_result.mib_per_sec:.2f} MiB/s\n", style="green")
        text.append("Drain time (upload flush): ", style="dim")
        text.append(f"{write_result.drain_seconds:.1f}s\n", style="yellow")
        text.append("Peak queued (observed during drain): ", style="dim")
        text.append(f"{write_result.peak_remaining_upload_mib:.2f} MiB\n", style="yellow")
        text.append("End-to-end (flushed): ", style="dim")
        text.append(f"{write_result.end_to_end_mib_per_sec:.2f} MiB/s\n", style="bold cyan")

        return Panel(text, title="[bold]LucidLink Flush Metrics[/bold]", border_style="cyan")

    def display_results(self, results: list[BenchmarkResult], target_dir: str,
                       write_size: str, threads: int):
        """Display complete benchmark visualization"""
        if not results:
            self.console.print("[bold red]No results to display[/bold red]")
            return

        # Check for incomplete tests
        frame_counts = [r.frames for r in results]
        if len(set(frame_counts)) > 1:
            self.console.print()
            self.console.print("[bold yellow]⚠ Warning:[/bold yellow] Tests completed different frame counts:")
            for i, result in enumerate(results):
                op_label = "Write" if result.operation == "write" else f"Read #{sum(1 for r in results[:i+1] if r.operation == 'read')}"
                self.console.print(f"  {op_label}: {result.frames:,} frames")
            self.console.print()

        # Header
        self.console.print()
        self.console.rule(f"[bold blue]tframetest Benchmark Results[/bold blue]")
        self.console.print()

        # Summary info
        summary = Text()
        summary.append(f"Target: ", style="bold")
        summary.append(f"{target_dir} | ", style="cyan")
        summary.append(f"Frame Size: ", style="bold")
        summary.append(f"{write_size} | ", style="yellow")
        summary.append(f"Frames: ", style="bold")
        # Show frame range if inconsistent
        if len(set(frame_counts)) > 1:
            summary.append(f"{min(frame_counts):,}-{max(frame_counts):,}", style="yellow")
        else:
            summary.append(f"{results[0].frames:,}", style="magenta")
        # Only show threads if specified (non-zero)
        if threads:
            summary.append(f" | ", style="dim")
            summary.append(f"Threads: ", style="bold")
            summary.append(f"{threads}", style="green")
        self.console.print(Panel(summary, border_style="blue"))
        self.console.print()

        # Main visualizations
        self.console.print(self.create_throughput_chart(results))
        self.console.print()
        self.console.print(self.create_insights_panel(results, threads))
        self.console.print()
        self.console.print(self.create_latency_chart(results))
        self.console.print()
        self.console.print(self.create_detailed_table(results))
        self.console.print()

        flush_panel = self.create_flush_panel(results)
        if flush_panel:
            self.console.print(flush_panel)
            self.console.print()

        # Add a warning if any result was flagged as implausibly fast for
        # real storage/network I/O (RAM cache, or exceeds --link-speed)
        flagged = [classify_cache_anomaly(r, self.link_speed_mib_s) for r in results]
        flagged = [a for a in flagged if a]
        if flagged:
            warning = Text()
            if "link" in flagged:
                warning.append("⚡ LOCAL CACHE DETECTED (exceeds link speed)\n\n", style="bold yellow")
                warning.append("One or more results exceed the theoretical throughput of the configured link speed. ", style="yellow")
                warning.append("That data was served from a local cache layer, not the remote storage tier.\n\n", style="yellow")
            if "ram" in flagged:
                warning.append("⚡ RAM CACHE DETECTED\n\n", style="bold yellow")
                warning.append("Read speeds exceeding 10 GB/s indicate the data was served from RAM cache, ", style="yellow")
                warning.append("not from the actual disk/SSD. ", style="yellow")
                warning.append("This shows cache performance, not storage I/O performance.\n\n", style="yellow")
            warning.append("To measure actual sustained storage/network performance:\n", style="dim")
            warning.append("  • Use a larger dataset that exceeds available RAM and local cache\n", style="dim")
            warning.append("  • Clear system cache before testing (macOS: ", style="dim")
            warning.append("sudo purge", style="cyan")
            warning.append(", Linux: ", style="dim")
            warning.append("sync; echo 3 | sudo tee /proc/sys/vm/drop_caches", style="cyan")
            warning.append(")\n", style="dim")
            warning.append("  • Pass --link-speed to flag results exceeding your link's real capacity\n", style="dim")
            self.console.print(Panel(warning, title="[bold yellow]⚠ Performance Note[/bold yellow]", border_style="yellow"))
            self.console.print()

    def export_csv(self, results: list[BenchmarkResult], csv_path: str,
                   target_dir: str, write_size: str, threads: int) -> bool:
        """Export benchmark results to CSV file"""
        try:
            with open(csv_path, 'w', newline='') as csvfile:
                # Write metadata header
                writer = csv.writer(csvfile)
                writer.writerow(['# Benchmark Metadata'])
                writer.writerow(['timestamp', datetime.now().isoformat()])
                writer.writerow(['target_directory', target_dir])
                writer.writerow(['frame_size', write_size])
                writer.writerow(['threads', threads])
                if self.link_speed_mib_s is not None:
                    writer.writerow(['link_speed_mib_per_sec', f"{self.link_speed_mib_s:.4f}"])
                writer.writerow([])

                # Write results header
                writer.writerow(['# Benchmark Results'])
                writer.writerow([
                    'test_name',
                    'operation',
                    'profile',
                    'frames',
                    'bytes',
                    'time_ns',
                    'time_seconds',
                    'fps',
                    'bytes_per_sec',
                    'mib_per_sec',
                    'min_ms',
                    'avg_ms',
                    'max_ms',
                    'range_ms',
                    'cache_flag',
                    'drain_seconds',
                    'peak_remaining_upload_mib',
                    'end_to_end_mib_per_sec'
                ])

                # Write results data
                for i, result in enumerate(results):
                    if result.operation == "write":
                        test_name = "Write"
                    else:
                        read_num = sum(1 for r in results[:i+1] if r.operation == "read")
                        test_name = f"Read_{read_num}"

                    range_ms = result.max_ms - result.min_ms
                    anomaly = classify_cache_anomaly(result, self.link_speed_mib_s) or ""

                    writer.writerow([
                        test_name,
                        result.operation,
                        result.profile,
                        result.frames,
                        result.bytes,
                        result.time_ns,
                        result.time_ns / 1e9,
                        result.fps,
                        result.bytes_per_sec,
                        result.mib_per_sec,
                        result.min_ms,
                        result.avg_ms,
                        result.max_ms,
                        range_ms,
                        anomaly,
                        result.drain_seconds if result.drain_seconds is not None else '',
                        result.peak_remaining_upload_mib if result.peak_remaining_upload_mib is not None else '',
                        result.end_to_end_mib_per_sec if result.end_to_end_mib_per_sec is not None else ''
                    ])

                # Write calculated insights if available
                write_result = next((r for r in results if r.operation == "write"), None)
                read_results = [r for r in results if r.operation == "read"]

                if write_result and len(read_results) >= 2:
                    writer.writerow([])
                    writer.writerow(['# Performance Insights'])
                    writer.writerow(['metric', 'value'])

                    repeatability = read_results[1].mib_per_sec / read_results[0].mib_per_sec
                    writer.writerow(['read_repeatability_ratio', f"{repeatability:.4f}"])

                    best_read = max(read_results, key=lambda r: r.mib_per_sec)
                    read_write_ratio = best_read.mib_per_sec / write_result.mib_per_sec
                    writer.writerow(['read_write_ratio', f"{read_write_ratio:.4f}"])

                    latency_improvement = (read_results[0].avg_ms - read_results[1].avg_ms) / read_results[0].avg_ms * 100
                    writer.writerow(['latency_improvement_percent', f"{latency_improvement:.2f}"])

            return True
        except Exception as e:
            self.console.print(f"[bold red]Error writing CSV:[/bold red] {e}")
            return False


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="TUI visualizer for tframetest benchmarks",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run full benchmark suite (1 write + 2 reads)
  uv run tfbench.py -w 4k -n 500 -t 8 /media/tc-mngr/tftest

  # Run with CSV export
  uv run tfbench.py -w 4k -n 500 -t 8 /mnt/storage --csv results.csv

  # Run with more frames and custom timeout
  uv run tfbench.py -w 4k -n 2000 -t 16 /mnt/storage --timeout 3600

  # Multiple read iterations to observe cache behavior
  uv run tfbench.py -w 4k -n 500 -t 8 /mnt/storage --reads 4

  # Flag results exceeding a 1 Gbps link's real capacity (~119 MiB/s)
  uv run tfbench.py -w 4k -n 500 -t 8 /mnt/storage --link-speed 1000

  # Use a specific tframetest binary instead of auto-discovery
  uv run tfbench.py -w 4k -n 500 -t 8 /mnt/storage --binary ./build/tframetest

  # Skip LucidLink upload-drain measurement after the write test
  uv run tfbench.py -w 4k -n 500 -t 8 /mnt/lucid-mount --no-flush

  # Parse existing tframetest output
  uv run tfbench.py --parse results.txt
        """
    )

    parser.add_argument("-w", "--write-size", default="4k",
                       help="Frame size for write test (e.g., 2k, 4k, 1m)")
    parser.add_argument("-n", "--frames", type=int, default=500,
                       help="Number of frames to test (default: 500)")
    parser.add_argument("-t", "--threads", type=int, default=0,
                       help="Number of threads to use. Default: 0, which means "
                            "8 in run mode (i.e. an actual run defaults to 8 "
                            "threads), or auto-detect from the profile string "
                            "in --parse mode")
    parser.add_argument("--reads", type=int, default=3,
                       help="Number of read tests to run (default: 3)")
    parser.add_argument("--timeout", type=int, default=1800,
                       help="Timeout per test in seconds (default: 1800 = 30 minutes)")
    parser.add_argument("--csv", metavar="FILE",
                       help="Export results to CSV file")
    parser.add_argument("--parse", metavar="FILE",
                       help="Parse and visualize existing tframetest output file")
    parser.add_argument("--binary", metavar="PATH",
                       help="Path to the tframetest binary to run, overriding "
                            "auto-discovery (env: TFBENCH_BINARY)")
    parser.add_argument("--no-flush", action="store_true",
                       help="Skip polling LucidLink's upload queue after the write "
                            "test, even if the target is a LucidLink mount")
    parser.add_argument("--flush-timeout", type=int, default=600, metavar="SECONDS",
                       help="Max seconds to wait for the LucidLink upload queue to "
                            "drain after the write test (default: 600 = 10 minutes). "
                            "Independent of --timeout, which only bounds each "
                            "tframetest run itself")
    parser.add_argument("--link-speed", type=float, metavar="MBPS",
                       help="Network link speed in Mbps (megabits/second, not "
                            "MiB/s) used to flag reads/writes that exceed the "
                            "link's theoretical throughput as served from a "
                            "local cache rather than genuine storage/network "
                            "I/O. The 10 GiB/s RAM-cache heuristic (reads only) "
                            "is always checked as well and takes precedence "
                            "when both apply")
    parser.add_argument("target_dir", nargs="?",
                       help="Target directory for benchmark tests")

    args = parser.parse_args()

    console = Console(force_terminal=True)

    if args.flush_timeout <= 0:
        console.print(f"[bold red]Error:[/bold red] --flush-timeout must be a positive number of seconds, got {args.flush_timeout}")
        return 1

    if args.link_speed is not None and args.link_speed <= 0:
        console.print(f"[bold red]Error:[/bold red] --link-speed must be a positive number of Mbps, got {args.link_speed}")
        return 1

    link_speed_mib_s = mbps_to_mib_per_sec(args.link_speed) if args.link_speed is not None else None

    # Parse mode
    if args.parse:
        parse_path = Path(args.parse)
        if not parse_path.exists():
            console.print(f"[bold red]Error:[/bold red] File not found: {args.parse}")
            return 1

        console.print(f"[cyan]Parsing tframetest output from:[/cyan] {args.parse}")
        results = TframetestParser.parse_file(args.parse)

        if not results:
            console.print("[bold red]Error:[/bold red] No valid tframetest results found in file")
            console.print("[dim]Expected format: tframetest output with 'Profile:', 'Results:', etc.[/dim]")
            return 1

        console.print(f"[green]✓[/green] Parsed {len(results)} test result(s)")

        # Extract frame size from first result's profile
        frame_size, profile_threads = TframetestParser.extract_info_from_profile(results[0].profile)

        # Use --threads if provided, otherwise try to extract from profile
        threads = args.threads if args.threads else profile_threads

        # Display visualization
        visualizer = BenchmarkVisualizer(console, link_speed_mib_s=link_speed_mib_s)
        visualizer.display_results(results, f"[parsed from {parse_path.name}]", frame_size, threads)

        # Export to CSV if requested
        if args.csv:
            csv_path = args.csv
            console.print(f"\n[cyan]Exporting results to CSV:[/cyan] {csv_path}")
            if visualizer.export_csv(results, csv_path, str(parse_path), frame_size, threads):
                console.print(f"[green]✓[/green] CSV exported successfully")
            else:
                console.print(f"[red]✗[/red] Failed to export CSV")
                return 1

        return 0

    # Run mode
    if not args.target_dir:
        console.print("[bold red]Error:[/bold red] target_dir is required when not using --parse")
        parser.print_help()
        return 1

    # Validate target directory
    target_path = Path(args.target_dir)
    if not target_path.exists():
        console.print(f"[bold red]Error:[/bold red] Target directory does not exist: {args.target_dir}")
        return 1

    # Default to 8 threads for run mode if not specified
    threads = args.threads if args.threads else 8

    # --binary overrides auto-discovery; falls back to TFBENCH_BINARY env var
    binary_override = args.binary or os.environ.get("TFBENCH_BINARY")

    # Run benchmark suite
    runner = BenchmarkRunner(console, binary_override=binary_override,
                             link_speed_mib_s=link_speed_mib_s)
    try:
        results = runner.run_benchmark_suite(
            args.write_size,
            args.frames,
            threads,
            args.target_dir,
            args.reads,
            args.timeout,
            flush=not args.no_flush,
            flush_timeout=args.flush_timeout
        )
    except KeyboardInterrupt:
        console.print("\n[bold yellow]Benchmark interrupted by user. Exiting cleanly.[/bold yellow]")
        return 130  # Standard exit code for SIGINT

    if not results:
        console.print("[bold red]No benchmark results obtained[/bold red]")
        return 1

    # Display visualization
    visualizer = BenchmarkVisualizer(console, link_speed_mib_s=link_speed_mib_s)
    visualizer.display_results(results, args.target_dir, args.write_size, threads)

    # Export to CSV if requested
    if args.csv:
        csv_path = args.csv
        console.print(f"\n[cyan]Exporting results to CSV:[/cyan] {csv_path}")
        if visualizer.export_csv(results, csv_path, args.target_dir, args.write_size, threads):
            console.print(f"[green]✓[/green] CSV exported successfully")
        else:
            console.print(f"[red]✗[/red] Failed to export CSV")
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
