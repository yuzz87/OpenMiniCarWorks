#!/usr/bin/env python3
"""Compare an actual vehicle position log with a reference trajectory.

Inputs are CSV files. Coordinates are SI units: x/y in meters and heading in
radians unless --actual-heading-unit deg is specified.
"""

import argparse
import csv
import json
import math
from pathlib import Path


TIME_ALIASES = ("t", "time", "time_s", "timestamp", "timestamp_s")
X_ALIASES = ("x", "x_m", "x_ref", "ref_x", "actual_x", "x_est", "pose_x")
Y_ALIASES = ("y", "y_m", "y_ref", "ref_y", "actual_y", "y_est", "pose_y")
HEADING_ALIASES = (
    "theta",
    "theta_rad",
    "phi",
    "phi_rad",
    "yaw",
    "yaw_rad",
    "heading",
    "heading_rad",
)


def finite_float(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"non-finite value: {value!r}")
    return number


def normalize_angle_rad(angle):
    return math.atan2(math.sin(angle), math.cos(angle))


def path_length(points):
    total = 0.0
    for i in range(1, len(points)):
        total += math.hypot(points[i][0] - points[i - 1][0], points[i][1] - points[i - 1][1])
    return total


def pick_column(fieldnames, requested, aliases, label, required=True):
    if requested and requested.lower() != "none":
        if requested not in fieldnames:
            raise SystemExit(f"{label} column {requested!r} not found in CSV header")
        return requested

    lower_to_name = {name.lower(): name for name in fieldnames}
    for alias in aliases:
        if alias.lower() in lower_to_name:
            return lower_to_name[alias.lower()]

    if required:
        raise SystemExit(
            f"could not infer {label} column; available columns: {', '.join(fieldnames)}"
        )
    return None


def read_csv_points(path, x_col, y_col, time_col=None, heading_col=None, heading_unit="rad"):
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise SystemExit(f"{path} has no CSV header")

        x_name = pick_column(reader.fieldnames, x_col, X_ALIASES, "x")
        y_name = pick_column(reader.fieldnames, y_col, Y_ALIASES, "y")
        t_name = pick_column(reader.fieldnames, time_col, TIME_ALIASES, "time", required=False)
        heading_name = pick_column(
            reader.fieldnames,
            heading_col,
            HEADING_ALIASES,
            "heading",
            required=False,
        )

        rows = []
        for row_index, row in enumerate(reader, start=2):
            try:
                x = finite_float(row[x_name])
                y = finite_float(row[y_name])
                t = finite_float(row[t_name]) if t_name else None
                heading = finite_float(row[heading_name]) if heading_name else None
                if heading is not None and heading_unit == "deg":
                    heading = math.radians(heading)
            except (KeyError, ValueError) as exc:
                raise SystemExit(f"{path}:{row_index}: invalid numeric value: {exc}") from exc
            rows.append({"t": t, "x": x, "y": y, "heading": heading})

    if not rows:
        raise SystemExit(f"{path} contains no data rows")
    return rows


def reference_heading(points, index):
    if len(points) < 2:
        return None
    if index <= 0:
        p0, p1 = points[0], points[1]
    elif index >= len(points) - 1:
        p0, p1 = points[-2], points[-1]
    else:
        p0, p1 = points[index - 1], points[index + 1]
    return math.atan2(p1[1] - p0[1], p1[0] - p0[0])


def nearest_reference(point, ref_points):
    best_index = 0
    best_d2 = math.inf
    px, py = point
    for index, (rx, ry) in enumerate(ref_points):
        d2 = (px - rx) ** 2 + (py - ry) ** 2
        if d2 < best_d2:
            best_d2 = d2
            best_index = index
    return best_index, math.sqrt(best_d2)


def percentile(values, ratio):
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * ratio))))
    return ordered[index]


def evaluate(reference_rows, actual_rows):
    ref_points = [(row["x"], row["y"]) for row in reference_rows]
    actual_points = [(row["x"], row["y"]) for row in actual_rows]
    aligned = []
    errors = []
    heading_errors = []

    for row in actual_rows:
        nearest_index, error = nearest_reference((row["x"], row["y"]), ref_points)
        ref_x, ref_y = ref_points[nearest_index]
        ref_heading = reference_heading(ref_points, nearest_index)
        heading_error = None
        if row["heading"] is not None and ref_heading is not None:
            heading_error = normalize_angle_rad(row["heading"] - ref_heading)
            heading_errors.append(heading_error)
        errors.append(error)
        aligned.append(
            {
                "t": row["t"],
                "x": row["x"],
                "y": row["y"],
                "heading_rad": row["heading"],
                "nearest_ref_index": nearest_index,
                "ref_x": ref_x,
                "ref_y": ref_y,
                "ref_heading_rad": ref_heading,
                "position_error_m": error,
                "heading_error_rad": heading_error,
            }
        )

    duration = None
    times = [row["t"] for row in actual_rows if row["t"] is not None]
    if len(times) >= 2:
        duration = max(times) - min(times)

    rms_error = math.sqrt(sum(error * error for error in errors) / len(errors))
    summary = {
        "reference_samples": len(reference_rows),
        "actual_samples": len(actual_rows),
        "duration_s": duration,
        "reference_path_length_m": path_length(ref_points),
        "actual_path_length_m": path_length(actual_points),
        "mean_position_error_m": sum(errors) / len(errors),
        "rms_position_error_m": rms_error,
        "p95_position_error_m": percentile(errors, 0.95),
        "max_position_error_m": max(errors),
        "final_position_error_m": errors[-1],
    }

    if heading_errors:
        abs_heading = [abs(value) for value in heading_errors]
        heading_rms = math.sqrt(sum(value * value for value in heading_errors) / len(heading_errors))
        summary.update(
            {
                "heading_samples": len(heading_errors),
                "mean_abs_heading_error_deg": math.degrees(sum(abs_heading) / len(abs_heading)),
                "rms_heading_error_deg": math.degrees(heading_rms),
                "max_abs_heading_error_deg": math.degrees(max(abs_heading)),
            }
        )

    return summary, aligned


