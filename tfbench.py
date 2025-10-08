#!/usr/bin/env python3
"""
tfbench - TUI visualizer for tframetest benchmark results

A tool to run and visualize tframetest benchmarks with rich TUI components.
"""

import argparse
import csv
import re
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


class BenchmarkRunner:
    """Execute tframetest and capture results"""

    def __init__(self, console: Console):
        self.console = console

    def run_test(self, write_size: str, num_frames: int, threads: int,
                 target_dir: str, is_read: bool = False, timeout: int = 1800) -> Optional[BenchmarkResult]:
        """Run a single tframetest command and return parsed results

        Args:
            timeout: Timeout in seconds (default 1800 = 30 minutes)
        """

        # Build command
        cmd = ["tframetest"]
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
                self.console.print(f"[green]✓[/green] {operation} test completed: {parsed.mib_per_sec:.2f} MiB/s")
                self.console.print(f"[dim]Completed {parsed.frames} frames in {parsed.time_ns / 1e9:.1f}s[/dim]")
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
            else:
                read_num = sum(1 for r in results[:i+1] if r.operation == "read")
                label = f"Read #{read_num}"
                color = colors[min(read_num, len(colors)-1)]

                # Add cache indicator
                if read_num == 1:
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
                cache_label if result.operation == "read" else ""
            )

        return Panel(table, title="[bold]Throughput Comparison (MiB/s)[/bold]", border_style="blue")

    def create_latency_chart(self, results: list[BenchmarkResult]) -> Panel:
        """Create latency comparison chart"""
        table = Table(show_header=True, header_style="bold magenta", border_style="blue")
        table.add_column("Test", style="bold", width=12)
        table.add_column("Min (ms)", justify="right", width=12)
        table.add_column("Avg (ms)", justify="right", width=12)
        table.add_column("Max (ms)", justify="right", width=12)
        table.add_column("Range (ms)", justify="right", width=12)

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

    def create_insights_panel(self, results: list[BenchmarkResult]) -> Panel:
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
                cache_type = "(cold)" if i == 1 else "(warm)" if i == 2 else f"(read {i})"
                text.append(f"  • Read #{i} {cache_type}: ", style="dim")
                text.append(f"{read_result.mib_per_sec:.2f} MiB/s, ", style="cyan")
                text.append(f"{read_result.avg_ms:.1f} ms avg\n", style="dim")

        # Test configuration
        if results:
            r = results[0]
            text.append(f"\n[dim]Configuration:[/dim]\n", style="dim")
            text.append(f"  Frames: {r.frames:,} | ", style="dim")
            text.append(f"Data: {r.bytes / (1024**3):.2f} GiB | ", style="dim")
            text.append(f"Threads: {len(read_results) + (1 if write_result else 0)}", style="dim")

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
            summary.append(f"{min(frame_counts):,}-{max(frame_counts):,} | ", style="yellow")
        else:
            summary.append(f"{results[0].frames:,} | ", style="magenta")
        summary.append(f"Threads: ", style="bold")
        summary.append(f"{threads}", style="green")
        self.console.print(Panel(summary, border_style="blue"))
        self.console.print()

        # Main visualizations
        self.console.print(self.create_throughput_chart(results))
        self.console.print()
        self.console.print(self.create_insights_panel(results))
        self.console.print()
        self.console.print(self.create_latency_chart(results))
        self.console.print()
        self.console.print(self.create_detailed_table(results))
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
    parser.add_argument("-t", "--threads", type=int, default=8,
                       help="Number of threads to use")
    parser.add_argument("--reads", type=int, default=2,
                       help="Number of read tests to run (default: 2)")
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
        console.print(f"[yellow]Parsing mode not yet implemented[/yellow]")
        console.print(f"TODO: Parse {args.parse}")
        return 1

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

    # Run benchmark suite
    runner = BenchmarkRunner(console)
    try:
        results = runner.run_benchmark_suite(
            args.write_size,
            args.frames,
            args.threads,
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
    visualizer.display_results(results, args.target_dir, args.write_size, args.threads)

    # Export to CSV if requested
    if args.csv:
        csv_path = args.csv
        console.print(f"\n[cyan]Exporting results to CSV:[/cyan] {csv_path}")
        if visualizer.export_csv(results, csv_path, args.target_dir, args.write_size, args.threads):
            console.print(f"[green]✓[/green] CSV exported successfully")
        else:
            console.print(f"[red]✗[/red] Failed to export CSV")
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
