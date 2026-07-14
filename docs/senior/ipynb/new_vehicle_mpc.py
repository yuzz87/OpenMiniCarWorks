"""新しい実機向けのMPC補助コード。

先輩のNotebookは変更せず、新しい実機向けの変更をこのファイルへ追加する。
このファイルにはUDP通信、GPIO、PWM出力を含めない。
角度はラジアン、距離はメートルで扱う。
"""

from __future__ import annotations

import numpy as np

STATE_DIM = 4


def make_reference_traj(
    t_eval: np.ndarray,
    v_ref: float = 0.4,
    goal_dist: float = 4.0,
    x0: float = 0.0,
    y0: float = -2.0,
    phi0: float = 0.0,
) -> np.ndarray:
    """初期姿勢から車体前方へ進む直線参照を作る。

    状態の順序は ``[phi, x, y, psi]``。

    - ``phi``: 車体方位 [rad]
    - ``x``, ``y``: 位置 [m]
    - ``psi``: 前輪舵角 [rad]

    戻り値の形状は ``(4, len(t_eval))``。

    ``v_ref``、``goal_dist``、``x0``、``y0``の既定値は先輩コードとの
    互換用であり、新しい実機用として確定した値ではない。
    """
    times = np.asarray(t_eval, dtype=float)
    if times.ndim != 1:
        raise ValueError("t_evalは1次元配列にしてください")
    if times.size == 0:
        raise ValueError("t_evalを空にすることはできません")
    if not np.all(np.isfinite(times)) or np.any(times < 0.0):
        raise ValueError("t_evalには有限かつ0秒以上の時刻を指定してください")

    parameters = np.asarray([v_ref, goal_dist, x0, y0, phi0], dtype=float)
    if not np.all(np.isfinite(parameters)):
        raise ValueError("参照軌道の設定値は有限値にしてください")
    if v_ref < 0.0:
        raise ValueError("v_refは0 m/s以上にしてください")
    if goal_dist < 0.0:
        raise ValueError("goal_distは0 m以上にしてください")

    distance = np.minimum(v_ref * times, goal_dist)

    reference = np.zeros((STATE_DIM, times.size), dtype=float)
    reference[0, :] = phi0
    reference[1, :] = x0 + distance * np.cos(phi0)
    reference[2, :] = y0 + distance * np.sin(phi0)
    reference[3, :] = 0.0
    return reference
