# gpiozero.AngularServoを使って、車両のステア角[deg]を指定するサンプル。
#
# 注意:
# - ここで指定する角度はサーボ軸角度ではなく、車両ステア角[deg]。
# - 現在の車両設定ではステアリング信号はBCM GPIO13。
#   BCM GPIO12はESC用なので、サーボ単体テストでGPIO12へ出さないこと。
# - 既定では実機へPWMを出さず、計算結果だけ表示する。
# - 実機で使う場合は sudo pigpiod を起動し、--enable-hardware を付ける。

import argparse
import importlib
import math
import time

# duty比[%]で作ったステアリング変換式。
# steer_angle_rad = DUTY_FIT_A * str_duty_percent + DUTY_FIT_B
DUTY_FIT_A = -0.186785136654
DUTY_FIT_B = 2.018473280947

# 現在のステアリング確認スクリプトに合わせる。
PWM_HZ = 70
GPIO_STR = 13

# gpiozero.AngularServoに与える仮想角度範囲[deg]。
# 実際のサーボ軸角度ではなく、既存校正式に合わせた車両ステア角の範囲。
VEHICLE_STEER_MIN_DEG = -18.0
VEHICLE_STEER_MAX_DEG = 18.0

# ESC/ステアリング確認スクリプトの安全範囲[duty %]。
PWM_SAFE_MIN = 7.50
PWM_SAFE_MAX = 13.00

# 終了時に戻す車両ステア角[deg]。
NEUTRAL_STEER_DEG = 0.0

HOLD_SECONDS = 1.0


def steer_deg_to_duty_percent(target_steer_deg):
    """車両ステア角[deg]をステアリングPWM duty比[%]へ変換する。"""
    target_steer_rad = math.radians(target_steer_deg)
    duty_percent = (target_steer_rad - DUTY_FIT_B) / DUTY_FIT_A
    return target_steer_rad, duty_percent


def duty_percent_to_pulse_width_s(duty_percent):
    """PWM duty比[%]をパルス幅[s]へ変換する。"""
    period_s = 1.0 / PWM_HZ
    return period_s * duty_percent / 100.0


def is_duty_out_of_range(duty_percent):
    """duty比[%]が安全範囲外ならTrueを返す。"""
    return duty_percent < PWM_SAFE_MIN or duty_percent > PWM_SAFE_MAX


def angular_servo_pulse_range_s():
    """AngularServoに設定する最小/最大パルス幅[s]を返す。

    gpiozero.AngularServoは min_angle -> min_pulse_width,
    max_angle -> max_pulse_width で線形変換する。

    現在の車両校正式では、正の車両ステア角ほどduty比が小さい。
    そのため、実機出力時は servo.angle = -target_steer_deg として向きを反転する。
    """
    _, duty_at_right = steer_deg_to_duty_percent(VEHICLE_STEER_MAX_DEG)
    _, duty_at_left = steer_deg_to_duty_percent(VEHICLE_STEER_MIN_DEG)
    min_pulse_width_s = duty_percent_to_pulse_width_s(duty_at_right)
    max_pulse_width_s = duty_percent_to_pulse_width_s(duty_at_left)
    return min_pulse_width_s, max_pulse_width_s


def vehicle_steer_deg_to_angular_servo_angle(target_steer_deg):
    """車両ステア角[deg]をAngularServo.angleへ渡す仮想角度[deg]へ変換する。"""
    return -target_steer_deg


def print_command(target_steer_deg):
    target_steer_rad, duty_percent = steer_deg_to_duty_percent(target_steer_deg)
    pulse_width_s = duty_percent_to_pulse_width_s(duty_percent)
    angular_servo_angle = vehicle_steer_deg_to_angular_servo_angle(target_steer_deg)
    print(f"target_vehicle_steer_deg={target_steer_deg:.4f} deg")
    print(f"target_vehicle_steer_rad={target_steer_rad:.6f} rad")
    print(f"command_duty_percent={duty_percent:.9f} %")
    print(f"equivalent_pulse_width={pulse_width_s * 1_000_000.0:.3f} us")
    print(f"angular_servo_angle={angular_servo_angle:.4f} deg")
    return duty_percent, angular_servo_angle


def validate_target(target_steer_deg, duty_percent):
    if target_steer_deg < VEHICLE_STEER_MIN_DEG or target_steer_deg > VEHICLE_STEER_MAX_DEG:
        print(
            f"校正済みのAngularServo角度範囲外です: {target_steer_deg:.4f} deg "
            f"not in [{VEHICLE_STEER_MIN_DEG:.1f}, {VEHICLE_STEER_MAX_DEG:.1f}] deg"
        )
        return False

    if is_duty_out_of_range(duty_percent):
        print(
            f"安全範囲外です: {duty_percent:.6f} % "
            f"not in [{PWM_SAFE_MIN:.2f}, {PWM_SAFE_MAX:.2f}] %"
        )
        return False

    return True


def run_hardware(target_steer_deg, angular_servo_angle, hold_seconds):
    """AngularServoでステアリングサーボへ出力する。"""
    gpiozero = importlib.import_module("gpiozero")
    pigpio_pins = importlib.import_module("gpiozero.pins.pigpio")

    min_pulse_width_s, max_pulse_width_s = angular_servo_pulse_range_s()
    frame_width_s = 1.0 / PWM_HZ

    factory = pigpio_pins.PiGPIOFactory()
    servo = gpiozero.AngularServo(
        GPIO_STR,
        min_angle=VEHICLE_STEER_MIN_DEG,
        max_angle=VEHICLE_STEER_MAX_DEG,
        min_pulse_width=min_pulse_width_s,
        max_pulse_width=max_pulse_width_s,
        frame_width=frame_width_s,
        pin_factory=factory,
    )

    try:
        print("ステアリングを中立へ設定します。")
        servo.angle = vehicle_steer_deg_to_angular_servo_angle(NEUTRAL_STEER_DEG)
        time.sleep(1.0)

        print(f"車両ステア角 {target_steer_deg:.4f} deg 相当の指令を出力します。")
        servo.angle = angular_servo_angle
        time.sleep(hold_seconds)
    finally:
        print("ステアリングを中立へ戻してdetachします。")
        try:
            servo.angle = vehicle_steer_deg_to_angular_servo_angle(NEUTRAL_STEER_DEG)
            time.sleep(1.0)
        finally:
            servo.detach()
            factory.close()


def make_parser():
    parser = argparse.ArgumentParser(
        description="gpiozero.AngularServoで車両ステア角[deg]を指定する。"
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

    duty_percent, angular_servo_angle = print_command(args.angle_deg)
    if not validate_target(args.angle_deg, duty_percent):
        return

    min_pulse_width_s, max_pulse_width_s = angular_servo_pulse_range_s()
    print(f"angular_servo_min_pulse_width={min_pulse_width_s * 1_000_000.0:.3f} us")
    print(f"angular_servo_max_pulse_width={max_pulse_width_s * 1_000_000.0:.3f} us")
    print(f"angular_servo_frame_width={1_000.0 / PWM_HZ:.3f} ms")

    if not args.enable_hardware:
        print("実車出力は無効です。--enable-hardware を付けるとPWMを出力します。")
        return

    print("実機PWM出力モードです。駆動輪を浮かせ、物理的に停止できる状態で実行してください。")
    run_hardware(args.angle_deg, angular_servo_angle, args.hold_seconds)


if __name__ == "__main__":
    main()
