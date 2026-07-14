# pigpio daemon connection check.
#
# Raspberry Pi上でpigpioデーモンに接続できるか確認する。
# sudo systemctl start pigpiod
# python3 pigpio_connection_check.py

import time


# GPIOへ実際に中立パルスを出して信号確認する場合だけTrueにする。
# オシロスコープやロジックアナライザで確認するときに使う。
# 車両が動く可能性があるため、通常はFalseのままにする。
USE_GPIO_OUTPUT_TEST = False

# 出力確認に使うBCM GPIO番号。
# 物理ピン対応:
# BCM GPIO12 -> physical pin 32
# BCM GPIO13 -> physical pin 33
# BCM GPIO17 -> physical pin 11
# BCM GPIO18 -> physical pin 12
TEST_GPIO = 13

# サーボ/ESCの中立確認用パルス幅[us]。
TEST_PULSE_US = 1500

# 中立パルスを出す時間[s]。
TEST_SECONDS = 3.0


def check_pigpio_connection(pi):
    """pigpioデーモンへ接続できているか確認する。"""
    if not pi.connected:
        print("NG: pigpio daemonへ接続できません。")
        print("次を実行してください: sudo systemctl start pigpiod")
        return False

    tick = pi.get_current_tick()
    print("OK: pigpio daemonへ接続できました。")
    print(f"current_tick={tick}")
    return True


def run_gpio_output_test(pi):
    """指定GPIOへ中立パルスを短時間出す。"""
    print(
        f"GPIO出力テスト: BCM GPIO{TEST_GPIO} に {TEST_PULSE_US} us を "
        f"{TEST_SECONDS:.1f} s 出力します。"
    )
    pi.set_mode(TEST_GPIO, 1)
    pi.set_servo_pulsewidth(TEST_GPIO, TEST_PULSE_US)
    time.sleep(TEST_SECONDS)
    pi.set_servo_pulsewidth(TEST_GPIO, 0)
    print("GPIO出力テストを終了しました。")


def main():
    # Raspberry Pi上で確認するときだけpigpioを読み込む。
    import pigpio

    pi = pigpio.pi()
    try:
        if not check_pigpio_connection(pi):
            return

        if USE_GPIO_OUTPUT_TEST:
            run_gpio_output_test(pi)
        else:
            print("GPIO出力テストは無効です。USE_GPIO_OUTPUT_TEST = True で有効化します。")
    finally:
        pi.stop()


if __name__ == "__main__":
    main()
