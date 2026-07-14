#!/usr/bin/env python3
"""前進Jogとエンコーダ速度計測を1ファイルで行う実機確認用スクリプト。

通常実行ではGPIOへアクセスしない。実機モードは駆動輪リフト専用。
距離はメートル、速度はメートル毎秒、Duty比はパーセントで扱う。
"""

from __future__ import annotations

import argparse
import csv
import math
import select
import sys
import termios
import threading
import time
import tty
from pathlib import Path

PWM_HZ = 70
ESC_GPIO = 12
STEERING_GPIO = 13
ESC_NEUTRAL_DUTY = 10.300
STEERING_NEUTRAL_DUTY = 10.895
FORWARD_DUTY_LIMIT = 10.100
SPEED_STEP_DUTY = 0.020
PWM_SAFE_MIN = 7.500
PWM_SAFE_MAX = 13.000

ENCODER_A_GPIO = 22
ENCODER_B_GPIO = 27
ENCODER_COUNTS_PER_REV = 36
WHEEL_DIAMETER_M = 0.066
ZERO_TIMEOUT_S = 0.25
EMA_ALPHA = 0.30

DEFAULT_RUN_SECONDS = 10.0
DEFAULT_LOG_HZ = 20.0
DEFAULT_LOG_CSV = "key_jog_encoder_standalone_log.csv"


class ForwardWheelEncoder:
    """A相立ち上がりを前進の正カウントとして記録する。"""

    def __init__(self, pi, pigpio_module) -> None:
        self._pi = pi
        self._pigpio = pigpio_module
        self._distance_per_count_m = (
            math.pi * WHEEL_DIAMETER_M / ENCODER_COUNTS_PER_REV
        )
        self._zero_timeout_us = int(ZERO_TIMEOUT_S * 1_000_000.0)
        self._count = 0
        self._speed_mps = 0.0
        self._speed_ready = False
        self._last_tick = None
        self._lock = threading.Lock()
        self._closed = False

        pi.set_mode(ENCODER_A_GPIO, pigpio_module.INPUT)
        pi.set_mode(ENCODER_B_GPIO, pigpio_module.INPUT)
        pi.set_pull_up_down(ENCODER_A_GPIO, pigpio_module.PUD_UP)
        pi.set_pull_up_down(ENCODER_B_GPIO, pigpio_module.PUD_UP)
        self._callback = pi.callback(
            ENCODER_A_GPIO,
            pigpio_module.RISING_EDGE,
            self._on_a_rising,
        )

    def _on_a_rising(self, gpio: int, level: int, tick: int) -> None:
        if level != 1:
            return

        with self._lock:
            self._count += 1
            if self._last_tick is not None:
                dt_us = self._pigpio.tickDiff(self._last_tick, tick)
                if 0 < dt_us <= self._zero_timeout_us:
                    measured_speed = self._distance_per_count_m / (dt_us * 1e-6)
                    if self._speed_ready:
                        self._speed_mps = (
                            EMA_ALPHA * measured_speed
                            + (1.0 - EMA_ALPHA) * self._speed_mps
                        )
                    else:
                        self._speed_mps = measured_speed
                        self._speed_ready = True
                else:
                    self._speed_mps = 0.0
                    self._speed_ready = False
            self._last_tick = tick

    def sample(self) -> tuple[int, float, float, float | None]:
        current_tick = self._pi.get_current_tick()
        with self._lock:
            count = self._count
            speed_mps = self._speed_mps
            last_tick = self._last_tick

        pulse_age_s = None
        if last_tick is not None:
            pulse_age_us = self._pigpio.tickDiff(last_tick, current_tick)
            pulse_age_s = pulse_age_us * 1e-6
            if pulse_age_us >= self._zero_timeout_us:
                speed_mps = 0.0

        distance_m = count * self._distance_per_count_m
        return count, distance_m, speed_mps, pulse_age_s

    def close(self) -> None:
        if self._closed:
            return
        self._callback.cancel()
        self._closed = True


