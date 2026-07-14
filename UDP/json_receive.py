#!/usr/bin/env python3
"""JSON UDP制御指令を受信するテストプログラム。

このテストはJSONを受信して検査・表示するだけである。
GPIO、pigpio、ESC、ステアリングPWMにはアクセスしない。

単位:
- target_steer_rad: 目標ステア角[rad]
- target_speed_mps: 目標速度[m/s]
- timestamp: UNIX時刻[s]
"""

import argparse
import json
import socket

from json_protocol import MAX_PACKET_BYTES, decode_control_packet

# 0.0.0.0で待ち受けると、Raspberry PiやPCの全ネットワークIFで受信できる。
DEFAULT_HOST = "0.0.0.0"

# PC -> Raspberry Pi確認で使う標準UDPポート。
DEFAULT_PORT = 5005


def make_parser():
    """コマンドライン引数の仕様を定義する。"""
    parser = argparse.ArgumentParser(
        description="Receive JSON UDP control messages for communication testing."
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"Local bind address. Default: {DEFAULT_HOST}",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"Local UDP port. Default: {DEFAULT_PORT}",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Exit after receiving one valid or invalid packet.",
    )
    return parser


def print_control_message(sender, text, message):
    """検査済みの制御指令を表示する。"""
    print(f"received from {sender}: {text}")
    print(
        "target_steer_rad={:.9f}, target_speed_mps={:.9f}, timestamp={:.6f}".format(
            message["target_steer_rad"],
            message["target_speed_mps"],
            message["timestamp"],
        )
    )


def main():
    """指定したIPアドレスとUDPポートで待ち受け、受信JSONを検査して表示する。"""
    args = make_parser().parse_args()
    bind_address = (args.host, args.port)
    # SOCK_DGRAMはUDPソケットを表す。bindで受信待ちするアドレスを決める。
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(bind_address)
        print(f"listening on {bind_address}")

        while True:
            # recvfromは、受信データと送信元アドレスを返す。
            packet, sender = sock.recvfrom(MAX_PACKET_BYTES)
            try:
                # UTF-8 JSONとして読めるか、必須フィールドがあるかを確認する。
                text, message = decode_control_packet(packet)
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                # 壊れたJSONや仕様外メッセージは、PWM等へ使わずエラー表示だけにする。
                print(f"invalid packet from {sender}: {exc}")
                print(packet)
            else:
                print_control_message(sender, text, message)

            # --onceを付けた場合は1パケット処理したら終了する。動作確認に便利。
            if args.once:
                break


if __name__ == "__main__":
    main()
