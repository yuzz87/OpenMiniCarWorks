#!/usr/bin/env python3
"""低速・駆動輪リフト専用のキーボードJog＋エンコーダ計測。

このスクリプトは明示的なハードウェア指定と安全確認がない限りPWMを出力しない。
最初のPowered run専用であり、床走行用ではない。

確認済みの現在値:

- ESC: BCM GPIO 12、70 Hz、中立10.3 %
- ステアリング: BCM GPIO 13、70 Hz、中立10.895 %
- 前進: ESC Duty比を中立より下げる
- 無負荷回転開始: 10.2 %付近
- 接地走行開始: 10.1 %付近
- エンコーダ: A=BCM22、B=BCM27、36 count/rev
- エンコーダ方向: Powered runの物理前進を基準に、符号反転なしで正にする

角度はラジアン、距離はメートル、速度はメートル毎秒で扱う。
"""

from __future__ import annotations

import argparse
import csv
import select
import sys
import termios
import time
import tty
from pathlib import Path

from encoder_speed_test import WheelEncoder

PWM_HZ = 70
ESC_GPIO = 12
STEERING_GPIO = 13

DEFAULT_ESC_NEUTRAL_DUTY = 10.3
DEFAULT_STEERING_NEUTRAL_DUTY = 10.895
DEFAULT_FORWARD_DUTY_LIMIT = 10.1
DEFAULT_SPEED_STEP_DUTY = 0.02
DEFAULT_RUN_SECONDS = 10.0
DEFAULT_LOG_HZ = 20.0
DEFAULT_LOG_CSV = "key_jog_encoder_log.csv"

PWM_SAFE_MIN = 7.50
PWM_SAFE_MAX = 13.00

ENCODER_A_GPIO = 22
ENCODER_B_GPIO = 27
ENCODER_COUNTS_PER_WHEEL_REV = 36
ENCODER_WHEEL_DIAMETER_M = 0.066
ENCODER_ZERO_TIMEOUT_S = 0.25
ENCODER_EMA_ALPHA = 0.30


class KeyboardInput:
    """Linux端末から1文字を非ブロッキングで読む。"""

    def __init__(self) -> None:
        self._fd = None
        self._old_settings = None

    def __enter__(self) -> "KeyboardInput":
        if not sys.stdin.isatty():
            raise RuntimeError("キーボードJogは対話端末から実行してください")
        self._fd = sys.stdin.fileno()
        self._old_settings = termios.tcgetattr(self._fd)
        tty.setcbreak(self._fd)
        return self

    def read(self) -> str | None:
        if select.select([sys.stdin], [], [], 0.0)[0]:
            return sys.stdin.read(1)
        return None

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if self._fd is not None and self._old_settings is not None:
            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old_settings)


def duty_to_pigpio(duty_percent: float) -> int:
    """Duty比[%]をpigpio.hardware_PWM用の0..1000000へ変換する。"""
    clamped = max(PWM_SAFE_MIN, min(PWM_SAFE_MAX, duty_percent))
    return int(round(clamped * 10_000.0))


def set_pwm(pi, esc_duty: float, steering_duty: float) -> None:
    """ESCとステアリングへPWMを出力する。"""
    esc_status = pi.hardware_PWM(
        ESC_GPIO,
        PWM_HZ,
        duty_to_pigpio(esc_duty),
    )
    steering_status = pi.hardware_PWM(
        STEERING_GPIO,
        PWM_HZ,
        duty_to_pigpio(steering_duty),
    )
    if esc_status != 0 or steering_status != 0:
        raise RuntimeError(
            "hardware_PWMに失敗しました: "
            f"ESC={esc_status}, steering={steering_status}"
        )


def set_neutral(pi, esc_neutral_duty: float, steering_neutral_duty: float) -> None:
    set_pwm(pi, esc_neutral_duty, steering_neutral_duty)


