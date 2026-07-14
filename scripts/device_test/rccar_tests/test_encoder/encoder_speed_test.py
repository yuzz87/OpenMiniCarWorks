#!/usr/bin/env python3
"""A/B相エンコーダだけを読み、車輪速度と累積距離を表示する。

このスクリプトはESC、モーター、ステアリング、PWMへ一切出力しない。
実機GPIOへアクセスするには、配線確認用フラグを明示的に指定する。

既定値のBCM 22/27、36 count/rev、タイヤ直径0.066 mは、リポジトリ内の
旧エンコーダコードから引き継いだ仮の校正値である。実機で必ず確認する。

角度はラジアン、距離はメートル、速度はメートル毎秒で扱う。
"""

from __future__ import annotations

import argparse
import csv
import math
import threading
import time
from pathlib import Path

DEFAULT_A_GPIO = 22
DEFAULT_B_GPIO = 27
DEFAULT_COUNTS_PER_WHEEL_REV = 36
DEFAULT_WHEEL_DIAMETER_M = 0.066
DEFAULT_DURATION_S = 10.0
DEFAULT_SAMPLE_HZ = 20.0
DEFAULT_ZERO_TIMEOUT_S = 0.25
DEFAULT_EMA_ALPHA = 0.30
DEFAULT_EXPECTED_SPEED_MPS = 0.30
DEFAULT_LOG_CSV = "encoder_speed_log.csv"


class WheelEncoder:
    """pigpioでA相立ち上がりを数える車輪エンコーダ。"""

    def __init__(
        self,
        pi,
        pigpio_module,
        *,
        a_gpio: int,
        b_gpio: int,
        counts_per_wheel_rev: int,
        wheel_diameter_m: float,
        zero_timeout_s: float,
        ema_alpha: float,
        invert_direction: bool,
        pull: str,
        glitch_filter_us: int,
        fixed_direction: int | None = None,
    ) -> None:
        self._pi = pi
        self._pigpio = pigpio_module
        self._a_gpio = a_gpio
        self._b_gpio = b_gpio
        self._distance_per_count_m = (
            math.pi * wheel_diameter_m / counts_per_wheel_rev
        )
        self._zero_timeout_us = int(zero_timeout_s * 1_000_000.0)
        self._ema_alpha = ema_alpha
        self._direction_scale = -1 if invert_direction else 1
        if fixed_direction not in (None, -1, 1):
            raise ValueError("fixed_directionはNone、-1、1のいずれかにしてください")
        self._fixed_direction = fixed_direction

        self._count = 0
        self._speed_mps = 0.0
        self._speed_initialized = False
        self._last_tick = None
        self._last_direction = None
        self._lock = threading.Lock()
        self._closed = False

        pi.set_mode(a_gpio, pigpio_module.INPUT)
        pi.set_mode(b_gpio, pigpio_module.INPUT)

        pull_modes = {
            "up": pigpio_module.PUD_UP,
            "down": pigpio_module.PUD_DOWN,
            "off": pigpio_module.PUD_OFF,
        }
        pi.set_pull_up_down(a_gpio, pull_modes[pull])
        pi.set_pull_up_down(b_gpio, pull_modes[pull])

        if glitch_filter_us > 0:
            pi.set_glitch_filter(a_gpio, glitch_filter_us)
            pi.set_glitch_filter(b_gpio, glitch_filter_us)

        self._callback = pi.callback(
            a_gpio,
            pigpio_module.RISING_EDGE,
            self._on_a_rising,
        )

    @property
    def distance_per_count_m(self) -> float:
        return self._distance_per_count_m

    def _on_a_rising(self, gpio: int, level: int, tick: int) -> None:
        if level != 1:
            return

        if self._fixed_direction is None:
            direction = -1 if self._pi.read(self._b_gpio) else 1
        else:
            # 前進専用試験では、Pythonコールバックの遅延による
            # B相方向誤判定を避け、A相立ち上がりを固定方向で数える。
            direction = self._fixed_direction
        direction *= self._direction_scale

        with self._lock:
            self._count += direction

            if self._last_tick is not None:
                dt_us = self._pigpio.tickDiff(self._last_tick, tick)
                same_direction = direction == self._last_direction
                recent_pulse = 0 < dt_us <= self._zero_timeout_us

                if same_direction and recent_pulse:
                    instantaneous_speed_mps = (
                        direction
                        * self._distance_per_count_m
                        / (dt_us * 1e-6)
                    )

                    if self._speed_initialized:
                        alpha = self._ema_alpha
                        self._speed_mps = (
                            alpha * instantaneous_speed_mps
                            + (1.0 - alpha) * self._speed_mps
                        )
                    else:
                        self._speed_mps = instantaneous_speed_mps
                        self._speed_initialized = True
                else:
                    # 停止後または回転方向変更後の最初の1パルスでは、
                    # 古いパルスとの時間差を速度へ使わない。
                    self._speed_mps = 0.0
                    self._speed_initialized = False

            self._last_tick = tick
            self._last_direction = direction

    def sample(self) -> tuple[int, float, float, float | None]:
        """count、距離[m]、速度[m/s]、最終パルス経過時間[s]を返す。"""
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
        self._pi.set_glitch_filter(self._a_gpio, 0)
        self._pi.set_glitch_filter(self._b_gpio, 0)
        self._closed = True


