#!/usr/bin/env python3
"""JSON UDP制御指令を1回送信するテストプログラム。

このテストはGPIO、pigpio、ESC、ステアリングPWMにはアクセスしない。
送信するだけなので、実車は動かない。

単位:
- target_steer_rad: 目標ステア角[rad]
- target_speed_mps: 目標速度[m/s]
- timestamp: UNIX時刻[s]
"""

import argparse
import math
import socket

from json_protocol import encode_control_message, make_control_message


# PC -> Raspberry Pi確認で使う標準UDPポート。
DEFAULT_PORT = 5005


def finite_float_arg(field_name):
    """argparse用に、有限のfloatだけを受け付ける変換関数を作る。"""

    def convert(value):
        # コマンドライン引数は文字列で入るので、まずfloatへ変換する。
        try:
            result = float(value)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f"{field_name} must be a number") from exc
        # nanやinfは制御指令として危険なので受け付けない。
        if not math.isfinite(result):
            raise argparse.ArgumentTypeError(f"{field_name} must be finite")
        return result

    return convert


def make_parser():
    """コマンドライン引数の仕様を定義する。"""
    parser = argparse.ArgumentParser(
        description="Send one JSON UDP control message for communication testing."
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
        "--timestamp",
        type=finite_float_arg("timestamp"),
        default=None,
        help="Timestamp [s]. Default: current UNIX time.",
    )
    return parser


def main():
    """コマンドライン引数からJSONを作り、指定IPアドレスとUDPポートへ送る。"""
    args = make_parser().parse_args()

    # JSONとして送る制御指令を作る。timestamp省略時は現在時刻[s]になる。
    message = make_control_message(
        args.target_steer_rad,
        args.target_speed_mps,
        args.timestamp,
    )

    # Pythonのdictを、UDPで送れるbytesへ変換する。
    payload = encode_control_message(message)

    # UDPはコネクションを張らず、sendtoで宛先を指定して1パケット送る。
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sent_bytes = sock.sendto(payload, (args.host, args.port))

    # 送った内容を人間が確認できるように表示する。
    print(f"sent {sent_bytes} bytes to {(args.host, args.port)}")
    print(payload.decode("utf-8"))


if __name__ == "__main__":
    main()
