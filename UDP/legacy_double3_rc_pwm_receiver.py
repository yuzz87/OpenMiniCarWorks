#!/usr/bin/env python3
"""現在のSimulink double x3パケットを受信し、必要に応じてRC用PWMを出力する。

既定ではドライランで動作する。GPIO、pigpio、ESC、ステアリングPWMへは、
--enable-hardware と安全確認オプションを明示したときだけアクセスする。

現在確認しているパケット形式:
- little-endian float64 x 3
- [legacy_motor_1, legacy_motor_2, legacy_servo_deg]

ドライラン/実機モードでの解釈:
- legacy_motor_1/2 は平均した後、--speed-per-legacy-unit により
  目標速度 [m/s] へ変換する。
- legacy_servo_deg は次の式で推定ステア角 [deg] へ変換する。
  steer_deg = legacy_steer_a * legacy_servo_deg + legacy_steer_b

単位:
- target_speed_mps: m/s
- target_steer_rad: rad
- PWM duty: percent
"""

import argparse
import math
import socket
import struct
import time
from dataclasses import dataclass


DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 5005
FMT = "<ddd"
NBYTES = struct.calcsize(FMT)
MAX_PACKET_BYTES = 1024

# PWM出力設定。GPIO番号はBCM表記。
DEFAULT_PWM_HZ = 70
DEFAULT_ESC_GPIO = 12
DEFAULT_STEERING_GPIO = 13

# 現在のRCカー校正値。dutyの単位は[%]。
DEFAULT_STEERING_NEUTRAL_DUTY = 10.895
DEFAULT_ESC_NEUTRAL_DUTY = 10.55

# steer_angle_rad = DUTY_FIT_A * steering_duty_percent + DUTY_FIT_B
DUTY_FIT_A = -0.186785136654
DUTY_FIT_B = 2.018473280947

# speed_mps = -SPEED_FIT_ALPHA * esc_duty_percent + SPEED_FIT_BETA
SPEED_FIT_ALPHA = 2.4618
SPEED_FIT_BETA = 25.347

DEFAULT_STEERING_SAFE_MIN = 7.50
DEFAULT_STEERING_SAFE_MAX = 13.00
DEFAULT_ESC_SAFE_MIN = 9.50
DEFAULT_ESC_SAFE_MAX = 13.00

DEFAULT_MAX_SPEED_MPS = 0.30
DEFAULT_MAX_STEER_RAD = math.radians(18.0)
ZERO_SPEED_EPS_MPS = 1e-6

# Simulink図面の線形式: y = -0.8246 x + 74.212
DEFAULT_LEGACY_STEER_A = -0.8246
DEFAULT_LEGACY_STEER_B = 74.212
DEFAULT_MOTOR_MISMATCH_TOL = 1e-6
DEFAULT_PARAM_INIT_SERVO_DEG = 90.0
DEFAULT_PARAM_INIT_TOL = 1e-6

DEFAULT_WATCHDOG_TIMEOUT_SECONDS = 0.30
DEFAULT_SOCKET_TIMEOUT_SECONDS = 0.02
NEUTRAL_SETTLE_SECONDS = 1.0


@dataclass
class PwmCommand:
    raw_1: float
    raw_2: float
    raw_3: float
    target_speed_mps: float
    target_steer_rad: float
    steering_duty_percent: float
    esc_duty_percent: float
    status: str
    safe_to_output: bool


LIMITED_OUTPUT_ALLOWED_STATUSES = {
    "negative_speed",
    "clamped_speed",
    "clamped_steer",
}


def clamp(value, low, high):
    return max(low, min(high, value))


def decode_packet(data):
    if len(data) != NBYTES:
        return None
    return struct.unpack(FMT, data)


def duty_to_pigpio(duty_percent):
    return int(round(duty_percent * 10000))


def is_in_range(value, low, high):
    return low <= value <= high


def steering_rad_to_duty_percent(target_steer_rad):
    return (target_steer_rad - DUTY_FIT_B) / DUTY_FIT_A


def speed_mps_to_esc_duty_percent(target_speed_mps, neutral_duty):
    if abs(target_speed_mps) <= ZERO_SPEED_EPS_MPS:
        return neutral_duty
    return (SPEED_FIT_BETA - target_speed_mps) / SPEED_FIT_ALPHA


def make_neutral_command(args, status):
    return PwmCommand(
        raw_1=0.0,
        raw_2=0.0,
        raw_3=90.0,
        target_speed_mps=0.0,
        target_steer_rad=0.0,
        steering_duty_percent=args.steering_neutral_duty,
        esc_duty_percent=args.esc_neutral_duty,
        status=status,
        safe_to_output=True,
    )


