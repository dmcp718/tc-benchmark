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
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

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

    @property
    def is_cached(self) -> bool:
        """Detect if this result is likely from RAM cache rather than disk I/O.

        Reads exceeding 10 GB/s (10240 MiB/s) are almost certainly hitting RAM cache
        rather than actual disk/SSD. Even the fastest NVMe SSDs top out around 7-8 GB/s.
        """
        CACHE_THRESHOLD_MIB_S = 10240  # 10 GB/s
        return self.operation == "read" and self.mib_per_sec > CACHE_THRESHOLD_MIB_S


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


class BenchmarkRunner:
    """Execute tframetest and capture results"""

    def __init__(self, console: Console):
        self.console = console
        self.tframetest_cmd = self._find_tframetest()

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
            installer_pkg = script_dir / "macos-installer" / "build" / "tframetest-3025.1.1-macos-arm64.pkg"
            if installer_pkg.exists():
                self._prompt_install_macos(installer_pkg)
                # After prompting, check again if user installed
                if system_binary.exists():
                    return str(system_binary)

            # Fall back to local binary
            macos_binary = script_dir / "tframetest-macos"
            if macos_binary.exists():
                return str(macos_binary)

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
                self.console.print(f"[bold red]Error:[/bold red] tframetest failed with code {result.returncode}")
                self.console.print(result.stderr)
                return None

            # Parse output
            parsed = TframetestParser.parse(result.stdout)
            if parsed:
                # Add cache indicator for cached reads
                cache_indicator = " ⚡ [yellow bold]RAM CACHE[/yellow bold]" if parsed.is_cached else ""
                self.console.print(f"[green]✓[/green] {operation} test completed: {parsed.mib_per_sec:.2f} MiB/s{cache_indicator}")
                self.console.print(f"[dim]Completed {parsed.frames} frames in {parsed.time_ns / 1e9:.1f}s[/dim]")

                # Warning for cached reads
                if parsed.is_cached:
                    self.console.print(f"[yellow]⚠ Speed >{parsed.mib_per_sec/1024:.1f} GB/s indicates RAM cache, not disk I/O[/yellow]")
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
                           target_dir: str, num_reads: int = 2, timeout: int = 1800) -> list[BenchmarkResult]:
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
            progress.update(task, advance=1)

            # Read tests
            for i in range(num_reads):
                read_result = self.run_test(write_size, num_frames, threads, target_dir, is_read=True, timeout=timeout)
                if read_result:
                    results.append(read_result)
                progress.update(task, advance=1)

        return results


