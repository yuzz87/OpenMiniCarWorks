import multiprocessing
import cv2
import numpy as np
import time
from typing import List, Tuple


# カメラ画像から指定したHSV色範囲を検出するための補助クラス。
# 各処理を multiprocessing.Process で分け、キューを使って
# 「カメラ取得 -> HSV二値化 -> 連結成分解析」へ流す構成になっている。
class ColorDetector(object):
    @staticmethod
    def updateFrame(
            q_frame_list: List[multiprocessing.Queue],
            update_rate: float = 10,
            frame_width: int = 320,
            frame_height: int = 240,
        ):
        '''
        Add frame to queue from camera.

        q_frame_list: list of queue of frame
        frame_width: frame width (1 for minimum)
        frame_height: frame height (1 for minimum)
        '''
        # カメラ入力を初期化する。VideoCapture(-1) は環境依存で既定のカメラを開く。
        capture = cv2.VideoCapture(-1)
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, frame_width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, frame_height)

        # update_rate[Hz] に合わせて、フレームをキューへ流す周期を決める。
        update_period = 1.0 / update_rate
        update_time = time.clock_gettime(time.CLOCK_BOOTTIME) + update_period

        while True:
            # カメラから1フレーム取得する。frame は OpenCV 標準の BGR 画像。
            got_frame, frame = capture.read()

            # 指定周期になるまでは読み捨てて、後段処理の負荷を抑える。
            if time.clock_gettime(time.CLOCK_BOOTTIME) < update_time:
                continue

            # 取得に失敗した場合は、次の取得まで待って復帰を試す。
            if not got_frame:
                print("failed to grab frame")
                update_time += 1.0
                continue

            for q_frame in q_frame_list:
                # キューが満杯なら古いフレームを捨て、常に新しい画像を優先する。
                if q_frame.full():
                    q_frame.get()

                # 色ごとの二値化プロセスへ同じフレームを配る。
                q_frame.put(frame)

            update_time += update_period


    @staticmethod
    def getBinFrame(
            hsv_range: List[Tuple[int, int, int]],
            q_frame: multiprocessing.Queue,
            q_bin: multiprocessing.Queue,
        ):
        '''
        Add binarized image to queue from frame.

        hsv_range: hsv range for binarization [(hsv_low), (hsv_high)] h:0-255 s:0-255 v:0-255
        q_frame: queue of frame (frame)
        q_bin: queue of binarized image (frame, bin_frame, bgr_disp)
        '''
        # 表示用の色を、検出対象のHSV範囲からBGRへ変換して作る。
        # OpenCV の描画関数はBGR順なので、ここで変換しておく。
        hsv_low, hsv_high = hsv_range
        h_mean = (hsv_low[0] + hsv_high[0]) / 2
        hsv_disp = np.array([h_mean, hsv_high[1], hsv_high[2]])
        bgr_disp = cv2.cvtColor(np.uint8([[hsv_disp]]), cv2.COLOR_HSV2BGR_FULL)[0, 0]
        bgr_disp = (int(bgr_disp[0]), int(bgr_disp[1]), int(bgr_disp[2]))

        while True:
            # カメラ取得プロセスから最新フレームを受け取る。
            frame = q_frame.get()

            # BGR画像をHSV_FULLへ変換する。H, S, V は 0-255 の範囲。
            hsv_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV_FULL)

            # 指定HSV範囲に入る画素だけを白、それ以外を黒にする。
            bin_frame = cv2.inRange(hsv_frame, hsv_range[0], hsv_range[1])

            # 後段が遅れている場合は古い二値画像を捨てる。
            if q_bin.full():
                q_bin.get()

            # 元画像、二値画像、表示色をまとめて連結成分解析へ渡す。
            q_bin.put([frame, bin_frame, bgr_disp])


    @staticmethod
    def getConnectedComponents(
            q_bin: multiprocessing.Queue,
            q_stats: multiprocessing.Queue,
        ):
        '''
        Add connected components to queue from binarized image.

        q_bin: queue of binarized image (frame, bin_frame, bgr_disp)
        q_stats: queue of connected components (frame, n_labels, labels, stats, centroids, bgr_disp)
        '''
        while True:
            # 二値化プロセスから画像一式を受け取る。
            frame, bin_frame, bgr_disp = q_bin.get()

            # 白画素のまとまりをラベル付けし、面積や重心を計算する。
            n_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(bin_frame)

            # 最新の検出結果を優先するため、キューが満杯なら古い結果を捨てる。
            if q_stats.full():
                q_stats.get()

            # 描画や制御で使うため、連結成分の統計情報をキューへ渡す。
            q_stats.put([frame, n_labels, labels, stats, centroids, bgr_disp])


