# Steering identification jog.
#
# [NOTE]
# 実行前にpigpioデーモンを起動する。
# sudo pigpiod

import time

import utilities

# 実車へPWMを出す場合だけ、下のコメント行を有効にする。
# 車両が動く可能性があるため、駆動輪を浮かせて物理的に停止できる状態で使う。
USE_HARDWARE = False
# USE_HARDWARE = True

# PWM周波数[Hz]。
PWM_HZ = 70

# ステアリング中立位置のduty比[%]。
PWM_NEUTRAL_STR = 10.88

# ESCの速度中立位置のduty比[%]。同定中は常に中立固定にする。
PWM_NEUTRAL_SPD = 10.55

# PWM出力ピン。Raspberry Piのhardware PWMは12/13または18/19で使用できる。
GPIO_ACC = 12
GPIO_STR = 13

# ステアリングduty比[%]の安全範囲。
PWM_STR_SAFE_MIN = 7.50
PWM_STR_SAFE_MAX = 13.00

# キー1回あたりのステアリング調整量[duty比%]。
STEER_STEP = 0.05

# 最大実行時間[s]。
RUN_SECONDS = 60.0

# 中立信号を出してからESC/サーボが落ち着くまで待つ時間[s]。
NEUTRAL_SETTLE_SECONDS = 1.0


def clamp_steer_duty(duty_percent):
    """ステアリングduty比[%]を安全範囲内へ制限する。"""
    return max(PWM_STR_SAFE_MIN, min(PWM_STR_SAFE_MAX, duty_percent))


def duty_to_pigpio(duty_percent):
    """duty比[%]をpigpio.hardware_PWM用の0..1000000の値へ変換する。"""
    return int(duty_percent * 10000)


def duty_to_pulse_width_us(duty_percent):
    """duty比[%]をパルス幅[us]へ変換する。"""
    return duty_percent / 100.0 * 1_000_000.0 / PWM_HZ


def set_pwm(pi, spd_duty, str_duty):
    """ESCとステアリングへPWMを出力する。"""
    pi.hardware_PWM(GPIO_ACC, PWM_HZ, duty_to_pigpio(spd_duty))
    pi.hardware_PWM(GPIO_STR, PWM_HZ, duty_to_pigpio(str_duty))


def set_neutral(pi):
    """ESCとステアリングを中立へ戻す。"""
    set_pwm(pi, PWM_NEUTRAL_SPD, PWM_NEUTRAL_STR)


def print_steering_value(str_duty):
    """CSVへ転記しやすい形でステアリング指令を表示する。"""
    print(
        "str_duty_percent={:.4f}, str_pulse_us={:.1f}".format(
            str_duty,
            duty_to_pulse_width_us(str_duty),
        )
    )


def write_help():
    print(
        "a/d: steering, n: neutral, Enter: stop, auto stop after {:.1f} s".format(
            RUN_SECONDS
        )
    )


def run_hardware():
    # Raspberry Pi上で実車出力するときだけpigpioを読み込む。
    import pigpio

    pi = pigpio.pi()
    if not pi.connected:
        raise RuntimeError("pigpio daemon not running (start it: sudo pigpiod)")

    pi.set_mode(GPIO_ACC, pigpio.OUTPUT)
    pi.set_mode(GPIO_STR, pigpio.OUTPUT)

    str_ref = PWM_NEUTRAL_STR

    try:
        set_neutral(pi)
        time.sleep(NEUTRAL_SETTLE_SECONDS)
        write_help()
        print_steering_value(str_ref)

        start_time = time.monotonic()
        while True:
            if time.monotonic() - start_time >= RUN_SECONDS:
                print("time limit reached")
                break

            key = utilities.getkey()
            if key == 10:
                break
            if key == ord("a"):
                str_ref -= STEER_STEP
            if key == ord("d"):
                str_ref += STEER_STEP
            if key == ord("n"):
                str_ref = PWM_NEUTRAL_STR

            str_ref = clamp_steer_duty(str_ref)

            # ESCは常に中立固定、ステアリングだけ変更する。
            set_pwm(pi, PWM_NEUTRAL_SPD, str_ref)

            if key != 0:
                print_steering_value(str_ref)

            time.sleep(0.01)
    except KeyboardInterrupt:
        print("stop!")
    finally:
        set_neutral(pi)
        time.sleep(NEUTRAL_SETTLE_SECONDS)
        pi.stop()
        print("finish.")


def main():
    if USE_HARDWARE:
        print("Steering identification mode.")
        print("ESC is fixed at neutral. Steering only is controlled.")
        run_hardware()
    else:
        print("実車出力は無効です。USE_HARDWARE = Trueを有効にしてください。")


if __name__ == "__main__":
    main()
