# Pure Pursuitによる経路追従
# 前方注視点に向かうステアリング角を計算する

import math


class PurePursuit:
    def __init__(self, wheelbase, lookahead, max_steer=math.radians(30.0)):
        self.L = wheelbase  # ホイールベース[m]
        self.lookahead = lookahead  # 前方注視距離[m]
        self.max_steer = max_steer  # 最大ステアリング角[rad]

    def compute_steering(self, pose, path):
        """現在姿勢からステアリング角を計算する"""

        # 現在位置と車体角度
        x, y, theta = pose

        # 経路上の前方注視点
        gx, gy = path.lookahead_point(x, y, self.lookahead)

        # 現在位置から目標点までの距離
        dx = gx - x
        dy = gy - y

        # 目標点を車体座標系に変換
        # X方向が前、Y方向が左
        cos_t = math.cos(-theta)
        sin_t = math.sin(-theta)

        x_v = cos_t * dx - sin_t * dy
        y_v = sin_t * dx + cos_t * dy

        # 目標点までの直線距離
        ld = math.hypot(x_v, y_v)

        # 目標点が近すぎる場合は直進
        if ld < 1e-6:
            return 0.0

        # Pure Pursuitで目標曲率を計算
        curvature = 2.0 * y_v / (ld * ld)

        # 曲率からステアリング角を計算
        delta = math.atan(self.L * curvature)

        # ステアリング角を最大範囲内に制限
        return max(-self.max_steer, min(self.max_steer, delta))
