#!/usr/bin/env python3
"""JSON UDP制御指令を一定周期で送信するテストプログラム。

PC側からRaspberry Pi側のUDP PWM受信プログラムへ、同じ目標ステア角[rad]と
目標速度[m/s]を送り続けるために使う。GPIO、pigpio、PWMにはアクセスしない。
"""

import argparse
import math
import socket
import time

from json_protocol import encode_control_message, make_control_message


DEFAULT_PORT = 5005
DEFAULT_RATE_HZ = 20.0
DEFAULT_DURATION_SECONDS = 5.0
NEUTRAL_REPEAT_COUNT = 3


def finite_float_arg(field_name):
    """argparse用に、有限のfloatだけを受け付ける変換関数を作る。"""

    def convert(value):
        try:
            result = float(value)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f"{field_name} must be a number") from exc
        if not math.isfinite(result):
            raise argparse.ArgumentTypeError(f"{field_name} must be finite")
        return result

    return convert


def positive_float_arg(field_name):
    """argparse用に、0より大きい有限のfloatだけを受け付ける変換関数を作る。"""
    convert_finite = finite_float_arg(field_name)

    def convert(value):
        result = convert_finite(value)
        if result <= 0.0:
            raise argparse.ArgumentTypeError(f"{field_name} must be positive")
        return result

    return convert


def make_parser():
    """コマンドライン引数の仕様を定義する。"""
    parser = argparse.ArgumentParser(
        description="Send JSON UDP control messages periodically."
    )
    parser.add_argument(
        "host",
        help="Destination IP address, for example 192.168.11.4 for Raspberry Pi.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"Destination UDP port. Default: {DEFAULT_PORT}",
    )
    parser.add_argument(
        "--target-steer-rad",
        type=finite_float_arg("target_steer_rad"),
        default=0.0,
        help="Target steering angle [rad]. Default: 0.0",
    )
    parser.add_argument(
        "--target-speed-mps",
        type=finite_float_arg("target_speed_mps"),
        default=0.0,
        help="Target speed [m/s]. Default: 0.0",
    )
    parser.add_argument(
        "--rate-hz",
        type=positive_float_arg("rate_hz"),
        default=DEFAULT_RATE_HZ,
        help=f"Send rate [Hz]. Default: {DEFAULT_RATE_HZ}",
    )
    parser.add_argument(
        "--duration",
        type=positive_float_arg("duration"),
        default=DEFAULT_DURATION_SECONDS,
        help=f"Send duration [s]. Default: {DEFAULT_DURATION_SECONDS}",
    )
    parser.add_argument(
        "--send-neutral-on-exit",
        action="store_true",
        help="Send neutral commands before exit.",
    )
    return parser


def send_message(sock, address, target_steer_rad, target_speed_mps):
    """現在時刻を入れたJSON制御指令を1回送信する。"""
    message = make_control_message(target_steer_rad, target_speed_mps)
    payload = encode_control_message(message)
    sock.sendto(payload, address)
    return payload


def main():
    """指定周期でUDP JSONを送信する。"""
    args = make_parser().parse_args()
    address = (args.host, args.port)
    period_seconds = 1.0 / args.rate_hz
    end_time = time.monotonic() + args.duration
    sent_count = 0
    last_payload = None

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            next_send_time = time.monotonic()
            while time.monotonic() < end_time:
                now = time.monotonic()
                if now < next_send_time:
                    time.sleep(next_send_time - now)

                last_payload = send_message(
                    sock,
                    address,
                    args.target_steer_rad,
                    args.target_speed_mps,
                )
                sent_count += 1
                next_send_time += period_seconds
        finally:
            if args.send_neutral_on_exit:
                for _ in range(NEUTRAL_REPEAT_COUNT):
                    last_payload = send_message(sock, address, 0.0, 0.0)
                    sent_count += 1
                    time.sleep(period_seconds)

    print(f"sent {sent_count} packets to {address}")
    if last_payload is not None:
        print(last_payload.decode("utf-8"))


if __name__ == "__main__":
    main()