def run(
        q_stats_list: List[multiprocessing.Queue],
        show_image: bool = True
    ):
    # 色ごとの連結成分解析結果を集め、最大の領域をカメラ画像へ描画する。
    while True:
        frame_updated = False
        for q_stats in q_stats_list:
            # 色ごとの検出結果を受け取る。
            _frame, n_labels, labels, stats, centroids, bgr_disp = q_stats.get()

            # 表示用フレームは最初に届いたものを使う。
            if not frame_updated:
                frame = _frame
                frame_updated = True

            # ラベル0は背景なので、n_labels >= 2 のときだけ対象物がある。
            if n_labels >= 2:
                # 背景を除いた最大面積のラベルを検出対象として扱う。
                max_idx = np.argmax(stats[1:, cv2.CC_STAT_AREA]) + 1

                left, top, width, height, area = stats[max_idx]
                centroid = centroids[max_idx]

                if show_image:
                    # 対象物の重心を、検出色に近い色で塗りつぶす。
                    cv2.circle(frame, tuple(np.int32(centroid)), 5, bgr_disp, thickness=-1)

                    # 対象物の外接矩形を描画する。
                    cv2.rectangle(frame, (left, top), (left + width, top + height), bgr_disp, thickness=2)

        if show_image:
            # 車体へのカメラ取り付け向きに合わせ、表示画像を180度回転する。
            frame = cv2.rotate(frame, cv2.ROTATE_180)

            # OpenCVウィンドウを更新する。
            cv2.waitKey(1)
            cv2.imshow("camera", frame)


def main():
    # カメラと色検出の設定値。
    update_rate = 10 # frame update rate
    frame_width = 160 # frame width (1 for minimum)
    frame_height = 120 # frame height (1 for minimum)
    show_image = True # true to show image
    hsv_range_list = [ # hsv range for each color [(hsv_low), (hsv_high)] h:0-255 s:0-255 v:0-255
        [(0, 120, 120), (25, 255, 255)], # red
        [(25, 130, 150), (55, 255, 255)], # yellow
        [(55, 120, 70), (120, 255, 255)], # green
        [(120, 100, 70), (190, 255, 255)], # blue
    ]

    # OpenCVやカメラドライバの制約に合わせ、幅は32、 高さは16の倍数に丸める。
    frame_width = 32 * round(frame_width / 32)
    frame_height = 16 * round(frame_height / 16)

    # 色ごとに、フレーム・二値画像・連結成分結果を受け渡すキューを作る。
    q_frame_list = []
    q_bin_list = []
    q_stats_list = []
    for i in range(len(hsv_range_list)):
        q_frame_list.append(multiprocessing.Queue(maxsize=2))
        q_bin_list.append(multiprocessing.Queue(maxsize=2))
        q_stats_list.append(multiprocessing.Queue(maxsize=2))

    # カメラ取得、色ごとの二値化、連結成分解析、表示を別プロセスで動かす。
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
    processes.append(
        multiprocessing.Process(
            target=run,
            args=(q_stats_list, show_image,)
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
        # 終了時は子プロセスを停止し、joinして後始末する。
        for process in processes:
            process.terminate()
            process.join()
        print("\nclosed all processes")


if __name__ == "__main__":
    main()
