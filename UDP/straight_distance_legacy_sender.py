#!/usr/bin/env python3
"""Send straight-line legacy UDP commands until a target distance is reached.

This script does not output PWM directly. It sends the same little-endian
float64 x3 packet used by legacy_double3_rc_pwm_receiver.py:

    [raw_motor_1, raw_motor_2, raw_steer]

Use --use-encoder only on the Raspberry Pi after confirming the encoder wiring,
GPIO numbers, 3.3 V logic compatibility, common ground, and vehicle safety setup.
"""

import argparse
import csv
import socket
import struct
import sys
import time
from pathlib import Path


FMT = "<ddd"
DEFAULT_PORT = 5005
DEFAULT_RATE_HZ = 20.0

# These defaults match the successful straight-line UDP receiver condition:
# receiver: --speed-per-legacy-unit 0.0090 --max-speed-mps 0.38
#           --legacy-steer-b 70.9136 --esc-neutral-duty 10.3
DEFAULT_RAW_MOTOR = 39.5
DEFAULT_RAW_STEER = 85.997574582
DEFAULT_TARGET_DISTANCE_M = 0.30
DEFAULT_MAX_RUN_S = 2.0

DEFAULT_ENCODER_A_GPIO = 22
DEFAULT_ENCODER_B_GPIO = 27
DEFAULT_ENCODER_TEETH = 36
DEFAULT_WHEEL_DIAMETER_M = 0.066

NEUTRAL_PACKET = (0.0, 0.0, 90.0)


