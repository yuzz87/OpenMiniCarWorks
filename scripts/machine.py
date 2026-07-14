import select
import sys
import termios
import time
import tty

# このスクリプトはRaspberry Pi上で実車へPWMを出す。
# ESC duty比[%]は下の定数で指定する。

# 実車へ出力するESC duty比[%]。
TARGET_DUTY_PERCENT = 10.114  # 9.997, 9.879, 9.794, 9.715

# 実車へPWMを出す場合だけ、下のコメント行を有効にする。
# 車両が動く可能性があるため、駆動輪を浮かせて物理的に停止できる状態で使う。
USE_HARDWARE = False
# USE_HARDWARE = True

# PWM周波数[Hz]。
# 70 Hzでは1周期が約14.3 msになる。
PWM_HZ = 70

# ステアリング中立位置のduty比[%]。
# 実車が直進する値に合わせて校正する。
PWM_NEUTRAL_STR = 10.88

# ESCの速度中立位置のduty比[%]。
# モーターが前進も後退もしない値に合わせて校正する。
PWM_NEUTRAL_SPD = 10.55

# PWM出力ピン。Raspberry Piのhardware PWMは12/13または18/19で使用できる。
GPIO_ACC = 12
GPIO_STR = 13

# 安全のため、ESCへ出してよいduty比[%]をこの範囲に限定する。
PWM_SAFE_MIN = 9.50
PWM_SAFE_MAX = 13.00

# 中立信号を出してからESC/サーボが落ち着くまで待つ時間[s]。
NEUTRAL_SETTLE_SECONDS = 1.0

# キー入力を確認する周期[s]。
KEY_POLL_SECONDS = 0.05


def duty_to_pigpio(duty_percent):
    """duty比[%]をpigpio.hardware_PWM用の0..1000000の値へ変換する。"""
    return int(duty_percent * 10000)


def is_duty_out_of_range(duty_percent):
    """duty比[%]が安全範囲外ならTrueを返す。"""
    return duty_percent < PWM_SAFE_MIN or duty_percent > PWM_SAFE_MAX


def wait_for_key(valid_keys):
    """valid_keysのいずれかが押されるまで待つ。"""
    if not sys.stdin.isatty():
        raise RuntimeError("keyboard input requires an interactive terminal")

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        while True:
            readable, _, _ = select.select([sys.stdin], [], [], KEY_POLL_SECONDS)
            if readable:
                key = sys.stdin.read(1).lower()
                if key in valid_keys:
                    return key
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def set_neutral(pi):
    """ESCとステアリングを中立duty比[%]へ戻す。"""
    pi.hardware_PWM(GPIO_ACC, PWM_HZ, duty_to_pigpio(PWM_NEUTRAL_SPD))
    pi.hardware_PWM(GPIO_STR, PWM_HZ, duty_to_pigpio(PWM_NEUTRAL_STR))


def run_hardware(duty_percent):
    """入力されたESC duty比[%]を実車へPWM出力する。"""
    print(f"{duty_percent:.3f}")
    if is_duty_out_of_range(duty_percent):
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

        print("wキーで発進、nキーで停止します。")
        key = wait_for_key({"w", "n"})
        if key == "n":
            return

        print(f"ESC duty比: {duty_percent:.3f} %")
        pi.hardware_PWM(GPIO_ACC, PWM_HZ, duty_to_pigpio(duty_percent))
        pi.hardware_PWM(GPIO_STR, PWM_HZ, duty_to_pigpio(PWM_NEUTRAL_STR))

        print("走行中です。nキーで停止します。")
        wait_for_key({"n"})
    finally:
        # 例外やCtrl-Cで抜けた場合でも、最後に必ず中立を出してから終了する。
        print("ESC/ステアリングを中立へ戻します。")
        try:
            set_neutral(pi)
            time.sleep(NEUTRAL_SETTLE_SECONDS)
        finally:
            pi.stop()


def main():
    """USE_HARDWAREがTrueの場合だけ実車へPWM出力する。"""
    if USE_HARDWARE:
        print(
            "実機PWM出力モードです。駆動輪を浮かせ、物理的に停止できる状態で実行してください。"
        )
        run_hardware(TARGET_DUTY_PERCENT)
    else:
        print()
        print(
            "実車出力は無効です。実車へ出力するにはmachine.pyのUSE_HARDWARE = Trueを有効にしてください。"
        )


if __name__ == "__main__":
    main()