def write_aligned_csv(path, aligned):
    fieldnames = [
        "t",
        "x",
        "y",
        "heading_rad",
        "nearest_ref_index",
        "ref_x",
        "ref_y",
        "ref_heading_rad",
        "position_error_m",
        "heading_error_rad",
    ]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(aligned)


def write_plot(path, reference_rows, actual_rows, aligned):
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise SystemExit("matplotlib is required for --plot") from exc

    ref_x = [row["x"] for row in reference_rows]
    ref_y = [row["y"] for row in reference_rows]
    actual_x = [row["x"] for row in actual_rows]
    actual_y = [row["y"] for row in actual_rows]
    errors = [row["position_error_m"] for row in aligned]
    times = [row["t"] for row in aligned]
    if not all(time is not None for time in times):
        times = list(range(len(aligned)))

    fig, axes = plt.subplots(1, 2, figsize=(11, 5))
    axes[0].plot(ref_x, ref_y, label="reference", linewidth=2)
    axes[0].plot(actual_x, actual_y, label="actual", linewidth=2)
    axes[0].set_aspect("equal", adjustable="box")
    axes[0].set_xlabel("x [m]")
    axes[0].set_ylabel("y [m]")
    axes[0].grid(True)
    axes[0].legend()

    axes[1].plot(times, errors)
    axes[1].set_xlabel("time [s]" if aligned[0]["t"] is not None else "sample")
    axes[1].set_ylabel("nearest-path error [m]")
    axes[1].grid(True)

    fig.tight_layout()
    fig.savefig(path, dpi=160)


def print_summary(summary):
    for key, value in summary.items():
        if value is None:
            print(f"{key}: none")
        elif isinstance(value, float):
            print(f"{key}: {value:.6f}")
        else:
            print(f"{key}: {value}")


def make_parser():
    parser = argparse.ArgumentParser(
        description="Evaluate actual x/y position log against a reference trajectory CSV."
    )
    parser.add_argument("--reference", required=True, help="Reference trajectory CSV")
    parser.add_argument("--actual", required=True, help="Actual vehicle pose CSV")
    parser.add_argument("--ref-x", default="", help="Reference x column [m]")
    parser.add_argument("--ref-y", default="", help="Reference y column [m]")
    parser.add_argument("--actual-x", default="", help="Actual x column [m]")
    parser.add_argument("--actual-y", default="", help="Actual y column [m]")
    parser.add_argument("--actual-time", default="", help="Actual time column [s]")
    parser.add_argument(
        "--actual-heading",
        default="",
        help="Actual heading column; use 'none' to disable [rad by default]",
    )
    parser.add_argument(
        "--actual-heading-unit",
        choices=("rad", "deg"),
        default="rad",
        help="Unit of actual heading column.",
    )
    parser.add_argument("--aligned-csv", help="Write per-sample nearest-reference errors")
    parser.add_argument("--summary-json", help="Write summary metrics as JSON")
    parser.add_argument("--plot", help="Write trajectory/error plot PNG")
    return parser


def main():
    args = make_parser().parse_args()
    reference_rows = read_csv_points(args.reference, args.ref_x, args.ref_y)
    actual_rows = read_csv_points(
        args.actual,
        args.actual_x,
        args.actual_y,
        time_col=args.actual_time,
        heading_col=args.actual_heading,
        heading_unit=args.actual_heading_unit,
    )
    summary, aligned = evaluate(reference_rows, actual_rows)
    print_summary(summary)

    if args.aligned_csv:
        write_aligned_csv(args.aligned_csv, aligned)
        print(f"aligned_csv: {args.aligned_csv}")

    if args.summary_json:
        Path(args.summary_json).write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"summary_json: {args.summary_json}")

    if args.plot:
        write_plot(args.plot, reference_rows, actual_rows, aligned)
        print(f"plot: {args.plot}")


if __name__ == "__main__":
    main()
