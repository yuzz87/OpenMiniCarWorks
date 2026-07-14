#!/usr/bin/env python3
"""UDP JSON制御指令をRaspberry Pi上でPWMへ変換する受信プログラム。

デフォルトではドライランで、受信値と計算したPWM duty比[%]を表示するだけである。
実車へ出力する場合は、--enable-hardware と安全確認オプションを明示する。

単位:
- target_steer_rad: 目標ステア角[rad]
- target_speed_mps: 目標速度[m/s]
- timestamp: UNIX時刻[s]。ウォッチドッグは受信時刻で判定する。
"""

import argparse
import json
import math
import socket
import time
from dataclasses import dataclass

from json_protocol import MAX_PACKET_BYTES, decode_control_packet


DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 5005

# PWM出力設定。GPIO番号はBCM表記。
DEFAULT_PWM_HZ = 70
DEFAULT_ESC_GPIO = 12
DEFAULT_STEERING_GPIO = 13

# 現在の実車校正値。duty比の単位は[%]。
DEFAULT_STEERING_NEUTRAL_DUTY = 10.895
DEFAULT_ESC_NEUTRAL_DUTY = 10.55

# ステアリング変換式:
# steer_angle_rad = DUTY_FIT_A * steering_duty_percent + DUTY_FIT_B
DUTY_FIT_A = -0.186785136654
DUTY_FIT_B = 2.018473280947

# ESC速度変換式:
# speed_mps = -SPEED_FIT_ALPHA * esc_duty_percent + SPEED_FIT_BETA
SPEED_FIT_ALPHA = 2.4618
SPEED_FIT_BETA = 25.347

# 安全制限。ステア角は現在の確認済み範囲である±18 degを初期値にする。
DEFAULT_MAX_STEER_RAD = math.radians(18.0)
DEFAULT_MAX_SPEED_MPS = 0.30
DEFAULT_STEERING_SAFE_MIN = 7.50
DEFAULT_STEERING_SAFE_MAX = 13.00
DEFAULT_ESC_SAFE_MIN = 9.50
DEFAULT_ESC_SAFE_MAX = 13.00

DEFAULT_WATCHDOG_TIMEOUT_SECONDS = 0.30
DEFAULT_SOCKET_TIMEOUT_SECONDS = 0.02
NEUTRAL_SETTLE_SECONDS = 1.0
ZERO_SPEED_EPS_MPS = 1e-6


@dataclass
class PwmCommand:
    """1回分のPWM指令値。"""

    target_steer_rad: float
    target_speed_mps: float
    steering_duty_percent: float
    esc_duty_percent: float
    status: str


def clamp(value, low, high):
    """値をlowからhighの範囲に制限する。"""
    return max(low, min(high, value))


def duty_to_pigpio(duty_percent):
    """duty比[%]をpigpio.hardware_PWM用の0..1000000の整数値へ変換する。"""
    return int(round(duty_percent * 10000))


def is_in_range(value, low, high):
    """値がlowからhighの範囲内ならTrueを返す。"""
    return low <= value <= high


def steering_rad_to_duty_percent(target_steer_rad):
    """目標ステア角[rad]をステアリングduty比[%]へ変換する。"""
    return (target_steer_rad - DUTY_FIT_B) / DUTY_FIT_A


def speed_mps_to_esc_duty_percent(target_speed_mps, neutral_duty):
    """目標速度[m/s]をESC duty比[%]へ変換する。

    0 m/s付近は近似式で外挿せず、中立duty[%]をそのまま返す。
    現時点では前進方向のみを扱い、負の速度は別の安全処理で拒否する。
    """
    if abs(target_speed_mps) <= ZERO_SPEED_EPS_MPS:
        return neutral_duty
    return (SPEED_FIT_BETA - target_speed_mps) / SPEED_FIT_ALPHA


