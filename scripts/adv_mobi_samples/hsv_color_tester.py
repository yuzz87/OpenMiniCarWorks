import cv2


def main():
    # カメラ画像中央のHSV値を画面に表示する確認用スクリプト。
    # color_detector.py の hsv_range_list を調整する前に、対象物の色を読むために使う。

    # カメラ入力サイズ。小さくすると処理は軽くなるが、表示の精細さは下がる。
    frame_width = 160
    frame_height = 120

    # OpenCVやカメラドライバの制約に合わせ、幅は32、高さは16の倍数に丸める。
    frame_width = 32 * round(frame_width / 32)
    frame_height = 16 * round(frame_height / 16)

    # 既定のカメラを開き、解像度を設定する。
    capture = cv2.VideoCapture(-1)
    capture.set(cv2.CAP_PROP_FRAME_WIDTH, frame_width)
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, frame_height)
    print(f"frame width: {capture.get(cv2.CAP_PROP_FRAME_WIDTH)}")
    print(f"frame height: {capture.get(cv2.CAP_PROP_FRAME_HEIGHT)}")

    try:
        while True:
            # カメラから1フレーム取得する。
            got_frame, frame = capture.read()

            # 車体へのカメラ取り付け向きに合わせ、表示画像を180度回転する。
            frame = cv2.rotate(frame, cv2.ROTATE_180)

            # BGR画像をHSV_FULLへ変換する。H, S, V は 0-255 の範囲。
            hsv_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV_FULL)

            # 画面中央の画素を読み、そのHSV値を表示する。
            h_val = hsv_frame[(int)(frame_height/2), (int)(frame_width/2)][0]
            s_val = hsv_frame[(int)(frame_height/2), (int)(frame_width/2)][1]
            v_val = hsv_frame[(int)(frame_height/2), (int)(frame_width/2)][2]
            # 中央位置に十字マーカーを描き、その右側にH/S/V値を重ねる。
            cv2.drawMarker(frame, ((int)(frame_width/2), (int)(frame_height/2)), (0, 0, 255), cv2.MARKER_TILTED_CROSS, 10)
            cv2.putText(frame, "h:" + "%3.0f"%h_val, ((int)(frame_width/2 + 10), (int)(frame_height/2 - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.3, (0, 0, 255))
            cv2.putText(frame, "s:" + "%3.0f"%s_val, ((int)(frame_width/2 + 10), (int)(frame_height/2 -  0)), cv2.FONT_HERSHEY_SIMPLEX, 0.3, (0, 0, 255))
            cv2.putText(frame, "v:" + "%3.0f"%v_val, ((int)(frame_width/2 + 10), (int)(frame_height/2 + 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.3, (0, 0, 255))

            # OpenCVウィンドウを更新する。
            cv2.waitKey(1)
            cv2.imshow("camera", frame)


    except KeyboardInterrupt:
        # Ctrl-Cで終了する。カメラ解放はプロセス終了時のOpenCV側処理に任せている。
        pass


if __name__ == "__main__":
    main()