class Sender:
    def __init__(self, host, port):
        self.address = (host, port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send(self, raw_1, raw_2, raw_3):
        self.sock.sendto(struct.pack(FMT, raw_1, raw_2, raw_3), self.address)

    def close(self):
        self.sock.close()


def load_odometer(args):
    ellipse_dir = Path(__file__).resolve().parents[1] / "scripts" / "ellipse_run"
    sys.path.insert(0, str(ellipse_dir))

    if args.use_encoder:
        from odometer import Odometer

        return Odometer(
            a_pin=args.encoder_a_gpio,
            b_pin=args.encoder_b_gpio,
            n_teeth=args.encoder_teeth,
            wheel_diameter=args.wheel_diameter_m,
        )

    from odometer import SimOdometer

    return SimOdometer()


def write_row(writer, elapsed, distance_m, traveled_m, target_m, raw_1, raw_2, raw_3, status):
    writer.writerow(
        {
            "elapsed_s": f"{elapsed:.6f}",
            "distance_m": f"{distance_m:.9f}",
            "traveled_m": f"{traveled_m:.9f}",
            "target_distance_m": f"{target_m:.9f}",
            "raw1": f"{raw_1:.9f}",
            "raw2": f"{raw_2:.9f}",
            "raw3": f"{raw_3:.9f}",
            "status": status,
        }
    )


def send_neutral(sender, repeats, interval_s):
    for _ in range(repeats):
        sender.send(*NEUTRAL_PACKET)
        time.sleep(interval_s)


def run(args):
    if args.target_distance_m <= 0.0:
        raise ValueError("--target-distance-m must be positive")
    if args.rate_hz <= 0.0:
        raise ValueError("--rate-hz must be positive")
    if args.max_run_s <= 0.0:
        raise ValueError("--max-run-s must be positive")

    odo = load_odometer(args)
    sender = Sender(args.host, args.port)

    dt_target = 1.0 / args.rate_hz
    raw_1 = args.raw_motor
    raw_2 = args.raw_motor
    raw_3 = args.raw_steer

    stop_reason = "unknown"
    rows = 0

    log_path = Path(args.log_csv)
    fieldnames = [
        "elapsed_s",
        "distance_m",
        "traveled_m",
        "target_distance_m",
        "raw1",
        "raw2",
        "raw3",
        "status",
    ]

    print(
        "straight distance sender: "
        f"target={args.target_distance_m:.3f} m, "
        f"raw=({raw_1:.6f}, {raw_2:.6f}, {raw_3:.6f}), "
        f"rate={args.rate_hz:.1f} Hz, max={args.max_run_s:.2f} s"
    )
    print(f"udp destination: {args.host}:{args.port}")
    if args.use_encoder:
        print(
            "encoder: "
            f"A=BCM{args.encoder_a_gpio}, B=BCM{args.encoder_b_gpio}, "
            f"teeth={args.encoder_teeth}, wheel_diameter={args.wheel_diameter_m:.3f} m"
        )
    else:
        print(f"simulation odometer: sim_speed={args.sim_speed_mps:.3f} m/s")

    with log_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        odo.start()
        t_start = time.monotonic()
        t_prev = t_start

        try:
            while True:
                now = time.monotonic()
                dt = now - t_prev
                if dt < dt_target:
                    time.sleep(dt_target - dt)
                    now = time.monotonic()
                    dt = now - t_prev
                t_prev = now

                if not args.use_encoder:
                    odo.advance(abs(args.sim_speed_mps) * dt)

                elapsed = now - t_start
                distance_m = odo.distance
                traveled_m = abs(distance_m)

                if traveled_m >= args.target_distance_m:
                    stop_reason = "target_distance_reached"
                    break
                if elapsed >= args.max_run_s:
                    stop_reason = "time_limit_reached"
                    break

                sender.send(raw_1, raw_2, raw_3)
                write_row(
                    writer,
                    elapsed,
                    distance_m,
                    traveled_m,
                    args.target_distance_m,
                    raw_1,
                    raw_2,
                    raw_3,
                    "run",
                )
                rows += 1

        except KeyboardInterrupt:
            stop_reason = "interrupted"
            print("\ninterrupted")
        finally:
            if not args.no_neutral_on_exit:
                send_neutral(sender, args.neutral_repeats, args.neutral_interval_s)
                elapsed = time.monotonic() - t_start
                write_row(
                    writer,
                    elapsed,
                    odo.distance,
                    abs(odo.distance),
                    args.target_distance_m,
                    *NEUTRAL_PACKET,
                    "neutral_exit",
                )
                rows += 1

            odo.stop()
            sender.close()

    print(
        f"done: reason={stop_reason}, traveled={abs(odo.distance):.3f} m, "
        f"signed_distance={odo.distance:.3f} m, rows={rows}, log={log_path}"
    )


def parse_args():
    parser = argparse.ArgumentParser(
        description="Send legacy UDP straight commands until encoder distance reaches a target."
    )
    parser.add_argument("--host", default="127.0.0.1", help="UDP receiver host")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="UDP receiver port")
    parser.add_argument(
        "--target-distance-m",
        type=float,
        default=DEFAULT_TARGET_DISTANCE_M,
        help="Stop target distance in meters",
    )
    parser.add_argument(
        "--raw-motor",
        type=float,
        default=DEFAULT_RAW_MOTOR,
        help="Legacy raw motor value for raw1/raw2",
    )
    parser.add_argument(
        "--raw-steer",
        type=float,
        default=DEFAULT_RAW_STEER,
        help="Legacy raw steering value for raw3",
    )
    parser.add_argument("--rate-hz", type=float, default=DEFAULT_RATE_HZ)
    parser.add_argument("--max-run-s", type=float, default=DEFAULT_MAX_RUN_S)
    parser.add_argument("--log-csv", default="straight_distance_legacy_sender_log.csv")
    parser.add_argument(
        "--use-encoder",
        action="store_true",
        help="Use Raspberry Pi encoder GPIO instead of simulated odometer",
    )
    parser.add_argument("--encoder-a-gpio", type=int, default=DEFAULT_ENCODER_A_GPIO)
    parser.add_argument("--encoder-b-gpio", type=int, default=DEFAULT_ENCODER_B_GPIO)
    parser.add_argument("--encoder-teeth", type=int, default=DEFAULT_ENCODER_TEETH)
    parser.add_argument("--wheel-diameter-m", type=float, default=DEFAULT_WHEEL_DIAMETER_M)
    parser.add_argument(
        "--sim-speed-mps",
        type=float,
        default=0.30,
        help="Simulated distance rate when --use-encoder is not set",
    )
    parser.add_argument(
        "--no-neutral-on-exit",
        action="store_true",
        help="Do not send Param_init neutral packets on exit",
    )
    parser.add_argument("--neutral-repeats", type=int, default=5)
    parser.add_argument("--neutral-interval-s", type=float, default=0.05)
    return parser.parse_args()


def main():
    run(parse_args())


if __name__ == "__main__":
    main()