def is_param_init(raw_1, raw_2, raw_3, args):
    return (
        abs(raw_1) <= args.motor_mismatch_tol
        and abs(raw_2) <= args.motor_mismatch_tol
        and abs(raw_3 - args.param_init_servo_deg) <= args.param_init_tol
    )


def make_pwm_command(raw_values, args):
    raw_1, raw_2, raw_3 = raw_values
    status_parts = []

    if is_param_init(raw_1, raw_2, raw_3, args):
        command = make_neutral_command(args, "param_init_neutral")
        command.raw_1 = raw_1
        command.raw_2 = raw_2
        command.raw_3 = raw_3
        return command

    if not all(math.isfinite(value) for value in raw_values):
        status_parts.append("nonfinite_raw")

    if abs(raw_1 - raw_2) > args.motor_mismatch_tol:
        status_parts.append("legacy_motor_mismatch")

    if args.speed_per_legacy_unit <= 0.0:
        status_parts.append("speed_scale_unset")

    legacy_motor_avg = 0.5 * (raw_1 + raw_2)
    target_speed_mps = legacy_motor_avg * args.speed_per_legacy_unit
    target_steer_deg = args.legacy_steer_a * raw_3 + args.legacy_steer_b
    target_steer_rad = math.radians(target_steer_deg)

    if target_speed_mps < -ZERO_SPEED_EPS_MPS:
        status_parts.append("negative_speed")

    limited_speed_mps = clamp(target_speed_mps, 0.0, args.max_speed_mps)
    if limited_speed_mps != target_speed_mps:
        status_parts.append("clamped_speed")

    limited_steer_rad = clamp(
        target_steer_rad,
        -args.max_steer_rad,
        args.max_steer_rad,
    )
    if limited_steer_rad != target_steer_rad:
        status_parts.append("clamped_steer")

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
        status_parts.append("steering_duty_out_of_range")

    if not is_in_range(esc_duty, args.esc_safe_min, args.esc_safe_max):
        status_parts.append("esc_duty_out_of_range")

    if not status_parts:
        status_parts.append("ok")

    safe_to_output = status_parts == ["ok"]
    return PwmCommand(
        raw_1=raw_1,
        raw_2=raw_2,
        raw_3=raw_3,
        target_speed_mps=limited_speed_mps,
        target_steer_rad=limited_steer_rad,
        steering_duty_percent=steering_duty,
        esc_duty_percent=esc_duty,
        status=",".join(status_parts),
        safe_to_output=safe_to_output,
    )


def print_command(prefix, sender, command):
    sender_text = "-" if sender is None else f"{sender[0]}:{sender[1]}"
    print(
        "{} sender={} raw=({:.9f}, {:.9f}, {:.9f}) "
        "target_speed_mps={:.9f} m/s target_steer_rad={:.9f} rad "
        "target_steer_deg={:.4f} deg steering_duty={:.6f} % "
        "esc_duty={:.6f} % status={}".format(
            prefix,
            sender_text,
            command.raw_1,
            command.raw_2,
            command.raw_3,
            command.target_speed_mps,
            command.target_steer_rad,
            math.degrees(command.target_steer_rad),
            command.steering_duty_percent,
            command.esc_duty_percent,
            command.status,
        )
    )


def set_pwm(pi, args, command):
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
    prefix = "PWM" if args.enable_hardware else "DRY"
    print_command(prefix, sender, command)
    if args.enable_hardware:
        set_pwm(pi, args, command)


def can_output_limited(command):
    status_parts = set(command.status.split(","))
    return bool(status_parts) and status_parts <= LIMITED_OUTPUT_ALLOWED_STATUSES


def output_limited_command(pi, args, command, sender):
    prefix = "LIMITED_PWM" if args.enable_hardware else "LIMITED_DRY"
    print_command(prefix, sender, command)
    if args.enable_hardware:
        set_pwm(pi, args, command)


def output_received_command(pi, args, command, sender):
    if command.safe_to_output:
        output_command(pi, args, command, sender)
        return

    if args.allow_limited_output and can_output_limited(command):
        output_limited_command(pi, args, command, sender)
        return

    print_command("REJECT", sender, command)
    neutral_command = make_neutral_command(args, "invalid_neutral")
    output_command(pi, args, neutral_command, None)


def setup_hardware(args):
    import pigpio

    pi = pigpio.pi()
    if not pi.connected:
        raise RuntimeError("pigpioデーモンが起動していません（sudo pigpiod で起動してください）")

    pi.set_mode(args.esc_gpio, pigpio.OUTPUT)
    pi.set_mode(args.steering_gpio, pigpio.OUTPUT)
    return pi


