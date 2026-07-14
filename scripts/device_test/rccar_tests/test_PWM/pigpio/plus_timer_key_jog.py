# Jog operation with keyboard and pulse width display.
#
# [NOTE]
# 実行前にpigpioデーモンを起動する。
# sudo pigpiod

import time

import utilities

# 校正パラメータ。実車に合わせて調整する値。
DELTA_JOG = 0.145  # キー1回あたりの調整量[duty比%]

# PWM周波数[Hz]。
# RCサーボやESCへ送るPWM信号の繰り返し周波数。
PWM_HZ = 70

# ステアリング中立位置のduty比[%]。
PWM_NEUTRAL_STR = 10.88

# ESCの速度中立位置のduty比[%]。
PWM_NEUTRAL_SPD = 10.55

# 最大実行時間[s]。
RUN_SECONDS = 10.0

# PWM出力ピン。Raspberry Piのhardware PWMは12/13または18/19で使用できる。
GPIO_ACC = 12
GPIO_STR = 13

# 安全のため、ESC/サーボへ出すduty比[%]をこの範囲に制限する。
PWM_SAFE_MIN = 7.50
PWM_SAFE_MAX = 13.00


def clamp_duty(duty_percent):
    """duty比[%]を安全範囲内へ制限する。"""
    return max(PWM_SAFE_MIN, min(PWM_SAFE_MAX, duty_percent))


def duty_to_pigpio(duty_percent):
    """duty比[%]をpigpio.hardware_PWM用の0..1000000の値へ変換する。"""
    return int(clamp_duty(duty_percent) * 10000)


def duty_to_pulse_width_us(duty_percent):
    """duty比[%]をパルス幅[us]へ変換する。"""
    return clamp_duty(duty_percent) / 100.0 * 1_000_000.0 / PWM_HZ


def set_pwm(pi, spd_duty, str_duty):
    """ESCとステアリングへPWMを出力する。"""
    pi.hardware_PWM(GPIO_ACC, PWM_HZ, duty_to_pigpio(spd_duty))
    pi.hardware_PWM(GPIO_STR, PWM_HZ, duty_to_pigpio(str_duty))


def set_neutral(pi):
    """速度とステアリングを中立へ戻す。"""
    set_pwm(pi, PWM_NEUTRAL_SPD, PWM_NEUTRAL_STR)


def print_values(str_duty, spd_duty):
    """現在のduty比[%]とパルス幅[us]を表示する。"""
    str_duty = clamp_duty(str_duty)
    spd_duty = clamp_duty(spd_duty)
    print(
        "str_duty[%]={:.4f}, str_pulse_us={:.1f}, "
        "spd_duty[%]={:.4f}, spd_pulse_us={:.1f}".format(
            str_duty,
            duty_to_pulse_width_us(str_duty),
            spd_duty,
            duty_to_pulse_width_us(spd_duty),
        )
    )


def write_help():
    print(
        "Enter: stop, w/s: speed, a/d: steering, n: neutral, "
        "auto stop after {:.1f} s".format(RUN_SECONDS)
    )


def main():
    # Raspberry Pi上で実車出力するときだけpigpioを読み込む。
    import pigpio

    print("PWM Jog control with pulse width display...")

    pi = pigpio.pi()
    if not pi.connected:
        raise RuntimeError("pigpio daemon not running (start it: sudo pigpiod)")

    pi.set_mode(GPIO_ACC, pigpio.OUTPUT)
    pi.set_mode(GPIO_STR, pigpio.OUTPUT)

    spd_ref = PWM_NEUTRAL_SPD
    str_ref = PWM_NEUTRAL_STR

    try:
        set_neutral(pi)
        time.sleep(1.0)
        write_help()
        print_values(str_ref, spd_ref)

        i = 0
        start_time = time.monotonic()
        while True:
            i += 1

            if time.monotonic() - start_time >= RUN_SECONDS:
                print("time limit reached")
                break

            key = utilities.getkey()
            if key == 10:
                break
            if key == ord("w"):
                spd_ref -= DELTA_JOG * 2
            if key == ord("s"):
                spd_ref += DELTA_JOG * 2
            if key == ord("a"):
                str_ref -= DELTA_JOG * 4
            if key == ord("d"):
                str_ref += DELTA_JOG * 4
            if key == ord("n"):
                str_ref = PWM_NEUTRAL_STR
                spd_ref = PWM_NEUTRAL_SPD

            spd_ref = clamp_duty(spd_ref)
            str_ref = clamp_duty(str_ref)
            set_pwm(pi, spd_ref, str_ref)

            if key != 0:
                print_values(str_ref, spd_ref)
            if i % 20 == 0:
                print_values(str_ref, spd_ref)
            if i % 200 == 0:
                write_help()

            time.sleep(0.01)
    except KeyboardInterrupt:
        print("stop!")
    finally:
        set_neutral(pi)
        time.sleep(1.0)
        pi.stop()
        print("finish.")


if __name__ == "__main__":
    main()
