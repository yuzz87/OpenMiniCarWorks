# ステアリング変換式を実車で確認する。
#
# 目標ステア角[deg]からステアリングduty比[%]を直接計算する。
# ESCは中立固定で、ステアリングだけを動かす。

import math
import time

import utilities

# 実車へPWMを出す場合だけ、下のコメント行を有効にする。
# 車両が動く可能性があるため、駆動輪を浮かせて物理的に停止できる状態で使う。
USE_HARDWARE = False
# USE_HARDWARE = True

# 確認する目標ステア角[deg]。1個ずつ確認する。
TARGET_STEER_DEG_LIST = [18.0, 9.4, 0.0, -9.0, -18.0]

# 中立専用モードで出力するステアリングduty比[%]。
NEUTRAL_DUTY_PERCENT = 10.895

# duty比[%]で作ったステアリング変換式。
# steer_angle_rad = DUTY_FIT_A * str_duty_percent + DUTY_FIT_B
DUTY_FIT_A = -0.186785136654
DUTY_FIT_B = 2.018473280947

# PWM周波数[Hz]。
PWM_HZ = 70

# ステアリング中立位置のduty比[%]。
PWM_NEUTRAL_STR = NEUTRAL_DUTY_PERCENT

# ESCの速度中立位置のduty比[%]。
PWM_NEUTRAL_SPD = 10.55

# PWM出力ピン。Raspberry Piのhardware PWMは12/13または18/19で使用できる。
GPIO_ACC = 12
GPIO_STR = 13

# 安全のため、ステアリングへ出してよいduty比[%]をこの範囲に限定する。
PWM_SAFE_MIN = 7.50
PWM_SAFE_MAX = 13.00

# 中立信号を出してからESC/サーボが落ち着くまで待つ時間[s]。
NEUTRAL_SETTLE_SECONDS = 1.0


def coefficients_are_set():
    """変換係数が設定済みならTrueを返す。"""
    return DUTY_FIT_A is not None and DUTY_FIT_B is not None


def steer_rad_to_duty_percent(target_steer_rad):
    """目標ステア角[rad]をステアリングduty比[%]へ変換する。"""
    if not coefficients_are_set():
        raise RuntimeError("DUTY_FIT_A and DUTY_FIT_B must be set")
    return (target_steer_rad - DUTY_FIT_B) / DUTY_FIT_A


def steer_deg_to_duty_percent(target_steer_deg):
    """目標ステア角[deg]をステアリングduty比[%]へ変換する。"""
    target_steer_rad = math.radians(target_steer_deg)
    duty_percent = steer_rad_to_duty_percent(target_steer_rad)
    return target_steer_rad, duty_percent


def duty_to_pigpio(duty_percent):
    """duty比[%]をpigpio.hardware_PWM用の0..1000000の値へ変換する。"""
    return int(round(duty_percent * 10000))


def is_duty_out_of_range(duty_percent):
    """duty比[%]が安全範囲外ならTrueを返す。"""
    return duty_percent < PWM_SAFE_MIN or duty_percent > PWM_SAFE_MAX


def set_pwm(pi, spd_duty, str_duty):
    """ESCとステアリングへPWMを出力する。"""
    pi.hardware_PWM(GPIO_ACC, PWM_HZ, duty_to_pigpio(spd_duty))
    pi.hardware_PWM(GPIO_STR, PWM_HZ, duty_to_pigpio(str_duty))


def set_neutral(pi):
    """ESCとステアリングを中立へ戻す。"""
    set_pwm(pi, PWM_NEUTRAL_SPD, PWM_NEUTRAL_STR)


def make_commands(target_steer_deg_list):
    """確認対象の角度[deg]をduty比[%]へ変換する。"""
    commands = []
    for target_steer_deg in target_steer_deg_list:
        target_steer_rad, duty_percent = steer_deg_to_duty_percent(target_steer_deg)
        commands.append((target_steer_deg, target_steer_rad, duty_percent))
    return commands


def print_command(index, total, target_steer_deg, target_steer_rad, duty_percent):
    """実車へ出す予定の指令値を表示する。"""
    print(f"[{index}/{total}]")
    print(f"target_steer_deg={target_steer_deg:.4f}")
    print(f"target_steer_rad={target_steer_rad:.6f}")
    print(f"command_duty_percent={duty_percent:.9f}")


def validate_commands(commands):
    """安全範囲外のduty比[%]がないか事前確認する。"""
    unsafe_commands = []
    for target_steer_deg, _, duty_percent in commands:
        if is_duty_out_of_range(duty_percent):
            unsafe_commands.append((target_steer_deg, duty_percent))

    if unsafe_commands:
        for target_steer_deg, duty_percent in unsafe_commands:
            print(f"{target_steer_deg:.4f} deg -> {duty_percent:.4f} %")
        return False
    return True


def run_hardware(commands):
    """ステアリングへ各duty比[%]を1個ずつ出力し、ESCは中立のままにする。"""
    if not validate_commands(commands):
        return

    # Raspberry Pi上で実車出力するときだけpigpioを読み込む。
    import pigpio

    pi = pigpio.pi()
    if not pi.connected:
        raise RuntimeError("pigpio daemon not running (start it: sudo pigpiod)")

    pi.set_mode(GPIO_ACC, pigpio.OUTPUT)
    pi.set_mode(GPIO_STR, pigpio.OUTPUT)

    try:
        print("ESC/ステアリングを中立へ設定します。")
        set_neutral(pi)
        time.sleep(NEUTRAL_SETTLE_SECONDS)

        print("w: 指令出力, n: 中立, Enter: 次へ, q: 終了")
        total = len(commands)
        for index, command in enumerate(commands, start=1):
            target_steer_deg, target_steer_rad, duty_percent = command
            print_command(
                index,
                total,
                target_steer_deg,
                target_steer_rad,
                duty_percent,
            )
            while True:
                key = utilities.getkey()
                if key == ord("w"):
                    set_pwm(pi, PWM_NEUTRAL_SPD, duty_percent)
                    print(f"str_duty[%]={duty_percent:.9f}")
                if key == ord("n"):
                    set_neutral(pi)
                    print("neutral")
                if key == 10:
                    set_neutral(pi)
                    break
                if key == ord("q"):
                    return
                time.sleep(0.01)
    finally:
        print("ESC/ステアリングを中立へ戻します。")
        try:
            set_neutral(pi)
            time.sleep(NEUTRAL_SETTLE_SECONDS)
        finally:
            pi.stop()


def main():
    if not coefficients_are_set():
        print("DUTY_FIT_A と DUTY_FIT_B を設定してください。")
        return

    commands = make_commands(TARGET_STEER_DEG_LIST)
    total = len(commands)
    for index, command in enumerate(commands, start=1):
        print_command(index, total, *command)
        print()

    if USE_HARDWARE:
        print(
            "実機PWM出力モードです。駆動輪を浮かせ、物理的に停止できる状態で実行してください。"
        )
        run_hardware(commands)
    else:
        print("実車出力は無効です。USE_HARDWARE = Trueを有効にすると出力します。")


if __name__ == "__main__":
    main()
