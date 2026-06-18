# 自己位置推定用のクラス
# x, y, theta を推定する

import abc  # 抽象基底クラス
import math


class Localizer(abc.ABC):
    """自己位置推定クラスの共通インターフェース"""

    @abc.abstractmethod
    def update(self, delta_s, steering_angle):
        # 移動距離とステアリング角から姿勢を更新
        pass  # 何もしない

    @abc.abstractmethod
    def get_pose(self):
        # 現在の姿勢 x, y, theta を返す
        pass


class DeadReckoningLocalizer(Localizer):
    """エンコーダとステアリング角による自己位置推定"""

    def __init__(self, wheelbase, x0=0.0, y0=0.0, theta0=0.0):
        self.L = wheelbase  # ホイールベース[m]
        self.x = x0  # 初期x座標[m]
        self.y = y0  # 初期y座標[m]
        self.theta = theta0  # 初期姿勢角[rad]

    def update(self, delta_s, steering_angle):
        # 移動していなければ更新しない
        if delta_s == 0.0:
            return

        # 自転車モデルで向きを更新
        self.theta += (delta_s / self.L) * math.tan(steering_angle)

        # 角度を -pi ～ pi に正規化
        self.theta = math.atan2(math.sin(self.theta), math.cos(self.theta))

        # 現在の向きに沿ってx, yを更新
        self.x += delta_s * math.cos(self.theta)
        self.y += delta_s * math.sin(self.theta)

    def get_pose(self):
        # 現在の推定姿勢を返す
        return (self.x, self.y, self.theta)


# 将来的に使っていくかもしれない
class LidarMCLLocalizer(Localizer):
    """LiDARと地図を使う自己位置推定用クラス"""

    def __init__(self, *args, **kwargs):
        # まだ未実装
        raise NotImplementedError(
            "LiDAR-MCL is a planned extension; see ellipse_run/PLAN/README."
        )

    def update(self, delta_s, steering_angle):
        # 未実装
        raise NotImplementedError

    def get_pose(self):
        # 未実装
        raise NotImplementedError