class BenchmarkVisualizer:
    """Create Rich TUI visualizations for benchmark results"""

    def __init__(self, console: Console):
        self.console = console

    def create_throughput_chart(self, results: list[BenchmarkResult]) -> Panel:
        """Create bar chart comparing throughput across tests"""
        table = Table.grid(padding=(0, 2))
        table.add_column(style="bold", width=12)
        table.add_column(width=40)
        table.add_column(style="cyan", justify="right", width=10)
        table.add_column(width=15)

        # Find max for scaling
        max_mib = max(r.mib_per_sec for r in results)

        colors = ["green", "blue", "cyan", "magenta", "yellow"]

        for i, result in enumerate(results):
            # Determine label
            if result.operation == "write":
                label = "Write"
                color = colors[0]
                cache_label = ""
            else:
                read_num = sum(1 for r in results[:i+1] if r.operation == "read")
                label = f"Read #{read_num}"
                color = colors[min(read_num, len(colors)-1)]

                # Add cache indicator with RAM cache detection
                if result.is_cached:
                    cache_label = "⚡ [yellow bold]RAM CACHE[/yellow bold]"
                elif read_num == 1:
                    cache_label = "(cold cache)"
                elif read_num == 2:
                    cache_label = "(warm cache)"
                else:
                    cache_label = f"(read {read_num})"

            # Create bar
            bar_width = int((result.mib_per_sec / max_mib) * 30)
            bar = "█" * bar_width + "░" * (30 - bar_width)

            # Add row
            table.add_row(
                f"[{color}]{label}[/{color}]",
                f"[{color}]{bar}[/{color}]",
                f"{result.mib_per_sec:.2f}",
                cache_label
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
            text.append(f"  • Throughput: ", style="dim")
            text.append(f"{write_result.mib_per_sec:.2f} MiB/s ", style="green")
            text.append(f"({write_result.fps:.2f} fps)\n", style="dim")
            text.append(f"  • Avg latency: ", style="dim")
            text.append(f"{write_result.avg_ms:.1f} ms", style="yellow")
            text.append(f" (min: {write_result.min_ms:.1f}, max: {write_result.max_ms:.1f})\n", style="dim")
            text.append(f"  • Total time: ", style="dim")
            text.append(f"{write_result.time_ns / 1e9:.1f}s ", style="cyan")
            text.append(f"for {write_result.frames:,} frames\n\n", style="dim")

        # Read performance comparisons
        if read_results:
            text.append("Read Performance:\n", style="bold blue")
            if len(read_results) >= 2:
                # Cache speedup (read2 vs read1)
                cache_speedup = read_results[1].mib_per_sec / read_results[0].mib_per_sec
                text.append(f"  • Cache speedup (Read #2 / Read #1): ", style="dim")
                text.append(f"{cache_speedup:.2f}x\n", style="green bold")

                # Best read vs write
                if write_result:
                    best_read = max(read_results, key=lambda r: r.mib_per_sec)
                    read_write_ratio = best_read.mib_per_sec / write_result.mib_per_sec
                    text.append(f"  • Read/Write ratio (cached): ", style="dim")
                    text.append(f"{read_write_ratio:.2f}x\n", style="cyan bold")

                # Latency improvement
                latency_improvement = (read_results[0].avg_ms - read_results[1].avg_ms) / read_results[0].avg_ms * 100
                text.append(f"  • Latency improvement: ", style="dim")
                text.append(f"{latency_improvement:.1f}%\n", style="yellow bold")

            # Show all read results
            for i, read_result in enumerate(read_results, 1):
                if read_result.is_cached:
                    cache_type = "⚡ RAM CACHE"
                    cache_style = "yellow bold"
                else:
                    cache_type = "(cold)" if i == 1 else "(warm)" if i == 2 else f"(read {i})"
                    cache_style = "dim"
                text.append(f"  • Read #{i} {cache_type}: ", style=cache_style)
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
        """Create detailed statistics table"""
        table = Table(show_header=True, header_style="bold cyan", border_style="blue")
        table.add_column("Test", style="bold")
        table.add_column("Profile")
        table.add_column("Frames", justify="right")
        table.add_column("FPS", justify="right")
        table.add_column("MiB/s", justify="right")
        table.add_column("Time (s)", justify="right")

        for i, result in enumerate(results):
            # Determine label
            if result.operation == "write":
                label = "Write"
                style = "green"
            else:
                read_num = sum(1 for r in results[:i+1] if r.operation == "read")
                label = f"Read #{read_num}"
                style = "cyan" if read_num == 2 else "blue"

            table.add_row(
                f"[{style}]{label}[/{style}]",
                result.profile,
                f"{result.frames:,}",
                f"{result.fps:.2f}",
                f"{result.mib_per_sec:.2f}",
                f"{result.time_ns / 1e9:.2f}"
            )

        return Panel(table, title="[bold]Detailed Statistics[/bold]", border_style="blue")

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

        # Add RAM cache warning if detected
        cached_reads = [r for r in results if r.is_cached]
        if cached_reads:
            warning = Text()
            warning.append("⚡ RAM CACHE DETECTED\n\n", style="bold yellow")
            warning.append("Read speeds exceeding 10 GB/s indicate the data was served from RAM cache, ", style="yellow")
            warning.append("not from the actual disk/SSD. ", style="yellow")
            warning.append("This shows cache performance, not storage I/O performance.\n\n", style="yellow")
            warning.append("To measure actual disk performance:\n", style="dim")
            warning.append("  • Use a larger dataset that exceeds available RAM\n", style="dim")
            warning.append("  • Clear system cache before testing (macOS: ", style="dim")
            warning.append("sudo purge", style="cyan")
            warning.append(", Linux: ", style="dim")
            warning.append("sync; echo 3 | sudo tee /proc/sys/vm/drop_caches", style="cyan")
            warning.append(")\n", style="dim")
            warning.append("  • Test on a different system with less RAM\n", style="dim")
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
                    'range_ms'
                ])

                # Write results data
                for i, result in enumerate(results):
                    if result.operation == "write":
                        test_name = "Write"
                    else:
                        read_num = sum(1 for r in results[:i+1] if r.operation == "read")
                        test_name = f"Read_{read_num}"

                    range_ms = result.max_ms - result.min_ms

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
                        range_ms
                    ])

                # Write calculated insights if available
                write_result = next((r for r in results if r.operation == "write"), None)
                read_results = [r for r in results if r.operation == "read"]

                if write_result and len(read_results) >= 2:
                    writer.writerow([])
                    writer.writerow(['# Performance Insights'])
                    writer.writerow(['metric', 'value'])

                    cache_speedup = read_results[1].mib_per_sec / read_results[0].mib_per_sec
                    writer.writerow(['cache_speedup_ratio', f"{cache_speedup:.4f}"])

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

  # Parse existing tframetest output
  uv run tfbench.py --parse results.txt
        """
    )

    parser.add_argument("-w", "--write-size", default="4k",
                       help="Frame size for write test (e.g., 2k, 4k, 1m)")
    parser.add_argument("-n", "--frames", type=int, default=500,
                       help="Number of frames to test (default: 500)")
    parser.add_argument("-t", "--threads", type=int, default=0,
                       help="Number of threads (default: 8 for run mode, auto-detect for parse mode)")
    parser.add_argument("--reads", type=int, default=3,
                       help="Number of read tests to run (default: 3)")
    parser.add_argument("--timeout", type=int, default=1800,
                       help="Timeout per test in seconds (default: 1800 = 30 minutes)")
    parser.add_argument("--csv", metavar="FILE",
                       help="Export results to CSV file")
    parser.add_argument("--parse", metavar="FILE",
                       help="Parse and visualize existing tframetest output file")
    parser.add_argument("target_dir", nargs="?",
                       help="Target directory for benchmark tests")

    args = parser.parse_args()

    console = Console()

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
        visualizer = BenchmarkVisualizer(console)
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

    # Run benchmark suite
    runner = BenchmarkRunner(console)
    try:
        results = runner.run_benchmark_suite(
            args.write_size,
            args.frames,
            threads,
            args.target_dir,
            args.reads,
            args.timeout
        )
    except KeyboardInterrupt:
        console.print("\n[bold yellow]Benchmark interrupted by user. Exiting cleanly.[/bold yellow]")
        return 130  # Standard exit code for SIGINT

    if not results:
        console.print("[bold red]No benchmark results obtained[/bold red]")
        return 1

    # Display visualization
    visualizer = BenchmarkVisualizer(console)
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