def validate_args(args: argparse.Namespace) -> None:
    for name, value in (
        ("--esc-neutral-duty", args.esc_neutral_duty),
        ("--steering-neutral-duty", args.steering_neutral_duty),
        ("--forward-duty-limit", args.forward_duty_limit),
    ):
        if not PWM_SAFE_MIN <= value <= PWM_SAFE_MAX:
            raise ValueError(
                f"{name}は{PWM_SAFE_MIN:.2f}〜{PWM_SAFE_MAX:.2f} %にしてください"
            )

    if args.forward_duty_limit >= args.esc_neutral_duty:
        raise ValueError(
            "前進はDuty比を下げる規約なので、--forward-duty-limitは"
            "--esc-neutral-dutyより小さくしてください"
        )
    if args.speed_step_duty <= 0.0:
        raise ValueError("--speed-step-dutyは正の値[%]にしてください")
    if args.run_seconds <= 0.0:
        raise ValueError("--run-secondsは正の値[s]にしてください")
    if args.log_hz <= 0.0:
        raise ValueError("--log-hzは正の値[Hz]にしてください")


def print_configuration(args: argparse.Namespace) -> None:
    print("key jog with encoder")
    print(f"PWM: ESC=BCM{ESC_GPIO}, steering=BCM{STEERING_GPIO}, {PWM_HZ} Hz")
    print(
        f"neutral: ESC={args.esc_neutral_duty:.3f} %, "
        f"steering={args.steering_neutral_duty:.3f} %"
    )
    print(
        f"forward range: {args.esc_neutral_duty:.3f} % -> "
        f"{args.forward_duty_limit:.3f} %, "
        f"step={args.speed_step_duty:.3f} %"
    )
    print(
        f"encoder: A=BCM{ENCODER_A_GPIO}, B=BCM{ENCODER_B_GPIO}, "
        f"{ENCODER_COUNTS_PER_WHEEL_REV} count/rev, "
        f"diameter={ENCODER_WHEEL_DIAMETER_M:.3f} m"
    )
    print("encoder direction: forward-only A-pulse counting (B direction ignored)")
    print(f"time limit: {args.run_seconds:.1f} s")
    print(f"CSV: {args.log_csv}")


def print_help() -> None:
    print("controls:")
    print("  r       : arm（このキーだけでは動かない）")
    print("  w       : 前進Dutyを1段増やす（Duty比を下げる）")
    print("  s       : 前進Dutyを1段戻す（中立へ近づける）")
    print("  n       : 即時中立・disarm")
    print("  Enter/q : 中立にして終了")


def require_hardware_confirmations(args: argparse.Namespace) -> None:
    required = {
        "--confirm-wheels-lifted": args.confirm_wheels_lifted,
        "--confirm-power-cutoff": args.confirm_power_cutoff,
        "--confirm-forward-duty-decreases": args.confirm_forward_duty_decreases,
        "--confirm-forward-duty-limit": args.confirm_forward_duty_limit,
        "--confirm-3v3-compatible": args.confirm_3v3_compatible,
        "--confirm-common-ground": args.confirm_common_ground,
    }
    missing = [name for name, confirmed in required.items() if not confirmed]
    if missing:
        raise RuntimeError(
            "Powered runに必要な確認が不足しています: " + ", ".join(missing)
        )


def run_dry(args: argparse.Namespace) -> None:
    print_configuration(args)
    print_help()
    print("[DRY] GPIO、PWM、モーター、ステアリングへアクセスしていません。")