def make_pwm_command(message, args):
    """受信JSONメッセージを安全制限付きPWM指令へ変換する。"""
    status_parts = []
    target_steer_rad = message["target_steer_rad"]
    target_speed_mps = message["target_speed_mps"]

    if target_speed_mps < -ZERO_SPEED_EPS_MPS:
        raise ValueError("negative target_speed_mps is not allowed")

    limited_steer_rad = clamp(
        target_steer_rad,
        -args.max_steer_rad,
        args.max_steer_rad,
    )
    if limited_steer_rad != target_steer_rad:
        status_parts.append("clamped_steer")

    limited_speed_mps = clamp(target_speed_mps, 0.0, args.max_speed_mps)
    if limited_speed_mps != target_speed_mps:
        status_parts.append("clamped_speed")

    steering_duty = steering_rad_to_duty_percent(limited_steer_rad)
    esc_duty = speed_mps_to_esc_duty_percent(
        limited_speed_mps,
        args.esc_neutral_duty,
    )

    if not is_in_range(
        steering_duty,
        args.steering_safe_min,
        args.steering_safe_max,
    ):
        raise ValueError(f"steering duty out of range: {steering_duty:.6f} %")

    if not is_in_range(esc_duty, args.esc_safe_min, args.esc_safe_max):
        raise ValueError(f"ESC duty out of range: {esc_duty:.6f} %")

    if not status_parts:
        status_parts.append("ok")

    return PwmCommand(
        target_steer_rad=limited_steer_rad,
        target_speed_mps=limited_speed_mps,
        steering_duty_percent=steering_duty,
        esc_duty_percent=esc_duty,
        status=",".join(status_parts),
    )


def make_neutral_command(args, status):
    """中立PWM指令を作る。"""
    return PwmCommand(
        target_steer_rad=0.0,
        target_speed_mps=0.0,
        steering_duty_percent=args.steering_neutral_duty,
        esc_duty_percent=args.esc_neutral_duty,
        status=status,
    )


def print_command(prefix, sender, command):
    """受信元とPWM指令値を表示する。"""
    sender_text = "-" if sender is None else f"{sender[0]}:{sender[1]}"
    print(
        "{} sender={} target_steer_rad={:.6f} rad "
        "target_speed_mps={:.6f} m/s steering_duty={:.6f} % "
        "esc_duty={:.6f} % status={}".format(
            prefix,
            sender_text,
            command.target_steer_rad,
            command.target_speed_mps,
            command.steering_duty_percent,
            command.esc_duty_percent,
            command.status,
        )
    )


def set_pwm(pi, args, command):
    """ESCとステアリングへPWMを出力する。"""
    pi.hardware_PWM(
        args.esc_gpio,
        args.pwm_hz,
        duty_to_pigpio(command.esc_duty_percent),
    )
    pi.hardware_PWM(
        args.steering_gpio,
        args.pwm_hz,
        duty_to_pigpio(command.steering_duty_percent),
    )


def output_command(pi, args, command, sender=None):
    """ドライラン表示、または実車PWM出力を行う。"""
    prefix = "PWM" if args.enable_hardware else "DRY"
    print_command(prefix, sender, command)
    if args.enable_hardware:
        set_pwm(pi, args, command)


def setup_hardware(args):
    """実車PWM出力用にpigpioへ接続する。"""
    import pigpio

    pi = pigpio.pi()
    if not pi.connected:
        raise RuntimeError("pigpio daemon not running (start it: sudo pigpiod)")

    pi.set_mode(args.esc_gpio, pigpio.OUTPUT)
    pi.set_mode(args.steering_gpio, pigpio.OUTPUT)
    return pi


def validate_hardware_options(args, parser):
    """実車出力時に必要な安全確認オプションを検査する。"""
    if not args.enable_hardware:
        return
    if not args.confirm_wheels_lifted:
        parser.error("--enable-hardware requires --confirm-wheels-lifted")
    if not args.confirm_power_cutoff:
        parser.error("--enable-hardware requires --confirm-power-cutoff")


