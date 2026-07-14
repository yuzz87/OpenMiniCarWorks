#!/usr/bin/env python3
"""Save RPLidar A1M8 scans to CSV and optionally plot them.

Distances are stored in meters [m].
Angles from the rplidar package are assumed to be degrees [deg] and are stored
as radians [rad] in the CSV.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


DEFAULT_DEVICE = "/dev/ttyUSB0"
DEFAULT_MAX_SCANS = 10
DEFAULT_MIN_RANGE_M = 0.05
DEFAULT_MAX_RANGE_M = 12.0
DEFAULT_CSV_PATH = "lidar_scan.csv"
DEFAULT_PNG_PATH = "lidar_scan.png"

CSV_HEADER = [
    "scan_index",
    "sample_index",
    "timestamp_s",
    "quality",
    "angle_rad",
    "range_m",
    "x_m",
    "y_m",
]


@dataclass(frozen=True)
class ScanPoint:
    scan_index: int
    sample_index: int
    timestamp_s: float
    quality: int
    angle_rad: float
    range_m: float
    x_m: float
    y_m: float


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be greater than 0")
    return parsed


def positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0.0:
        raise argparse.ArgumentTypeError("value must be greater than 0")
    return parsed


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Save RPLidar scans to CSV in SI units and create an XY plot. "
            "Input angles from rplidar are degrees; CSV angles are radians."
        )
    )
    parser.add_argument("--device", default=DEFAULT_DEVICE, help="serial device path")
    parser.add_argument(
        "--max-scans",
        type=positive_int,
        default=DEFAULT_MAX_SCANS,
        help="number of scans to collect",
    )
    parser.add_argument(
        "--min-range-m",
        type=positive_float,
        default=DEFAULT_MIN_RANGE_M,
        help="minimum range to save [m]",
    )
    parser.add_argument(
        "--max-range-m",
        type=positive_float,
        default=DEFAULT_MAX_RANGE_M,
        help="maximum range to save [m]",
    )
    parser.add_argument("--csv", default=DEFAULT_CSV_PATH, help="output CSV path")
    parser.add_argument("--png", default=DEFAULT_PNG_PATH, help="output PNG path")
    parser.add_argument(
        "--no-plot",
        action="store_true",
        help="skip PNG plotting even when matplotlib is installed",
    )
    args = parser.parse_args(argv)

    if args.min_range_m > args.max_range_m:
        parser.error("--min-range-m must be less than or equal to --max-range-m")

    return args


def resolve_output_path(path_text: str) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    return Path(__file__).resolve().parent / path


def angle_deg_to_rad(angle_deg: float) -> float:
    """Convert degrees [deg] to normalized radians [rad]."""

    return math.radians(angle_deg % 360.0)


def measurement_to_point(
    *,
    scan_index: int,
    sample_index: int,
    timestamp_s: float,
    measurement: Sequence[float],
    min_range_m: float,
    max_range_m: float,
) -> ScanPoint | None:
    quality_raw, angle_deg_raw, distance_mm_raw = measurement
    range_m = float(distance_mm_raw) / 1000.0

    if not math.isfinite(range_m):
        return None
    if range_m < min_range_m or range_m > max_range_m:
        return None

    angle_rad = angle_deg_to_rad(float(angle_deg_raw))
    x_m = range_m * math.cos(angle_rad)
    y_m = range_m * math.sin(angle_rad)

    return ScanPoint(
        scan_index=scan_index,
        sample_index=sample_index,
        timestamp_s=timestamp_s,
        quality=int(quality_raw),
        angle_rad=angle_rad,
        range_m=range_m,
        x_m=x_m,
        y_m=y_m,
    )


def collect_scan_rows(
    lidar: object,
    *,
    max_scans: int,
    min_range_m: float,
    max_range_m: float,
) -> list[ScanPoint]:
    rows: list[ScanPoint] = []

    for scan_index, scan in enumerate(lidar.iter_scans()):
        if scan_index >= max_scans:
            break

        timestamp_s = time.time()
        kept_count = 0
        for sample_index, measurement in enumerate(scan):
            point = measurement_to_point(
                scan_index=scan_index,
                sample_index=sample_index,
                timestamp_s=timestamp_s,
                measurement=measurement,
                min_range_m=min_range_m,
                max_range_m=max_range_m,
            )
            if point is None:
                continue
            rows.append(point)
            kept_count += 1

        print(
            f"scan {scan_index}: got {len(scan)} measurements, "
            f"kept {kept_count}"
        )

    return rows


def write_csv(csv_path: Path, rows: Iterable[ScanPoint]) -> int:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0

    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(CSV_HEADER)
        for row in rows:
            writer.writerow(
                [
                    row.scan_index,
                    row.sample_index,
                    f"{row.timestamp_s:.6f}",
                    row.quality,
                    f"{row.angle_rad:.9f}",
                    f"{row.range_m:.6f}",
                    f"{row.x_m:.6f}",
                    f"{row.y_m:.6f}",
                ]
            )
            count += 1

    return count


def plot_rows(png_path: Path, rows: Sequence[ScanPoint], scan_count: int) -> bool:
    if not rows:
        print("No valid scan points; PNG plot was skipped.", file=sys.stderr)
        return False

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib is not installed; PNG plot was skipped.", file=sys.stderr)
        return False

    png_path.parent.mkdir(parents=True, exist_ok=True)

    x_values = [point.x_m for point in rows]
    y_values = [point.y_m for point in rows]
    range_values = [point.range_m for point in rows]

    fig, ax = plt.subplots(figsize=(8, 8))
    scatter = ax.scatter(
        x_values,
        y_values,
        s=3,
        c=range_values,
        cmap="viridis",
        linewidths=0,
    )
    fig.colorbar(scatter, ax=ax, label="range [m]")

    max_abs = max(
        max(abs(value) for value in x_values),
        max(abs(value) for value in y_values),
    )
    axis_limit = max(0.5, max_abs * 1.05)
    arrow_len = min(1.0, axis_limit * 0.35)
    ax.arrow(
        0.0,
        0.0,
        arrow_len,
        0.0,
        color="tab:red",
        width=axis_limit * 0.002,
        head_width=axis_limit * 0.035,
        length_includes_head=True,
    )
    ax.text(arrow_len, axis_limit * 0.025, "0 rad", color="tab:red")

    ax.set_title(f"RPLidar scan: {scan_count} scans, {len(rows)} points")
    ax.set_xlabel("x [m]")
    ax.set_ylabel("y [m]")
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlim(-axis_limit, axis_limit)
    ax.set_ylim(-axis_limit, axis_limit)
    ax.grid(True)

    fig.tight_layout()
    fig.savefig(png_path, dpi=150)
    plt.close(fig)
    return True


def create_lidar(device: str) -> object:
    try:
        from rplidar import RPLidar
    except ImportError as exc:
        raise RuntimeError(
            "The rplidar package is not installed. "
            "Install rplidar-roboticia or run this script in the LiDAR environment."
        ) from exc

    return RPLidar(device)


def cleanup_lidar(lidar: object | None) -> None:
    if lidar is None:
        return

    for method_name in ("stop", "stop_motor", "disconnect"):
        method = getattr(lidar, method_name, None)
        if method is None:
            continue
        try:
            method()
        except Exception as exc:  # pragma: no cover - depends on serial device state.
            print(f"warning: lidar.{method_name}() failed: {exc}", file=sys.stderr)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    csv_path = resolve_output_path(args.csv)
    png_path = resolve_output_path(args.png)
    lidar = None
    rows: list[ScanPoint] = []

    try:
        lidar = create_lidar(args.device)

        print("Getting RPLidar info...")
        print(lidar.get_info())
        print("Getting RPLidar health...")
        print(lidar.get_health())

        rows = collect_scan_rows(
            lidar,
            max_scans=args.max_scans,
            min_range_m=args.min_range_m,
            max_range_m=args.max_range_m,
        )
    except KeyboardInterrupt:
        print("Interrupted by user; saving collected rows.", file=sys.stderr)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"error: LiDAR scan failed: {exc}", file=sys.stderr)
        return 1
    finally:
        cleanup_lidar(lidar)

    saved_count = write_csv(csv_path, rows)
    print(f"Saved {saved_count} points to {csv_path}")

    if args.no_plot:
        print("PNG plot skipped by --no-plot")
    elif plot_rows(png_path, rows, args.max_scans):
        print(f"Saved plot to {png_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
