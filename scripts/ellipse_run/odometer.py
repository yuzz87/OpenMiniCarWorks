# 光学式タイヤエンコーダ用オドメータ
# A相・B相、1回転36パルス

import math


class Odometer:
    """実機用の累積移動距離計測クラス"""

    def __init__(self, a_pin=22, b_pin=27, n_teeth=36, wheel_diameter=0.066):
        self.a_pin = a_pin  # A相のGPIO番号
        self.b_pin = b_pin  # B相のGPIO番号
        self.n_teeth = n_teeth  # 1回転あたりのパルス数
        self.wheel_diameter = wheel_diameter  # タイヤ直径[m]

        # 1パルスあたりの移動距離[m]
        self.dist_per_tick = math.pi * wheel_diameter / n_teeth

        self._ticks = 0  # 符号付き累積パルス数
        self._gpio = None  # GPIO操作用

    def start(self):
        # 実機でのみRPi.GPIOを読み込む
        import RPi.GPIO as GPIO

        self._gpio = GPIO  # Odometerオブジェクトに保存

        # GPIO番号をBCM方式で指定
        GPIO.setmode(GPIO.BCM)

        # A相・B相をプルアップ付き入力に設定
        GPIO.setup(self.a_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(self.b_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        # A相の立ち上がり時に割り込み処理を実行
        GPIO.add_event_detect(self.a_pin, GPIO.RISING, callback=self._on_a_rising)

    def _on_a_rising(self, channel):
        # A相立ち上がり時のB相から回転方向を判定
        if self._gpio.input(self.b_pin):
            self._ticks -= 1  # 後退
        else:
            self._ticks += 1  # 前進

    @property
    def distance(self):
        """符号付き累積移動距離[m]を返す"""
        return self._ticks * self.dist_per_tick

    def stop(self):
        # A相の割り込み監視を解除
        if self._gpio is not None:
            self._gpio.remove_event_detect(self.a_pin)


class SimOdometer:
    """PC動作確認用の模擬オドメータ"""

    def __init__(self):
        self._distance = 0.0  # 累積移動距離[m]

    def start(self):
        # シミュレーションでは初期化不要
        pass

    def advance(self, ds):
        # 1ステップ分の移動距離を加算
        self._distance += ds

    @property
    def distance(self):
        # 累積移動距離[m]を返す
        return self._distance

    def stop(self):
        # シミュレーションでは終了処理不要
        pass
