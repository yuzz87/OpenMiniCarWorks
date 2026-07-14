import time

import pigpio

# Raspberry Pi上でpigpioを使い、サーボ/ESCへ直接パルス幅を出す走行デモ。
# 実行すると車両が動く可能性があるため、駆動輪を浮かせ、物理的に電源を切れる状態で使う。
# sudo pigpiod
# python3 demo.py
# ステアリングサーボとESCの信号GPIO番号。ここではBCM GPIO番号を使う。
STEER_PIN = 13
THROTTLE_PIN = 12

# サーボ/ESCの中立パルス幅[us]。
STEER_NEUTRAL_US = 1555.7
THROTTLE_NEUTRAL_US = 1507.1

# pigpioデーモンへ接続する。実行前に sudo pigpiod が必要。
pi = pigpio.pi()
if not pi.connected:
    raise RuntimeError("pigpio daemon not running (start it: sudo pigpiod)")

# デモ走行で中立からずらすパルス幅[us]。
# accelはスロットル、steerはステアリングのオフセットとして使う。
accel = 50  # 実測値のわけではない->中立値からどのくらいずらすかの値
steer = 200  # 実測値のわけではない->中立値からどのくらいずらすかの値
FORWARD_SECONDS = 3.0


def neuteral():
    # ステアリングとスロットルを中立へ戻す。
    pi.set_servo_pulsewidth(STEER_PIN, STEER_NEUTRAL_US)  # ピン番号, パルス幅_us
    pi.set_servo_pulsewidth(THROTTLE_PIN, THROTTLE_NEUTRAL_US)


def circle():
    # 一定ステアリング・一定スロットルを出し続け、円弧走行を試すデモ。
    print("circle")
    try:
        while True:
            # ステアリングを片側へ切り、ESCへ前進側のパルス幅を出す。
            pi.set_servo_pulsewidth(STEER_PIN, STEER_NEUTRAL_US + steer)
            pi.set_servo_pulsewidth(THROTTLE_PIN, THROTTLE_NEUTRAL_US - accel)
    except KeyboardInterrupt:
        # Ctrl-C時は必ず中立へ戻す。
        neuteral()


def forward_three_seconds():
    # 3秒だけ前進して、中立へ戻して終了するデモ。
    print("forward three seconds")
    try:
        pi.set_servo_pulsewidth(STEER_PIN, STEER_NEUTRAL_US)
        pi.set_servo_pulsewidth(THROTTLE_PIN, THROTTLE_NEUTRAL_US - accel)
        time.sleep(FORWARD_SECONDS)
    except KeyboardInterrupt:
        # 中断時もスロットルを中立へ戻す。
        print("stop!")
    finally:
        neuteral()


def zigzag():
    # 前進しながら左右へステアリングを切り替えるデモ。
    zigzag
    print("zigzag")
    count = 0
    wait_time = 1
    try:
        for i in range(3):
            print(count)
            pi.set_servo_pulsewidth(THROTTLE_PIN, THROTTLE_NEUTRAL_US - accel)
            # 左右の向きは実車のサーボ取り付け方向に依存する。
            pi.set_servo_pulsewidth(STEER_PIN, STEER_NEUTRAL_US + steer)
            time.sleep(wait_time)
            pi.set_servo_pulsewidth(STEER_PIN, STEER_NEUTRAL_US - steer)
            time.sleep(wait_time)
            count += 1
        neuteral()
    except KeyboardInterrupt:
        # 中断時はステアリングとスロットルを中立へ戻す。
        neuteral()


def run():
    # 起動直後は中立にする。実際のデモ関数は必要に応じてコメントを外して呼び出す。
    neuteral()
    # circle()
    # forward_three_seconds()
    # zigzag()


if __name__ == "__main__":
    run()