class KeyboardInput:
    def __init__(self) -> None:
        self._fd = None
        self._old_settings = None

    def __enter__(self) -> "KeyboardInput":
        if not sys.stdin.isatty():
            raise RuntimeError("対話端末から実行してください")
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
    if not PWM_SAFE_MIN <= duty_percent <= PWM_SAFE_MAX:
        raise ValueError(f"Duty比が安全範囲外です: {duty_percent:.3f} %")
    return int(round(duty_percent * 10_000.0))


def set_pwm(pi, esc_duty: float, steering_duty: float) -> None:
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
            f"PWM出力に失敗しました: ESC={esc_status}, steering={steering_status}"
        )


def set_neutral(pi) -> None:
    set_pwm(pi, ESC_NEUTRAL_DUTY, STEERING_NEUTRAL_DUTY)


def print_configuration(args: argparse.Namespace) -> None:
    print("前進Jog＋エンコーダ速度計測（単体版）")
    print(f"PWM: ESC=BCM{ESC_GPIO}, steering=BCM{STEERING_GPIO}, {PWM_HZ} Hz")
    print(
        f"中立: ESC={ESC_NEUTRAL_DUTY:.3f} %, "
        f"steering={STEERING_NEUTRAL_DUTY:.3f} %"
    )
    print(
        f"前進範囲: {ESC_NEUTRAL_DUTY:.3f} % -> {FORWARD_DUTY_LIMIT:.3f} %, "
        f"刻み={SPEED_STEP_DUTY:.3f} %"
    )
    print(
        f"encoder: A=BCM{ENCODER_A_GPIO}, B=BCM{ENCODER_B_GPIO}, "
        f"{ENCODER_COUNTS_PER_REV} count/rev, diameter={WHEEL_DIAMETER_M:.3f} m"
    )
    print("方向: 前進専用。A相パルスを正に数え、B相は方向判定に使いません")
    print(f"時間上限: {args.run_seconds:.1f} s")
    print(f"CSV: {args.log_csv}")
    print("操作: r=arm, w=前進を1段増加, s=中立へ1段戻す")
    print("      n=即時中立, Enter/q=中立にして終了")


def require_confirmations(args: argparse.Namespace) -> None:
    required = {
        "--confirm-wheels-lifted": args.confirm_wheels_lifted,
        "--confirm-power-cutoff": args.confirm_power_cutoff,
        "--confirm-forward-duty-decreases": args.confirm_forward_duty_decreases,
        "--confirm-forward-duty-limit": args.confirm_forward_duty_limit,
        "--confirm-3v3-compatible": args.confirm_3v3_compatible,
        "--confirm-common-ground": args.confirm_common_ground,
    }
    missing = [name for name, ok in required.items() if not ok]
    if missing:
        raise RuntimeError("安全確認が不足しています: " + ", ".join(missing))


def write_log_row(
    writer,
    elapsed_s: float,
    event: str,
    armed: bool,
    esc_duty: float,
    encoder: ForwardWheelEncoder,
) -> tuple[int, float, float, float | None]:
    count, distance_m, speed_mps, pulse_age_s = encoder.sample()
    writer.writerow(
        {
            "elapsed_s": f"{elapsed_s:.6f}",
            "event": event,
            "armed": int(armed),
            "esc_duty_percent": f"{esc_duty:.6f}",
            "steering_duty_percent": f"{STEERING_NEUTRAL_DUTY:.6f}",
            "encoder_count": count,
            "encoder_distance_m": f"{distance_m:.9f}",
            "encoder_speed_mps": f"{speed_mps:.9f}",
            "pulse_age_s": "" if pulse_age_s is None else f"{pulse_age_s:.6f}",
        }
    )
    return count, distance_m, speed_mps, pulse_age_s


def run_dry(args: argparse.Namespace) -> None:
    print_configuration(args)
    print("[DRY] GPIO、PWM、モーター、ステアリングへアクセスしていません")


