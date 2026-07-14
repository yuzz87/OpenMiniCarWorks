### PARAMETERS START ### : edit these parameters

# Raspberry Pi上で実機制御まで行うかどうか。
# Trueの場合は pigpio と RPi.GPIO 系の処理を使い、車両が動く可能性がある。
use_raspi = True # true to run on raspberry pi

# 色検出の設定値。
update_rate = 20 # frame update rate
frame_width = 160 # frame width
frame_height = 120 # frame height
show_image = True # true to show image
hsv_range_list = [ # hsv range for each color [(hsv_low), (hsv_high)] h:0-255 s:0-255 v:0-255
    [(0, 0, 80), (255, 15, 255)], # white
    [(0, 120, 120), (25, 255, 255)], # red
    [(25, 130, 150), (55, 255, 255)], # yellow
    [(60, 70, 110), (90, 255, 255)], # green
    [(120, 100, 70), (190, 255, 255)], # blue
]

# 速度観測用エンコーダの設定値。wheel_diameterの単位は[m]。
n_teeth = 36 # number of teeth on encoder
wheel_diameter = 0.06 # wheel diameter in meters

# GPIOとPWM出力の設定値。ピン番号はBCM GPIO番号。
STEER_PIN = 17
THROTTLE_PIN = 18
ENCODER_A_PIN = 22
ENCODER_B_PIN = 27

# サーボ/ESCの中立パルス幅[us]。
NEUTERAL_INPUT = 1500

### PARAMETERS END ###

import multiprocessing
from color_detector import ColorDetector
if use_raspi:
    from speed_observer import SpeedObserver
import pigpio
import cv2
import numpy as np
import time
from typing import List

# Raspberry Pi実行時だけpigpioへ接続する。
if use_raspi:
    raspi = pigpio.pi()


def custom_control_function(
        centroid_list: List[tuple],
        area_list: List[float],
        speed: float
    ):
    # 色検出結果と速度観測値から、ステアリングとスロットルを決めるユーザー制御部。
    # centroid_list と area_list は hsv_range_list と同じ順番で並ぶ。
    # このサンプルでは緑色の重心を画面中央へ寄せるようにステアリングを切る。
    ### CONTROL START ### : place your code here to control the car

    # 検出色ごとの最大領域の重心と面積を取り出す。未検出の場合、重心はNoneになる。
    white_centroid = centroid_list[0]
    white_area = area_list[0]

    red_centroid = centroid_list[1]
    red_area = area_list[1]

    yellow_centroid = centroid_list[2]
    yellow_area = area_list[2]

    green_centroid = centroid_list[3]
    green_area = area_list[3]

    blue_centroid = centroid_list[4]
    blue_area = area_list[4]

    # ステアリングとスロットルのオフセット[us]を計算する。
    steer = 0
    throttle = 0
    if green_centroid is not None:
        # 画面中心からの横方向ずれを -1.0 から +1.0 程度に正規化する。
        center_error = (green_centroid[0] - frame_width/2) / (frame_width/2) 
        # ずれに比例してステアリングを切る。符号は実車の取り付け方向に依存する。
        steer = -600 * center_error
        # 大きく曲がるほど速度を落とす簡易制御。
        throttle = 30 * (1-0.3*abs(center_error))

    # 実機実行時だけサーボ/ESCへパルス幅[us]を出力する。
    if use_raspi:
        raspi.set_servo_pulsewidth(STEER_PIN, NEUTERAL_INPUT + steer)
        raspi.set_servo_pulsewidth(THROTTLE_PIN, NEUTERAL_INPUT - throttle)

    ### CONTROL END ###


def run(
        q_stats_list: List[multiprocessing.Queue],
        q_speed: multiprocessing.Queue,
        show_image: bool
    ):
    # 色検出プロセス群と速度観測プロセスから最新値を集め、制御関数を周期的に呼ぶ。
    ### SETUP START ### : place your code here to run once

    # 各色の検出結果、速度、表示用フレームを保持する。
    color_stats_list = [None for i in range(len(hsv_range_list))]
    speed = None
    frame = None

    # 起動時にステアリングとスロットルを中立へ戻す。
    neuteral()

    # 各色の検出プロセスが最初の結果を出すまで待つ。
    for i, q_stats in enumerate(q_stats_list):
        while True:
            try:
                color_stats_list[i] = q_stats.get(timeout=1.0)
                break
            except multiprocessing.queues.Empty:
                print ("waiting for color detection")
                continue
    frame = color_stats_list[0][0]

    # Raspberry Pi実行時は、速度観測プロセスが最初の値を出すまで待つ。
    if use_raspi:
        while True:
            try:
                speed = q_speed.get(timeout=1.0)
                break
            except multiprocessing.queues.Empty:
                print ("waiting for speed observation")
                continue

    ### SETUP END ###

    ### LOOP START ### : place your code here to run repeatedly

    while True:
        # 各色の検出結果を、キューに新しい値がある場合だけ更新する。
        frame_updated = False
        for i, q_stats in enumerate(q_stats_list):
            try:
                color_stats_list[i] = q_stats.get(block=False)
                if not frame_updated and show_image:
                    frame = color_stats_list[i][0]
                    frame_updated = True
            except multiprocessing.queues.Empty:
                continue

        # エンコーダ速度[m/s]も、新しい値があれば更新する。
        try:
            speed = q_speed.get(block=False)
        except multiprocessing.queues.Empty:
            pass

        # 各色について、最大の連結成分の重心と面積を取り出す。
        centroid_list = []
        area_list = []
        for color_stats in color_stats_list:
            centroid, area = get_largest_component(color_stats, frame)
            centroid_list.append(centroid)
            area_list.append(area)

        if show_image and frame_updated:
            # カメラ取り付け向きに合わせ、表示画像を180度回転する。
            frame = cv2.rotate(frame, cv2.ROTATE_180)

            # 検出結果を重ねたフレームを表示する。
            cv2.imshow('frame', frame)
            cv2.waitKey(1)

        # 最新の色検出結果と速度を使って車両制御を行う。
        custom_control_function(centroid_list, area_list, speed)

    ### LOOP END ###


