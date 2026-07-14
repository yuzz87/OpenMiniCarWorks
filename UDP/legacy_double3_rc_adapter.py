#!/usr/bin/env python3
"""Dry-run adapter for the current Simulink double x3 UDP output.

This script does not access GPIO, pigpio, ESC, or steering PWM.

Current observed packet format:
- little-endian float64 x 3
- [legacy_motor_1, legacy_motor_2, legacy_servo_deg]

Dry-run interpretation:
- legacy_motor_1/2 are treated as a legacy motor command, not RC ESC duty.
- legacy_servo_deg is converted to an estimated RC steering angle using the
  legacy line shown in the Simulink diagram:
  steer_deg = legacy_steer_a * legacy_servo_deg + legacy_steer_b

Units:
- legacy_servo_deg: deg
- target_speed_mps: m/s
- target_steer_rad: rad
- PWM duty: percent
"""

import argparse
import math
import socket
import struct


DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 5005
FMT = "<ddd"
NBYTES = struct.calcsize(FMT)
MAX_PACKET_BYTES = 1024

# Current RC-car steering conversion:
# steer_angle_rad = DUTY_FIT_A * steering_duty_percent + DUTY_FIT_B
DUTY_FIT_A = -0.186785136654
DUTY_FIT_B = 2.018473280947

# Current RC-car ESC speed conversion:
# speed_mps = -SPEED_FIT_ALPHA * esc_duty_percent + SPEED_FIT_BETA
SPEED_FIT_ALPHA = 2.4618
SPEED_FIT_BETA = 25.347

STEERING_NEUTRAL_DUTY = 10.895
ESC_NEUTRAL_DUTY = 10.55
STEERING_SAFE_MIN = 7.50
STEERING_SAFE_MAX = 13.00
ESC_SAFE_MIN = 9.50
ESC_SAFE_MAX = 13.00

MAX_SPEED_MPS = 0.30
MAX_STEER_RAD = math.radians(18.0)
ZERO_SPEED_EPS_MPS = 1e-6

# From the Simulink diagram: y = -0.8246 x + 74.212
LEGACY_STEER_A = -0.8246
LEGACY_STEER_B = 74.212


def decode_packet(data):
    if len(data) != NBYTES:
        return None
    return struct.unpack(FMT, data)


def steering_rad_to_duty_percent(target_steer_rad):
    return (target_steer_rad - DUTY_FIT_B) / DUTY_FIT_A


def speed_mps_to_esc_duty_percent(target_speed_mps):
    if abs(target_speed_mps) <= ZERO_SPEED_EPS_MPS:
        return ESC_NEUTRAL_DUTY
    return (SPEED_FIT_BETA - target_speed_mps) / SPEED_FIT_ALPHA


def is_in_range(value, low, high):
    return low <= value <= high


def make_parser():
    parser = argparse.ArgumentParser(
        description="Dry-run adapter for legacy double x3 UDP packets."
    )
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--speed-per-legacy-unit",
        type=float,
        default=0.0,
        help=(
            "Temporary linear scale from legacy motor command to speed [m/s]. "
            "Default 0.0 keeps speed at neutral and reports scale_unset."
        ),
    )
    parser.add_argument(
        "--legacy-steer-a",
        type=float,
        default=LEGACY_STEER_A,
        help="Legacy servo deg to actual steer deg slope.",
    )
    parser.add_argument(
        "--legacy-steer-b",
        type=float,
        default=LEGACY_STEER_B,
        help="Legacy servo deg to actual steer deg intercept.",
    )
    parser.add_argument("--max-speed-mps", type=float, default=MAX_SPEED_MPS)
    parser.add_argument("--max-steer-rad", type=float, default=MAX_STEER_RAD)
    parser.add_argument("--motor-mismatch-tol", type=float, default=1e-6)
    return parser


def make_status(raw_1, raw_2, raw_3, target_speed_mps, target_steer_rad, args):
    status = []
    values = (raw_1, raw_2, raw_3, target_speed_mps, target_steer_rad)
    if not all(math.isfinite(value) for value in values):
        status.append("nonfinite")

    if abs(raw_1 - raw_2) > args.motor_mismatch_tol:
        status.append("legacy_motor_mismatch")

    if args.speed_per_legacy_unit == 0.0:
        status.append("speed_scale_unset")

    if target_speed_mps < -ZERO_SPEED_EPS_MPS:
        status.append("negative_speed")
    elif target_speed_mps > args.max_speed_mps:
        status.append("speed_over_initial_limit")

    if abs(target_steer_rad) > args.max_steer_rad:
        status.append("steer_over_initial_limit")

    steering_duty = steering_rad_to_duty_percent(target_steer_rad)
    esc_duty = speed_mps_to_esc_duty_percent(target_speed_mps)
    if not is_in_range(steering_duty, STEERING_SAFE_MIN, STEERING_SAFE_MAX):
        status.append("steering_duty_out_of_range")
    if not is_in_range(esc_duty, ESC_SAFE_MIN, ESC_SAFE_MAX):
        status.append("esc_duty_out_of_range")

    if not status:
        status.append("ok")
    return ",".join(status)


def convert_packet(raw_1, raw_2, raw_3, args):
    legacy_motor_avg = 0.5 * (raw_1 + raw_2)
    target_speed_mps = legacy_motor_avg * args.speed_per_legacy_unit

    target_steer_deg = args.legacy_steer_a * raw_3 + args.legacy_steer_b
    target_steer_rad = math.radians(target_steer_deg)

    steering_duty = steering_rad_to_duty_percent(target_steer_rad)
    esc_duty = speed_mps_to_esc_duty_percent(target_speed_mps)
    return (
        legacy_motor_avg,
        target_speed_mps,
        target_steer_deg,
        target_steer_rad,
        steering_duty,
        esc_duty,
    )


def main():
    args = make_parser().parse_args()
    bind_address = (args.host, args.port)

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(bind_address)
        print(f"waiting UDP on {bind_address}...")
        print(f"accepting {NBYTES} byte float64x3 legacy packets")
        print("dry-run only: GPIO/PWM output is disabled")
        print(
            "assumed packet: legacy_motor_1, legacy_motor_2, legacy_servo_deg"
        )

        while True:
            data, addr = sock.recvfrom(MAX_PACKET_BYTES)
            values = decode_packet(data)
            if values is None:
                print(f"skip {addr}: unexpected packet size {len(data)} bytes")
                continue

            raw_1, raw_2, raw_3 = values
            (
                legacy_motor_avg,
                target_speed_mps,
                target_steer_deg,
                target_steer_rad,
                steering_duty,
                esc_duty,
            ) = convert_packet(raw_1, raw_2, raw_3, args)
            status = make_status(
                raw_1,
                raw_2,
                raw_3,
                target_speed_mps,
                target_steer_rad,
                args,
            )

            print(
                "{} raw=({:.9f}, {:.9f}, {:.9f}) "
                "legacy_motor_avg={:.9f} target_speed_mps={:.9f} m/s "
                "target_steer_deg={:.4f} deg target_steer_rad={:.9f} rad "
                "steering_duty={:.6f} % esc_duty={:.6f} % status={}".format(
                    addr,
                    raw_1,
                    raw_2,
                    raw_3,
                    legacy_motor_avg,
                    target_speed_mps,
                    target_steer_deg,
                    target_steer_rad,
                    steering_duty,
                    esc_duty,
                    status,
                )
            )


if __name__ == "__main__":
    main()
