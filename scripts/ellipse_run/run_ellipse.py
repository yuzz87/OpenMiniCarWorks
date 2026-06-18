# エンコーダのデッドレコニングで楕円経路を走行する
#
# 処理の流れ：
# オドメータ → 自己位置推定 → 基準経路 → 制御器 → 車両制御

import math
import time

from car_driver import CarDriver
from localizer import DeadReckoningLocalizer
from odometer import Odometer, SimOdometer
from pure_pursuit import PurePursuit
from reference_path import ReferencePath

### 設定項目 ###

# True：実機、False：PCシミュレーション
use_hardware = False  # False, True

# pursuit：Pure Pursuit、feedforward：曲率による制御
control_mode = "pursuit"

# 車両寸法
WHEELBASE = 0.25  # ホイールベース[m]
WHEEL_DIAMETER = 0.066  # タイヤ直径[m]
N_TEETH = 36  # エンコーダの歯数
MAX_STEER_DEG = 28.0  # 最大ステアリング角[度]

# 楕円経路
ELLIPSE_A = 2.0  # X方向の半径[m]
ELLIPSE_B = 1.2  # Y方向の半径[m]
TARGET_SPEED = 0.4  # 目標速度[m/s]
N_LAPS = 1  # 周回数

# Pure Pursuitの前方注視距離
LOOKAHEAD = 0.6

# エンコーダのGPIO番号
ENC_A_PIN = 22
ENC_B_PIN = 27

# サーボとESCの設定
STEER_PIN = 17
THROTTLE_PIN = 18
STEER_NEUTRAL_US = 1500  # ステアリング中立値
STEER_RANGE_US = 400  # 最大操舵時の変化量
STEER_SIGN = 1  # 左右が逆なら-1
THROTTLE_NEUTRAL_US = 1500
THROTTLE_DRIVE_US = 1440  # 前進時のESC信号
ARM_SECONDS = 1.0  # ESC起動待ち時間[s]

# 制御周期と出力ファイル
CONTROL_HZ = 50
LOG_CSV = "pose_log.csv"
PLOT_PNG = "ellipse_track.png"


def build_path():
    """楕円経路を生成して旋回可能か確認する"""

    # 開始位置と車体方向に合わせた楕円を生成
    path = ReferencePath.ellipse(a=ELLIPSE_A, b=ELLIPSE_B, cx=0.0, cy=ELLIPSE_B)

    # 経路に必要な最小旋回半径
    rmin_needed = path.min_radius()

    # 車両が実現できる最小旋回半径
    car_rmin = WHEELBASE / math.tan(math.radians(MAX_STEER_DEG))

    print(f"path length      : {path.length:.2f} m")
    print(f"path min radius  : {rmin_needed:.2f} m")
    print(
        f"car  min radius  : {car_rmin:.2f} m "
        f"(wheelbase {WHEELBASE} m, "
        f"max steer {MAX_STEER_DEG} deg)"
    )

    # 車両が曲がれない経路の場合は警告
    if rmin_needed < car_rmin:
        print(
            "WARNING: ellipse is tighter than the car can turn. "
            "Increase ELLIPSE_B or reduce eccentricity."
        )

    return path


