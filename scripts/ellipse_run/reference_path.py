# 楕円などの基準経路を生成・管理するクラス

import csv
import math

import numpy as np


class ReferencePath:
    """順番に並んだ閉じた2次元経路"""

    def __init__(self, points):
        # 経路点を小数型のNumPy配列に変換
        self.points = np.asarray(points, dtype=float)

        # (N, 2)形式かつ3点以上か確認
        if self.points.ndim != 2 or self.points.shape[1] != 2 or len(self.points) < 3:
            raise ValueError("points must be an (N>=3, 2) array of (x, y)")

        # 隣り合う経路点の座標差
        diffs = np.diff(self.points, axis=0)

        # 各区間の長さ
        seg = np.hypot(diffs[:, 0], diffs[:, 1])

        # 開始点から各点までの累積距離
        self.s = np.concatenate([[0.0], np.cumsum(seg)])

        # 経路全体の長さ
        self.length = float(self.s[-1])

        # 各経路点の符号付き曲率
        self.kappa = self._compute_signed_curvature()

    @classmethod
    def ellipse(cls, a, b, cx=0.0, cy=0.0, n=720, start_deg=0.0):
        """楕円形の経路を生成する"""

        # 0～360度までの角度を生成
        phi = np.linspace(0.0, 2.0 * np.pi, n, endpoint=True) + math.radians(start_deg)

        # 楕円上のX座標とY座標
        x = cx + a * np.cos(phi)
        y = cy + b * np.sin(phi)

        # X座標とY座標を組み合わせて経路を作成
        return cls(np.column_stack([x, y]))

    @classmethod
    def from_csv(cls, path):
        """CSVファイルから経路を読み込む"""

        pts = []

        with open(path, newline="") as f:
            reader = csv.reader(f)

            # ヘッダーを読み飛ばす
            header = next(reader, None)

            for row in reader:
                # 空行は無視
                if not row:
                    continue

                # X座標とY座標を追加
                pts.append((float(row[0]), float(row[1])))

        return cls(pts)

    def to_csv(self, path):
        """経路をCSVファイルへ保存する"""

        with open(path, "w", newline="") as f:
            writer = csv.writer(f)

            # ヘッダーと経路点を書き込む
            writer.writerow(["x", "y"])
            writer.writerows(self.points)

    def nearest_index(self, x, y):
        """現在位置に最も近い経路点の番号を返す"""

        # 各経路点までの距離の2乗
        d2 = (self.points[:, 0] - x) ** 2 + (self.points[:, 1] - y) ** 2

        # 距離が最小となる点の番号
        return int(np.argmin(d2))

    def lookahead_point(self, x, y, lookahead):
        """現在位置から前方の目標点を返す"""

        # 現在位置に最も近い経路点
        i0 = self.nearest_index(x, y)

        # 前方注視点の累積距離
        target_s = (self.s[i0] + lookahead) % self.length

        # 累積距離に対応する経路点を検索
        idx = int(np.searchsorted(self.s, target_s))

        # 経路末尾を越えたら先頭へ戻る
        if idx >= len(self.points):
            idx = 0

        return (float(self.points[idx, 0]), float(self.points[idx, 1]))

    def signed_curvature_at_s(self, s):
        """指定した累積距離の符号付き曲率を返す"""

        return float(np.interp(s % self.length, self.s, self.kappa))

    def min_radius(self):
        """経路内の最小旋回半径を返す"""

        # 経路内で最大となる曲率
        max_curv = float(np.max(np.abs(self.kappa)))

        # 旋回半径は曲率の逆数
        return 1.0 / max_curv if max_curv > 0 else math.inf

    def _compute_signed_curvature(self):
        """各経路点の符号付き曲率を計算する"""

        p = self.points
        n = len(p)

        # 曲率を0で初期化
        kappa = np.zeros(n)

        for i in range(n):
            # 現在点と前後の点
            a = p[(i - 1) % n]
            b = p[i]
            c = p[(i + 1) % n]

            # 3点間の距離
            ab = math.hypot(b[0] - a[0], b[1] - a[1])
            bc = math.hypot(c[0] - b[0], c[1] - b[1])
            ca = math.hypot(a[0] - c[0], a[1] - c[1])

            denom = ab * bc * ca

            # 重複点や直線に近い点は計算しない
            if denom < 1e-9:
                continue

            # 外積から左右の曲がり方向を判定
            cross2 = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

            # メンガー曲率を計算
            # 正：左カーブ、負：右カーブ
            kappa[i] = 2.0 * cross2 / denom

        return kappa