def validate_args(args: argparse.Namespace) -> None:
    if args.a_gpio == args.b_gpio:
        raise ValueError("A相とB相には異なるBCM GPIOを指定してください")
    if args.counts_per_wheel_rev <= 0:
        raise ValueError("--counts-per-wheel-revは正の整数にしてください")
    if args.wheel_diameter_m <= 0.0:
        raise ValueError("--wheel-diameter-mは正の値[m]にしてください")
    if args.duration_s <= 0.0:
        raise ValueError("--duration-sは正の値[s]にしてください")
    if args.sample_hz <= 0.0:
        raise ValueError("--sample-hzは正の値[Hz]にしてください")
    if args.zero_timeout_s <= 0.0:
        raise ValueError("--zero-timeout-sは正の値[s]にしてください")
    if not 0.0 < args.ema_alpha <= 1.0:
        raise ValueError("--ema-alphaは0より大きく1以下にしてください")
    if args.glitch_filter_us < 0:
        raise ValueError("--glitch-filter-usは0以上にしてください")


def print_configuration(args: argparse.Namespace) -> float:
    distance_per_count_m = (
        math.pi * args.wheel_diameter_m / args.counts_per_wheel_rev
    )
    expected_count_hz = (
        abs(args.expected_speed_mps) / distance_per_count_m
        if args.expected_speed_mps != 0.0
        else 0.0
    )

    print("encoder speed test")
    print(f"A phase: BCM GPIO {args.a_gpio}")
    print(f"B phase: BCM GPIO {args.b_gpio}")
    print(f"counts per wheel revolution: {args.counts_per_wheel_rev}")
    print(f"wheel diameter: {args.wheel_diameter_m:.6f} m")
    print(f"distance per count: {distance_per_count_m:.9f} m/count")
    print(f"sample rate: {args.sample_hz:.1f} Hz")
    print(f"duration: {args.duration_s:.2f} s")
    print(
        f"expected count rate at {args.expected_speed_mps:.3f} m/s: "
        f"{expected_count_hz:.2f} count/s"
    )
    print(f"input pull: {args.pull}")
    print(f"glitch filter: {args.glitch_filter_us} us")
    return distance_per_count_m


def run_dry(args: argparse.Namespace) -> None:
    print_configuration(args)
    print("[DRY] GPIOにはアクセスしていません。PWM・モーター出力もありません。")
    print(
        "実機入力を読む前に、エンコーダ出力が3.3 V互換であることと、"
        "共通GNDを確認してください。"
    )