def main():
    """走行制御のメイン処理"""

    # 基準経路を生成
    path = build_path()

    # 最大ステアリング角をradへ変換
    max_steer = math.radians(MAX_STEER_DEG)

    # 自己位置推定器を作成
    localizer = DeadReckoningLocalizer(wheelbase=WHEELBASE)

    # Pure Pursuit制御器を作成
    controller = PurePursuit(WHEELBASE, LOOKAHEAD, max_steer=max_steer)

    # 車両ドライバを作成
    driver = CarDriver(
        steer_pin=STEER_PIN,
        throttle_pin=THROTTLE_PIN,
        steer_neutral_us=STEER_NEUTRAL_US,
        steer_range_us=STEER_RANGE_US,
        max_steer=max_steer,
        steer_sign=STEER_SIGN,
        throttle_neutral_us=THROTTLE_NEUTRAL_US,
        use_hardware=use_hardware,
    )

    # 実機とシミュレーションでオドメータを切り替える
    if use_hardware:
        odo = Odometer(ENC_A_PIN, ENC_B_PIN, N_TEETH, WHEEL_DIAMETER)
    else:
        odo = SimOdometer()

    # オドメータと車両制御を開始
    odo.start()
    driver.start()

    # ESC起動のため中立信号を送る
    driver.neutral()
    time.sleep(ARM_SECONDS)

    # 目標走行距離
    goal_distance = N_LAPS * path.length

    # 1周期の目標時間
    dt_target = 1.0 / CONTROL_HZ

    # 前回出力したステアリング角
    delta = 0.0

    # 前回の累積移動距離
    prev_dist = odo.distance

    # 前回の処理時刻
    t_prev = time.time()

    # 走行ログ
    log = []

    print(
        f"start: {control_mode}, target {goal_distance:.2f} m "
        f"({N_LAPS} lap(s)) -- Ctrl-C to stop"
    )

    try:
        while True:
            # 制御周期を一定にする
            now = time.time()
            dt = now - t_prev

            if dt < dt_target:
                time.sleep(dt_target - dt)
                now = time.time()
                dt = now - t_prev

            t_prev = now

            # PCシミュレーションでは移動距離を追加
            if not use_hardware:
                odo.advance(TARGET_SPEED * dt)

            # 前回からの移動距離を計算
            dist = odo.distance
            ds = dist - prev_dist
            prev_dist = dist

            # 移動距離と前回の操舵角から姿勢を更新
            localizer.update(ds, delta)
            pose = localizer.get_pose()

            # 目標距離に到達したら終了
            traveled = abs(dist)

            if traveled >= goal_distance:
                break

            # ステアリング角を計算
            if control_mode == "feedforward":
                # 経路の曲率から操舵角を計算
                kappa = path.signed_curvature_at_s(traveled)
                delta = math.atan(WHEELBASE * kappa)

                # 最大ステアリング角に制限
                delta = max(-max_steer, min(max_steer, delta))
            else:
                # Pure Pursuitで操舵角を計算
                delta = controller.compute_steering(pose, path)

            # ステアリングとスロットルを出力
            driver.drive(delta, THROTTLE_DRIVE_US)

            # 時刻、位置、向き、操舵角を記録
            log.append((now, pose[0], pose[1], pose[2], delta))

    except KeyboardInterrupt:
        # Ctrl+Cが押された場合
        print("\ninterrupted")

    finally:
        # 必ず車両を停止する
        driver.stop()
        odo.stop()

        # pigpioとの接続を終了
        if use_hardware and driver.pi is not None:
            driver.pi.stop()

        print(f"done: {len(log)} steps, traveled {abs(odo.distance):.2f} m")

        # ログと走行軌跡を保存
        save_log(log)
        plot_track(path, log)


def save_log(log):
    """走行ログをCSVへ保存する"""

    import csv

    with open(LOG_CSV, "w", newline="") as f:
        writer = csv.writer(f)

        # CSVの見出し
        writer.writerow(["t", "x", "y", "theta", "steer"])

        # 走行データ
        writer.writerows(log)

    print(f"log saved: {LOG_CSV}")


def plot_track(path, log):
    """基準経路と推定走行軌跡を画像へ保存する"""

    # ログが空なら終了
    if not log:
        return

    try:
        import matplotlib

        # 画面を表示せず画像として保存
        matplotlib.use("Agg")

        import matplotlib.pyplot as plt

    except ImportError:
        print("matplotlib not available; skipping plot")
        return

    # ログからX座標とY座標を取り出す
    xs = [row[1] for row in log]
    ys = [row[2] for row in log]

    fig, ax = plt.subplots()

    # 基準経路
    ax.plot(path.points[:, 0], path.points[:, 1], "b--", label="reference")

    # 推定した走行軌跡
    ax.plot(xs, ys, "r-", label="driven (estimate)")

    # 開始位置
    ax.plot(xs[0], ys[0], "go", label="start")

    # X軸とY軸の縮尺を揃える
    ax.set_aspect("equal")
    ax.legend()
    ax.set_title("Ellipse reference vs driven")

    # グラフを画像へ保存
    fig.savefig(PLOT_PNG, dpi=120)

    print(f"plot saved: {PLOT_PNG}")


# このファイルが直接実行されたときだけmainを実行
if __name__ == "__main__":
    main()
