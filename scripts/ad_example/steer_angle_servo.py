# 車両のステア角[deg]を指定してステアリングサーボへPWM出力するサンプル。
#
# 既定では実機へPWMを出さず、計算結果だけ表示する。
# 実機で動かす場合は、駆動輪を浮かせて物理的に停止できる状態にし、
# sudo pigpiod を起動してから --enable-hardware を付けて実行する。

import argparse
import importlib
import math
import time

# duty比[%]で作ったステアリング変換式。
# steer_angle_rad = DUTY_FIT_A * str_duty_percent + DUTY_FIT_B
# 入力角度: 車両ステア角[deg]
# 内部角度: 車両ステア角[rad]
DUTY_FIT_A = -0.186785136654
DUTY_FIT_B = 2.018473280947

# PWM周波数[Hz]。
PWM_HZ = 70

# Raspberry Pi BCM GPIO番号。
# ESCは中立固定、ステアリングだけ動かす。
GPIO_ACC = 12
GPIO_STR = 13

# 中立duty比[%]。
PWM_NEUTRAL_STR = 10.895
PWM_NEUTRAL_SPD = 10.55

# 安全のため、ステアリングへ出してよいduty比[%]をこの範囲に限定する。
PWM_SAFE_MIN = 7.50
PWM_SAFE_MAX = 13.00

NEUTRAL_SETTLE_SECONDS = 1.0
HOLD_SECONDS = 1.0


def steer_deg_to_duty_percent(target_steer_deg):
    """車両ステア角[deg]をステアリングPWM duty比[%]へ変換する。"""
    target_steer_rad = math.radians(target_steer_deg)
    duty_percent = (target_steer_rad - DUTY_FIT_B) / DUTY_FIT_A
    return target_steer_rad, duty_percent


def duty_to_pigpio(duty_percent):
    """duty比[%]をpigpio.hardware_PWM用の0..1000000の整数値へ変換する。"""
    return int(round(duty_percent * 10000))


def is_duty_out_of_range(duty_percent):
    """duty比[%]が安全範囲外ならTrueを返す。"""
    return duty_percent < PWM_SAFE_MIN or duty_percent > PWM_SAFE_MAX


def print_command(target_steer_deg, target_steer_rad, duty_percent):
    print(f"target_steer_deg={target_steer_deg:.4f} deg")
    print(f"target_steer_rad={target_steer_rad:.6f} rad")
    print(f"command_duty_percent={duty_percent:.9f} %")


def set_pwm(pi, spd_duty, str_duty):
    """ESCとステアリングへPWMを出力する。"""
    pi.hardware_PWM(GPIO_ACC, PWM_HZ, duty_to_pigpio(spd_duty))
    pi.hardware_PWM(GPIO_STR, PWM_HZ, duty_to_pigpio(str_duty))


def set_neutral(pi):
    """ESCとステアリングを中立へ戻す。"""
    set_pwm(pi, PWM_NEUTRAL_SPD, PWM_NEUTRAL_STR)


def run_hardware(target_steer_deg, duty_percent, hold_seconds):
    """ESCを中立にしたまま、指定した車両ステア角に対応するPWMを出す。"""
    # Raspberry Pi上で実車出力するときだけpigpioを読み込む。
    pigpio = importlib.import_module("pigpio")

    pi = pigpio.pi()
    if not pi.connected:
        raise RuntimeError("pigpio daemon not running (start it: sudo pigpiod)")

    pi.set_mode(GPIO_ACC, pigpio.OUTPUT)
    pi.set_mode(GPIO_STR, pigpio.OUTPUT)

    try:
        print("ESC/ステアリングを中立へ設定します。")
        set_neutral(pi)
        time.sleep(NEUTRAL_SETTLE_SECONDS)

        print(f"車両ステア角 {target_steer_deg:.4f} deg の指令を出力します。")
        set_pwm(pi, PWM_NEUTRAL_SPD, duty_percent)
        time.sleep(hold_seconds)
    finally:
        print("ESC/ステアリングを中立へ戻します。")
        try:
            set_neutral(pi)
            time.sleep(NEUTRAL_SETTLE_SECONDS)
        finally:
            pi.stop()


def make_parser():
    parser = argparse.ArgumentParser(
        description="車両ステア角[deg]をステアリングサーボPWM duty比[%]へ変換する。"
    )
    parser.add_argument(
        "angle_deg",
        type=float,
        help="目標の車両ステア角[deg]。例: 0, 9.4, -9.0",
    )
    parser.add_argument(
        "--enable-hardware",
        action="store_true",
        help="実機へPWMを出力する。指定しない場合は計算結果だけ表示する。",
    )
    parser.add_argument(
        "--hold-seconds",
        type=float,
        default=HOLD_SECONDS,
        help="実機出力時に指定角を保持する時間[s]。",
    )
    return parser


def main():
    args = make_parser().parse_args()

    target_steer_rad, duty_percent = steer_deg_to_duty_percent(args.angle_deg)
    print_command(args.angle_deg, target_steer_rad, duty_percent)

    if is_duty_out_of_range(duty_percent):
        print(
            f"安全範囲外です: {duty_percent:.6f} % "
            f"not in [{PWM_SAFE_MIN:.2f}, {PWM_SAFE_MAX:.2f}] %"
        )
        return

    if not args.enable_hardware:
        print("実車出力は無効です。--enable-hardware を付けるとPWMを出力します。")
        return

    print("実機PWM出力モードです。駆動輪を浮かせ、物理的に停止できる状態で実行してください。")
    run_hardware(args.angle_deg, duty_percent, args.hold_seconds)


if __name__ == "__main__":
    main()
