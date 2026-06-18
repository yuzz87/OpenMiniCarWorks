# ステアリング角とスロットル値をPWM信号へ変換する
# ステアリング：GPIO17、スロットル：GPIO18


def _clamp(v, lo, hi):
    """値を最小値から最大値の範囲に制限する"""
    return lo if v < lo else hi if v > hi else v


class CarDriver:
    """pigpioを使用してサーボとESCを制御する"""

    def __init__(
        self,
        steer_pin=17,
        throttle_pin=18,
        steer_neutral_us=1500,
        steer_range_us=400,
        max_steer=0.5,
        steer_sign=1,
        throttle_neutral_us=1500,
        steer_limit_us=(1100, 1900),
        throttle_limit_us=(1300, 1700),
        use_hardware=True,
    ):
        self.steer_pin = steer_pin  # ステアリングのGPIO番号
        self.throttle_pin = throttle_pin  # スロットルのGPIO番号

        # ステアリングの中立パルス幅[μs]
        self.steer_neutral_us = steer_neutral_us

        # ステアリング方向の符号
        self.steer_sign = steer_sign

        # 最大ステアリング角[rad]
        self.max_steer = max_steer

        # 1radあたりのパルス幅変化量
        self.us_per_rad = steer_range_us / max_steer if max_steer else 0.0

        # スロットルの中立パルス幅[μs]
        self.throttle_neutral_us = throttle_neutral_us

        # パルス幅の安全範囲
        self.steer_limit_us = steer_limit_us
        self.throttle_limit_us = throttle_limit_us

        # 実機を使用するか
        self.use_hardware = use_hardware

        # pigpio接続用
        self.pi = None

    def start(self):
        """pigpioへ接続して制御を開始する"""

        # PC動作確認では何もしない
        if not self.use_hardware:
            return

        # 実機でのみpigpioを読み込む
        import pigpio

        self.pi = pigpio.pi()

        # pigpioデーモンとの接続を確認
        if not self.pi.connected:
            raise RuntimeError("pigpio daemon not running (start it: sudo pigpiod)")

        # ステアリングとスロットルを中立にする
        self.neutral()

    def steering_to_us(self, angle_rad):
        """ステアリング角をパルス幅へ変換する"""

        # ステアリング角を制限
        angle = _clamp(angle_rad, -self.max_steer, self.max_steer)

        # 角度からパルス幅を計算
        us = self.steer_neutral_us + self.steer_sign * angle * self.us_per_rad

        # パルス幅を安全範囲内に制限
        return _clamp(us, self.steer_limit_us[0], self.steer_limit_us[1])

    def set_steering(self, angle_rad):
        """ステアリング角をサーボへ出力する"""

        us = self.steering_to_us(angle_rad)
        self._servo(self.steer_pin, us)

    def set_throttle_us(self, throttle_us):
        """スロットルのパルス幅をESCへ出力する"""

        # パルス幅を安全範囲内に制限
        us = _clamp(throttle_us, self.throttle_limit_us[0], self.throttle_limit_us[1])

        self._servo(self.throttle_pin, us)

    def drive(self, steering_angle, throttle_us):
        """ステアリングとスロットルを同時に設定する"""

        self.set_steering(steering_angle)
        self.set_throttle_us(throttle_us)

    def neutral(self):
        """ステアリングとスロットルを中立にする"""

        self._servo(self.steer_pin, self.steer_neutral_us)
        self._servo(self.throttle_pin, self.throttle_neutral_us)

    def stop(self):
        """車両を中立状態にして停止する"""

        # ESCへ中立信号を送り続ける
        self.neutral()

    def _servo(self, pin, us):
        """指定GPIOへサーボ用パルスを出力する"""

        # 実機接続時のみ信号を出力
        if self.use_hardware and self.pi is not None:
            self.pi.set_servo_pulsewidth(pin, int(us))
