import multiprocessing
import RPi.GPIO as GPIO
from math import pi
import time


# GPIOに接続した2相エンコーダから車輪速度を推定するクラス。
# Raspberry Pi専用の RPi.GPIO を使うため、PC上での通常実行には向かない。
class SpeedObserver(object):
    @staticmethod
    def updateSpeed(
            q_speed: multiprocessing.Queue,
            A_PIN: int = 22,
            B_PIN: int = 27,
            n_teeth: int = 36,
            wheel_diameter: float = 0.06
        ):
        '''
        Add speed to queue from encoder.

        q_speed: queue of speed (m/s)
        A_PIN: pin number of encoder A
        B_PIN: pin number of encoder B
        n_teeth: number of teeth on encoder
        wheel_diameter: wheel diameter in meters
        '''
        # BCM GPIO番号でエンコーダA/B相入力を設定する。
        # 入力はプルアップ前提。5 V出力のエンコーダはGPIOへ直接接続しないこと。
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(A_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(B_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        # speed[m/s] は最後に検出したA相立ち上がり間隔から求める。
        speed = 0
        last_a_flag = 0
        last_fwd_time = 0
        last_bwd_time = 0

        while True:
            # A相とB相を読み、A相の立ち上がりで回転方向と周期を判定する。
            a_flag = GPIO.input(A_PIN)
            b_flag = GPIO.input(B_PIN)

            if a_flag and not last_a_flag:
                if not b_flag:
                    # B相がLowなら前進方向として扱う。
                    dt = time.time() - last_fwd_time
                    last_fwd_time = time.time()
                else:
                    # B相がHighなら後退方向として扱う。dtを負にして速度符号へ反映する。
                    dt = last_bwd_time - time.time()
                    last_bwd_time = time.time()
                # 1歯分の移動距離を、前回立ち上がりからの時間で割って速度[m/s]にする。
                speed = (pi * wheel_diameter / n_teeth) / dt

            last_a_flag = a_flag

            # キューが満杯なら古い速度を捨て、最新値を優先する。
            if q_speed.full():
                q_speed.get()

            # main.pyなどの制御プロセスへ速度[m/s]を渡す。
            q_speed.put(speed)


def printQueue(q: multiprocessing.Queue):
    # 速度キューの値を定期的に表示するテスト用関数。
    while True:
        print(q.get())
        time.sleep(0.1)


def main():
    # エンコーダと車輪の設定値。単位はSI単位系で、wheel_diameterは[m]。
    A_PIN = 22
    B_PIN = 27
    n_teeth = 36
    wheel_diameter = 0.06

    # 速度観測プロセスから表示プロセスへ速度を渡すキュー。
    q_speed = multiprocessing.Queue(2)

    # エンコーダ読み取りと表示を別プロセスで動かす。
    processes = [
        multiprocessing.Process(
            target=SpeedObserver.updateSpeed,
            args=(q_speed, A_PIN, B_PIN, n_teeth, wheel_diameter,)
        ),
        multiprocessing.Process(
            target=printQueue,
            args=(q_speed,)
        )
    ]

    # 速度観測と表示を開始する。
    for process in processes:
        process.start()

    try:
        # Ctrl-Cが押されるまでメインプロセスは待機する。
        while True:
            time.sleep(1e5)
    except KeyboardInterrupt:
        # 終了時は子プロセスを停止して回収する。
        for process in processes:
            process.terminate()
            process.join()
        print("\nclosed all processes")


if __name__ == "__main__":
    main()