def run_hardware(args: argparse.Namespace) -> None:
    require_hardware_confirmations(args)

    # Raspberry Pi実機で明示的に実行したときだけ読み込む。
    import pigpio  # type: ignore[import-not-found]

    print_configuration(args)
    print_help()
    print("[HARDWARE] 駆動輪リフト専用。床へ降ろさないでください。")
    print("[RISK] 前進上限10.1 %は、旧上限10.2 %より強い出力です。")

    pi = pigpio.pi()
    if not pi.connected:
        pi.stop()
        raise RuntimeError("pigpio daemonへ接続できません")

    encoder = None
    log_file = None
    writer = None
    esc_duty = args.esc_neutral_duty
    steering_duty = args.steering_neutral_duty
    armed = False
    stop_reason = "unknown"
    start_time = time.monotonic()

    try:
        pi.set_mode(ESC_GPIO, pigpio.OUTPUT)
        pi.set_mode(STEERING_GPIO, pigpio.OUTPUT)

        # 起動直後は必ず確認済みの中立値を出す。
        set_neutral(pi, args.esc_neutral_duty, args.steering_neutral_duty)
        time.sleep(1.0)

        encoder = WheelEncoder(
            pi,
            pigpio,
            a_gpio=ENCODER_A_GPIO,
            b_gpio=ENCODER_B_GPIO,
            counts_per_wheel_rev=ENCODER_COUNTS_PER_WHEEL_REV,
            wheel_diameter_m=ENCODER_WHEEL_DIAMETER_M,
            zero_timeout_s=ENCODER_ZERO_TIMEOUT_S,
            ema_alpha=ENCODER_EMA_ALPHA,
            # このJogは前進専用。高速時にPython側でB相を読むと方向が
            # 交互に誤判定されたため、A相立ち上がりを常に前進として数える。
            invert_direction=False,
            pull="up",
            glitch_filter_us=0,
            fixed_direction=1,
        )

        log_path = Path(args.log_csv)
        log_file = log_path.open("w", newline="")
        writer = csv.DictWriter(
            log_file,
            fieldnames=[
                "elapsed_s",
                "event",
                "armed",
                "esc_duty_percent",
                "steering_duty_percent",
                "encoder_count",
                "encoder_distance_m",
                "encoder_speed_mps",
                "pulse_age_s",
            ],
        )
        writer.writeheader()

        print("中立を出力しました。準備後にrでarmし、wを1回だけ押してください。")
        print("elapsed  event  arm  ESC[%]  count  distance[m]  speed[m/s]")

        log_period_s = 1.0 / args.log_hz
        next_log_time = time.monotonic()

        with KeyboardInput() as keyboard:
            while True:
                now = time.monotonic()
                elapsed_s = now - start_time
                event = ""

                if elapsed_s >= args.run_seconds:
                    stop_reason = "time_limit"
                    break

                key = keyboard.read()
                if key is not None:
                    if key == "r":
                        armed = True
                        event = "armed"
                    elif key == "w":
                        if armed:
                            esc_duty = max(
                                args.forward_duty_limit,
                                esc_duty - args.speed_step_duty,
                            )
                            event = "forward_step"
                        else:
                            event = "ignored_not_armed"
                    elif key == "s":
                        esc_duty = min(
                            args.esc_neutral_duty,
                            esc_duty + args.speed_step_duty,
                        )
                        event = "toward_neutral"
                    elif key == "n":
                        esc_duty = args.esc_neutral_duty
                        armed = False
                        event = "neutral_disarm"
                    elif key in ("\n", "\r", "q"):
                        stop_reason = "user_exit"
                        break
                    else:
                        event = f"unknown_key_{ord(key)}"

                    set_pwm(pi, esc_duty, steering_duty)

                if now >= next_log_time or event:
                    count, distance_m, speed_mps, pulse_age_s = encoder.sample()
                    writer.writerow(
                        {
                            "elapsed_s": f"{elapsed_s:.6f}",
                            "event": event or "sample",
                            "armed": int(armed),
                            "esc_duty_percent": f"{esc_duty:.6f}",
                            "steering_duty_percent": f"{steering_duty:.6f}",
                            "encoder_count": count,
                            "encoder_distance_m": f"{distance_m:.9f}",
                            "encoder_speed_mps": f"{speed_mps:.9f}",
                            "pulse_age_s": (
                                "" if pulse_age_s is None else f"{pulse_age_s:.6f}"
                            ),
                        }
                    )
                    log_file.flush()
                    print(
                        f"{elapsed_s:7.3f}  {(event or 'sample'):16s}  "
                        f"{int(armed):3d}  {esc_duty:6.3f}  {count:5d}  "
                        f"{distance_m:11.5f}  {speed_mps:10.4f}"
                    )
                    next_log_time = now + log_period_s

                time.sleep(0.005)

    except KeyboardInterrupt:
        stop_reason = "keyboard_interrupt"
        print("\nCtrl-Cを受信しました")
    except Exception:
        stop_reason = "exception"
        raise
    finally:
        # 正常終了、時間上限、Ctrl-C、例外のすべてで中立へ戻す。
        try:
            set_neutral(pi, args.esc_neutral_duty, args.steering_neutral_duty)
            time.sleep(1.0)
        finally:
            if encoder is not None:
                if writer is not None and log_file is not None:
                    count, distance_m, speed_mps, pulse_age_s = encoder.sample()
                    writer.writerow(
                        {
                            "elapsed_s": f"{time.monotonic() - start_time:.6f}",
                            "event": f"neutral_exit:{stop_reason}",
                            "armed": 0,
                            "esc_duty_percent": f"{args.esc_neutral_duty:.6f}",
                            "steering_duty_percent": (
                                f"{args.steering_neutral_duty:.6f}"
                            ),
                            "encoder_count": count,
                            "encoder_distance_m": f"{distance_m:.9f}",
                            "encoder_speed_mps": f"{speed_mps:.9f}",
                            "pulse_age_s": (
                                "" if pulse_age_s is None else f"{pulse_age_s:.6f}"
                            ),
                        }
                    )
                    log_file.flush()
                encoder.close()
            if log_file is not None:
                log_file.close()
            pi.stop()

    print(f"終了: reason={stop_reason}, CSV={args.log_csv}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="低速・駆動輪リフト専用のJog操作とエンコーダ計測"
    )
    parser.add_argument("--enable-hardware", action="store_true")
    parser.add_argument("--confirm-wheels-lifted", action="store_true")
    parser.add_argument("--confirm-power-cutoff", action="store_true")
    parser.add_argument("--confirm-forward-duty-decreases", action="store_true")
    parser.add_argument(
        "--confirm-forward-duty-limit",
        action="store_true",
        help="10.1 %までDuty比を下げる強い前進範囲を確認したことを明示",
    )
    parser.add_argument("--confirm-3v3-compatible", action="store_true")
    parser.add_argument("--confirm-common-ground", action="store_true")

    parser.add_argument(
        "--esc-neutral-duty",
        type=float,
        default=DEFAULT_ESC_NEUTRAL_DUTY,
    )
    parser.add_argument(
        "--steering-neutral-duty",
        type=float,
        default=DEFAULT_STEERING_NEUTRAL_DUTY,
    )
    parser.add_argument(
        "--forward-duty-limit",
        type=float,
        default=DEFAULT_FORWARD_DUTY_LIMIT,
        help="最初のリフト試験で許可する最小ESC Duty比[%]",
    )
    parser.add_argument(
        "--speed-step-duty",
        type=float,
        default=DEFAULT_SPEED_STEP_DUTY,
    )
    parser.add_argument(
        "--run-seconds",
        type=float,
        default=DEFAULT_RUN_SECONDS,
    )
    parser.add_argument("--log-hz", type=float, default=DEFAULT_LOG_HZ)
    parser.add_argument("--log-csv", default=DEFAULT_LOG_CSV)

    args = parser.parse_args()
    validate_args(args)
    return args


def main() -> None:
    args = parse_args()
    if args.enable_hardware:
        run_hardware(args)
    else:
        run_dry(args)


if __name__ == "__main__":
    main()