def validate_hardware_options(args, parser):
    if not args.enable_hardware:
        return
    if not args.confirm_wheels_lifted:
        parser.error("--enable-hardware を使うには --confirm-wheels-lifted が必要です")
    if not args.confirm_power_cutoff:
        parser.error("--enable-hardware を使うには --confirm-power-cutoff が必要です")
    if args.allow_limited_output and not args.confirm_accept_limited_output:
        parser.error(
            "--enable-hardware と --allow-limited-output を使うには "
            "--confirm-accept-limited-output が必要です"
        )
    if args.speed_per_legacy_unit <= 0.0:
        parser.error("--enable-hardware を使うには --speed-per-legacy-unit > 0 が必要です")


def make_parser():
    parser = argparse.ArgumentParser(
        description="legacy double x3 のUDPパケットを受信し、RC用PWMへ変換する。"
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
    parser.add_argument("--max-speed-mps", type=float, default=DEFAULT_MAX_SPEED_MPS)
    parser.add_argument("--max-steer-rad", type=float, default=DEFAULT_MAX_STEER_RAD)
    parser.add_argument(
        "--speed-per-legacy-unit",
        type=float,
        default=0.0,
        help="legacy motor command を速度 [m/s] へ変換する線形スケール。",
    )
    parser.add_argument(
        "--legacy-steer-a",
        type=float,
        default=DEFAULT_LEGACY_STEER_A,
        help="legacy servo値[deg]から実ステア角[deg]へ変換する傾き。",
    )
    parser.add_argument(
        "--legacy-steer-b",
        type=float,
        default=DEFAULT_LEGACY_STEER_B,
        help="legacy servo値[deg]から実ステア角[deg]へ変換する切片。",
    )
    parser.add_argument(
        "--motor-mismatch-tol",
        type=float,
        default=DEFAULT_MOTOR_MISMATCH_TOL,
    )
    parser.add_argument(
        "--param-init-servo-deg",
        type=float,
        default=DEFAULT_PARAM_INIT_SERVO_DEG,
        help="Param_init の中立値として扱う legacy servo値[deg]。",
    )
    parser.add_argument(
        "--param-init-tol",
        type=float,
        default=DEFAULT_PARAM_INIT_TOL,
        help="Param_init 中立パケットを判定する許容誤差。",
    )
    parser.add_argument(
        "--watchdog-timeout",
        type=float,
        default=DEFAULT_WATCHDOG_TIMEOUT_SECONDS,
        help="中立PWMを出すまでのタイムアウト[s]。",
    )
    parser.add_argument(
        "--socket-timeout",
        type=float,
        default=DEFAULT_SOCKET_TIMEOUT_SECONDS,
        help="UDP受信ポーリングのタイムアウト[s]。",
    )
    parser.add_argument(
        "--enable-hardware",
        action="store_true",
        help="pigpioを使って実際にPWMを出力する。既定はドライラン。",
    )
    parser.add_argument(
        "--allow-limited-output",
        action="store_true",
        help=(
            "negative_speed / clamped_speed / clamped_steer を拒否せず、"
            "設定した制限を適用した後の速度・操舵を出力する。"
            "それ以外の不正指令は引き続き拒否する。"
        ),
    )
    parser.add_argument(
        "--confirm-accept-limited-output",
        action="store_true",
        help="--enable-hardware と --allow-limited-output を使うときに必要。",
    )
    parser.add_argument(
        "--confirm-wheels-lifted",
        action="store_true",
        help="--enable-hardware を使うときに必要。",
    )
    parser.add_argument(
        "--confirm-power-cutoff",
        action="store_true",
        help="--enable-hardware を使うときに必要。",
    )
    return parser


def run_receiver(args):
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
        print(f"受信待機中 {(args.host, args.port)}")
        print(
            "mode={}, packet=float64x3, pwm_hz={}, esc_gpio={}, "
            "steering_gpio={}, watchdog_timeout={:.3f} s, "
            "speed_per_legacy_unit={:.9f}".format(
                "hardware" if args.enable_hardware else "dry-run",
                args.pwm_hz,
                args.esc_gpio,
                args.steering_gpio,
                args.watchdog_timeout,
                args.speed_per_legacy_unit,
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

                raw_values = decode_packet(packet)
                if raw_values is None:
                    print(f"不正なパケット {sender}: {len(packet)} bytes")
                    command = make_neutral_command(args, "invalid_neutral")
                    output_command(pi, args, command, None)
                    continue

                command = make_pwm_command(raw_values, args)
                output_received_command(pi, args, command, sender)
        except KeyboardInterrupt:
            print("Ctrl-Cにより停止しました")
        finally:
            print("終了前に中立を出力します")
            try:
                output_command(pi, args, neutral_command, None)
                if args.enable_hardware:
                    time.sleep(NEUTRAL_SETTLE_SECONDS)
            finally:
                if pi is not None:
                    pi.stop()


def main():
    parser = make_parser()
    args = parser.parse_args()
    validate_hardware_options(args, parser)
    run_receiver(args)


if __name__ == "__main__":
    main()
