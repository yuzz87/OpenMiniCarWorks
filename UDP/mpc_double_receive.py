#!/usr/bin/env python3
"""Receive Simulink/MPC double commands over UDP and print them.

This is a communication check only. It does not access GPIO, pigpio, ESC, or
steering PWM.

Packet format:
- little-endian float64 x 2
- [target_speed_mps, target_steer_rad]

Units:
- target_speed_mps: m/s
- target_steer_rad: rad
"""

import argparse
import math
import socket
import struct


DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 5005
FMT = "<dd"
NBYTES = struct.calcsize(FMT)
MAX_PACKET_BYTES = 1024

DEFAULT_MAX_SPEED_MPS = 0.30
DEFAULT_MAX_STEER_RAD = math.radians(18.0)


def decode_packet(data):
    """Decode one UDP packet as [target_speed_mps, target_steer_rad]."""
    if len(data) != NBYTES:
        return None
    return struct.unpack(FMT, data)


def make_parser():
    parser = argparse.ArgumentParser(
        description="Receive double x2 UDP commands: speed [m/s], steer [rad]."
    )
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--max-speed-mps", type=float, default=DEFAULT_MAX_SPEED_MPS)
    parser.add_argument("--max-steer-rad", type=float, default=DEFAULT_MAX_STEER_RAD)
    return parser


def make_status(target_speed_mps, target_steer_rad, args):
    status = []
    if target_speed_mps < 0.0:
        status.append("negative_speed")
    elif target_speed_mps > args.max_speed_mps:
        status.append("speed_over_initial_limit")

    if abs(target_steer_rad) > args.max_steer_rad:
        status.append("steer_over_initial_limit")

    if not status:
        status.append("ok")
    return ",".join(status)


def main():
    args = make_parser().parse_args()
    bind_address = (args.host, args.port)

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(bind_address)
        print(f"waiting UDP on {bind_address}...")
        print(f"accepting {NBYTES} byte float64x2 packets")
        print(
            "expected: target_speed_mps[m/s], target_steer_rad[rad]; "
            "GPIO/PWM output is disabled"
        )

        while True:
            data, addr = sock.recvfrom(MAX_PACKET_BYTES)
            values = decode_packet(data)
            if values is None:
                print(f"skip {addr}: unexpected packet size {len(data)} bytes")
                continue

            target_speed_mps, target_steer_rad = values
            status = make_status(target_speed_mps, target_steer_rad, args)
            print(
                "{} target_speed_mps={:.9f} m/s "
                "target_steer_rad={:.9f} rad target_steer_deg={:.4f} deg "
                "status={}".format(
                    addr,
                    target_speed_mps,
                    target_steer_rad,
                    math.degrees(target_steer_rad),
                    status,
                )
            )


if __name__ == "__main__":
    main()