def run_hardware(args: argparse.Namespace) -> None:
    if not args.confirm_3v3_compatible:
        raise RuntimeError(
            "実機入力には--confirm-3v3-compatibleが必要です。"
            "5 V出力をRaspberry Pi GPIOへ直接接続しないでください。"
        )
    if not args.confirm_common_ground:
        raise RuntimeError(
            "実機入力には--confirm-common-groundが必要です。"
            "Raspberry PiとエンコーダのGNDを共通にしてください。"
        )

    # Raspberry Pi実機で明示的に実行したときだけ読み込む。
    import pigpio  # type: ignore[import-not-found]

    print_configuration(args)
    print("[HARDWARE] エンコーダ入力だけを読みます。PWM出力は行いません。")

    pi = pigpio.pi()
    if not pi.connected:
        pi.stop()
        raise RuntimeError("pigpio daemonへ接続できません。Raspberry Pi上で確認してください")

    encoder = None
    log_file = None
    try:
        encoder = WheelEncoder(
            pi,
            pigpio,
            a_gpio=args.a_gpio,
            b_gpio=args.b_gpio,
            counts_per_wheel_rev=args.counts_per_wheel_rev,
            wheel_diameter_m=args.wheel_diameter_m,
            zero_timeout_s=args.zero_timeout_s,
            ema_alpha=args.ema_alpha,
            invert_direction=args.invert_direction,
            pull=args.pull,
            glitch_filter_us=args.glitch_filter_us,
        )

        log_path = Path(args.log_csv)
        log_file = log_path.open("w", newline="")
        writer = csv.writer(log_file)
        writer.writerow(
            [
                "elapsed_s",
                "count",
                "distance_m",
                "speed_mps",
                "pulse_age_s",
            ]
        )

        print("車輪を手で回すか、モーター電源を切った車体を手押ししてください。")
        print("Ctrl-Cで終了できます。")
        print("elapsed[s]  count  distance[m]  speed[m/s]  pulse_age[s]")

        period_s = 1.0 / args.sample_hz
        start_time = time.monotonic()
        next_sample_time = start_time

        while True:
            now = time.monotonic()
            elapsed_s = now - start_time
            if elapsed_s >= args.duration_s:
                break

            if now < next_sample_time:
                time.sleep(next_sample_time - now)
                now = time.monotonic()
                elapsed_s = now - start_time

            count, distance_m, speed_mps, pulse_age_s = encoder.sample()
            pulse_age_text = "" if pulse_age_s is None else f"{pulse_age_s:.6f}"

            writer.writerow(
                [
                    f"{elapsed_s:.6f}",
                    count,
                    f"{distance_m:.9f}",
                    f"{speed_mps:.9f}",
                    pulse_age_text,
                ]
            )
            log_file.flush()

            display_age = "--" if pulse_age_s is None else f"{pulse_age_s:.4f}"
            print(
                f"{elapsed_s:10.3f}  {count:5d}  {distance_m:11.5f}  "
                f"{speed_mps:10.4f}  {display_age:>12}"
            )

            next_sample_time += period_s
            if next_sample_time < now:
                next_sample_time = now + period_s

    except KeyboardInterrupt:
        print("\n計測を中断しました")
    finally:
        if encoder is not None:
            encoder.close()
        if log_file is not None:
            log_file.close()
        pi.stop()

    print(f"計測終了: CSV={args.log_csv}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="A/B相エンコーダから車輪速度と累積距離を計測する"
    )
    parser.add_argument("--use-hardware", action="store_true")
    parser.add_argument("--confirm-3v3-compatible", action="store_true")
    parser.add_argument("--confirm-common-ground", action="store_true")
    parser.add_argument("--a-gpio", type=int, default=DEFAULT_A_GPIO)
    parser.add_argument("--b-gpio", type=int, default=DEFAULT_B_GPIO)
    parser.add_argument(
        "--counts-per-wheel-rev",
        type=int,
        default=DEFAULT_COUNTS_PER_WHEEL_REV,
        help="A相立ち上がりで実測したタイヤ1回転当たりカウント数",
    )
    parser.add_argument(
        "--wheel-diameter-m",
        type=float,
        default=DEFAULT_WHEEL_DIAMETER_M,
    )
    parser.add_argument("--duration-s", type=float, default=DEFAULT_DURATION_S)
    parser.add_argument("--sample-hz", type=float, default=DEFAULT_SAMPLE_HZ)
    parser.add_argument(
        "--zero-timeout-s",
        type=float,
        default=DEFAULT_ZERO_TIMEOUT_S,
    )
    parser.add_argument("--ema-alpha", type=float, default=DEFAULT_EMA_ALPHA)
    parser.add_argument(
        "--expected-speed-mps",
        type=float,
        default=DEFAULT_EXPECTED_SPEED_MPS,
        help="DRY表示用。モーター指令には使用しない",
    )
    parser.add_argument(
        "--pull",
        choices=("up", "down", "off"),
        default="up",
        help="エンコーダ出力形式に合わせる。既定upは旧コード互換",
    )
    parser.add_argument("--glitch-filter-us", type=int, default=0)
    parser.add_argument("--invert-direction", action="store_true")
    parser.add_argument("--log-csv", default=DEFAULT_LOG_CSV)
    args = parser.parse_args()
    validate_args(args)
    return args


def main() -> None:
    args = parse_args()
    if args.use_hardware:
        run_hardware(args)
    else:
        run_dry(args)


if __name__ == "__main__":
    main()