def run_hardware(args: argparse.Namespace) -> None:
    require_confirmations(args)

    import pigpio  # type: ignore[import-not-found]

    print_configuration(args)
    print("[HARDWARE] 駆動輪を床から浮かせた状態だけで使用してください")
    print("[RISK] 10.100 %は接地時に車体が動いた確認済みの出力です")

    pi = pigpio.pi()
    if not pi.connected:
        pi.stop()
        raise RuntimeError("pigpio daemonへ接続できません")

    encoder = None
    log_file = None
    writer = None
    esc_duty = ESC_NEUTRAL_DUTY
    armed = False
    stop_reason = "unknown"
    start_time = time.monotonic()

    try:
        pi.set_mode(ESC_GPIO, pigpio.OUTPUT)
        pi.set_mode(STEERING_GPIO, pigpio.OUTPUT)
        set_neutral(pi)
        time.sleep(1.0)

        encoder = ForwardWheelEncoder(pi, pigpio)
        log_file = Path(args.log_csv).open("w", newline="", encoding="utf-8")
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

        print("中立を出力しました。rを押し、その後wを1回ずつ押してください")
        print("elapsed  event             arm  ESC[%]  count  distance[m]  speed[m/s]")

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
                                FORWARD_DUTY_LIMIT,
                                esc_duty - SPEED_STEP_DUTY,
                            )
                            event = "forward_step"
                        else:
                            event = "ignored_not_armed"
                    elif key == "s":
                        esc_duty = min(
                            ESC_NEUTRAL_DUTY,
                            esc_duty + SPEED_STEP_DUTY,
                        )
                        event = "toward_neutral"
                    elif key == "n":
                        esc_duty = ESC_NEUTRAL_DUTY
                        armed = False
                        event = "neutral_disarm"
                    elif key in ("\n", "\r", "q"):
                        stop_reason = "user_exit"
                        break
                    else:
                        event = f"unknown_key_{ord(key)}"

                    set_pwm(pi, esc_duty, STEERING_NEUTRAL_DUTY)

                if now >= next_log_time or event:
                    count, distance_m, speed_mps, _ = write_log_row(
                        writer,
                        elapsed_s,
                        event or "sample",
                        armed,
                        esc_duty,
                        encoder,
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
        try:
            set_neutral(pi)
            time.sleep(1.0)
        finally:
            if encoder is not None:
                if writer is not None and log_file is not None:
                    write_log_row(
                        writer,
                        time.monotonic() - start_time,
                        f"neutral_exit:{stop_reason}",
                        False,
                        ESC_NEUTRAL_DUTY,
                        encoder,
                    )
                    log_file.flush()
                encoder.close()
            if log_file is not None:
                log_file.close()
            pi.stop()

    print(f"終了: reason={stop_reason}, CSV={args.log_csv}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="前進Jogとエンコーダ速度計測を単体で実行する"
    )
    parser.add_argument("--enable-hardware", action="store_true")
    parser.add_argument("--confirm-wheels-lifted", action="store_true")
    parser.add_argument("--confirm-power-cutoff", action="store_true")
    parser.add_argument("--confirm-forward-duty-decreases", action="store_true")
    parser.add_argument("--confirm-forward-duty-limit", action="store_true")
    parser.add_argument("--confirm-3v3-compatible", action="store_true")
    parser.add_argument("--confirm-common-ground", action="store_true")
    parser.add_argument("--run-seconds", type=float, default=DEFAULT_RUN_SECONDS)
    parser.add_argument("--log-hz", type=float, default=DEFAULT_LOG_HZ)
    parser.add_argument("--log-csv", default=DEFAULT_LOG_CSV)
    args = parser.parse_args()

    if args.run_seconds <= 0.0:
        parser.error("--run-secondsは正の値[s]にしてください")
    if args.log_hz <= 0.0:
        parser.error("--log-hzは正の値[Hz]にしてください")
    return args


def main() -> None:
    args = parse_args()
    if args.enable_hardware:
        run_hardware(args)
    else:
        run_dry(args)


if __name__ == "__main__":
    main()