def make_parser():
    """コマンドライン引数の仕様を定義する。"""
    parser = argparse.ArgumentParser(
        description="Receive JSON UDP commands and convert them to PWM output."
    )
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--pwm-hz", type=int, default=DEFAULT_PWM_HZ)
    parser.add_argument("--esc-gpio", type=int, default=DEFAULT_ESC_GPIO)
    parser.add_argument("--steering-gpio", type=int, default=DEFAULT_STEERING_GPIO)
    parser.add_argument(
        "--steering-neutral-duty",
        type=float,
        default=DEFAULT_STEERING_NEUTRAL_DUTY,
    )
    parser.add_argument(
        "--esc-neutral-duty",
        type=float,
        default=DEFAULT_ESC_NEUTRAL_DUTY,
    )
    parser.add_argument(
        "--steering-safe-min",
        type=float,
        default=DEFAULT_STEERING_SAFE_MIN,
    )
    parser.add_argument(
        "--steering-safe-max",
        type=float,
        default=DEFAULT_STEERING_SAFE_MAX,
    )
    parser.add_argument("--esc-safe-min", type=float, default=DEFAULT_ESC_SAFE_MIN)
    parser.add_argument("--esc-safe-max", type=float, default=DEFAULT_ESC_SAFE_MAX)
    parser.add_argument("--max-steer-rad", type=float, default=DEFAULT_MAX_STEER_RAD)
    parser.add_argument("--max-speed-mps", type=float, default=DEFAULT_MAX_SPEED_MPS)
    parser.add_argument(
        "--watchdog-timeout",
        type=float,
        default=DEFAULT_WATCHDOG_TIMEOUT_SECONDS,
        help="Timeout [s] before neutral PWM is commanded.",
    )
    parser.add_argument(
        "--socket-timeout",
        type=float,
        default=DEFAULT_SOCKET_TIMEOUT_SECONDS,
        help="UDP receive polling timeout [s].",
    )
    parser.add_argument(
        "--enable-hardware",
        action="store_true",
        help="Actually output PWM using pigpio. Default is dry-run.",
    )
    parser.add_argument(
        "--confirm-wheels-lifted",
        action="store_true",
        help="Required with --enable-hardware.",
    )
    parser.add_argument(
        "--confirm-power-cutoff",
        action="store_true",
        help="Required with --enable-hardware.",
    )
    return parser


def run_receiver(args):
    """UDP受信ループを実行する。"""
    pi = None
    last_packet_time = None
    watchdog_is_neutral = False
    neutral_command = make_neutral_command(args, "neutral")

    if args.enable_hardware:
        pi = setup_hardware(args)

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((args.host, args.port))
        sock.settimeout(args.socket_timeout)
        print(f"listening on {(args.host, args.port)}")
        print(
            "mode={}, pwm_hz={}, esc_gpio={}, steering_gpio={}, "
            "watchdog_timeout={:.3f} s, max_speed_mps={:.3f}".format(
                "hardware" if args.enable_hardware else "dry-run",
                args.pwm_hz,
                args.esc_gpio,
                args.steering_gpio,
                args.watchdog_timeout,
                args.max_speed_mps,
            )
        )

        try:
            output_command(pi, args, neutral_command, None)
            if args.enable_hardware:
                time.sleep(NEUTRAL_SETTLE_SECONDS)

            while True:
                try:
                    packet, sender = sock.recvfrom(MAX_PACKET_BYTES)
                except socket.timeout:
                    now = time.monotonic()
                    if (
                        last_packet_time is not None
                        and now - last_packet_time >= args.watchdog_timeout
                        and not watchdog_is_neutral
                    ):
                        command = make_neutral_command(args, "watchdog_neutral")
                        output_command(pi, args, command, None)
                        watchdog_is_neutral = True
                    continue

                last_packet_time = time.monotonic()
                watchdog_is_neutral = False

                try:
                    _, message = decode_control_packet(packet)
                    command = make_pwm_command(message, args)
                except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                    print(f"invalid packet from {sender}: {exc}")
                    command = make_neutral_command(args, "invalid_neutral")

                output_command(pi, args, command, sender)
        except KeyboardInterrupt:
            print("stopped by Ctrl-C")
        finally:
            print("neutral before shutdown")
            try:
                output_command(pi, args, neutral_command, None)
                if args.enable_hardware:
                    time.sleep(NEUTRAL_SETTLE_SECONDS)
            finally:
                if pi is not None:
                    pi.stop()


def main():
    """引数を検査し、UDP PWM受信ループを開始する。"""
    parser = make_parser()
    args = parser.parse_args()
    validate_hardware_options(args, parser)
    run_receiver(args)


if __name__ == "__main__":
    main()