def get_largest_component(
        color_stats: List,
        frame: np.ndarray
    ):
    '''
    Get largest connected component from color detection results.

    color_stats: color detection results
    frame: frame to draw bounding box and centroid
    '''
    # ColorDetector.getConnectedComponents() の出力を展開する。
    _frame, n_labels, labels, stats, centroids, bgr_disp = color_stats

    # 対象色が見つからなかった場合はNoneを返す。
    centroid = None
    area = None

    # ラベル0は背景なので、n_labels >= 2 のとき対象色の領域がある。
    if n_labels >= 2:
        # 背景を除き、最大面積の連結成分を対象物として選ぶ。
        max_idx = np.argmax(stats[1:, cv2.CC_STAT_AREA]) + 1

        # 最大成分の外接矩形、面積、重心を取り出す。
        left, top, width, height, area = stats[max_idx]
        centroid = centroids[max_idx]

        if show_image:
            # 表示用フレームへ外接矩形を描画する。
            cv2.rectangle(frame, (left, top), (left + width, top + height), bgr_disp, 2)

            # 最大成分の重心を描画する。
            cv2.circle(frame, (int(centroid[0]), int(centroid[1])), 5, bgr_disp, -1)

    return centroid, area


def neuteral():
    # 実機実行時だけ、ステアリングとスロットルを中立パルス幅[us]へ戻す。
    if use_raspi:
        raspi.set_servo_pulsewidth(STEER_PIN,NEUTERAL_INPUT)
        raspi.set_servo_pulsewidth(THROTTLE_PIN,NEUTERAL_INPUT)


def main():
    # OpenCVやカメラドライバの制約に合わせ、幅は32、高さは16の倍数に丸める。
    global frame_width, frame_height
    frame_width = 32 * round(frame_width / 32)
    frame_height = 16 * round(frame_height / 16)

    # 色ごとのフレーム、二値画像、連結成分結果を受け渡すキューを作る。
    q_frame_list = []
    q_bin_list = []
    q_stats_list = []
    for i in range(len(hsv_range_list)):
        q_frame_list.append(multiprocessing.Queue(maxsize=2))
        q_bin_list.append(multiprocessing.Queue(maxsize=2))
        q_stats_list.append(multiprocessing.Queue(maxsize=2))
    q_speed = multiprocessing.Queue(maxsize=10)

    # カメラ取得、色ごとの二値化、連結成分解析、速度観測、制御ループを別プロセスで動かす。
    processes: List[multiprocessing.Process] = []
    processes.append(
        multiprocessing.Process(
            target=ColorDetector.updateFrame,
            args=(q_frame_list, update_rate, frame_width, frame_height,)
        )
    )
    for hsv_range, q_frame, q_bin, q_stats in zip(hsv_range_list, q_frame_list, q_bin_list, q_stats_list):
        processes.append(
            multiprocessing.Process(
                target=ColorDetector.getBinFrame,
                args=(hsv_range, q_frame, q_bin,)
            )
        )
        processes.append(
            multiprocessing.Process(
                target=ColorDetector.getConnectedComponents,
                args=(q_bin, q_stats,)
            )
        )
    if use_raspi:
        processes.append(
            multiprocessing.Process(
                target=SpeedObserver.updateSpeed,
                args=(q_speed, ENCODER_A_PIN, ENCODER_B_PIN, n_teeth, wheel_diameter,)
            )
        )
    processes.append(
        multiprocessing.Process(
            target=run,
            args=(q_stats_list, q_speed, show_image,)
        )
    )

    # すべての処理プロセスを開始する。
    for process in processes:
        process.start()

    # Ctrl-Cが押されるまでメインプロセスは待機する。
    try:
        while True:
            time.sleep(1e5)
    except KeyboardInterrupt:
        # 終了時は子プロセスを停止し、車両を中立へ戻す。
        for process in processes:
            process.terminate()
            process.join()
        neuteral()
        print("\nclosed all processes")


if __name__ == "__main__":
    main()
