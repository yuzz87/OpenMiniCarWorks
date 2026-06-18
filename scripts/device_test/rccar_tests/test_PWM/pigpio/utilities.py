# getkey
import fcntl
import os
import sys
import termios


def getkey():
    # 標準入力の番号を取得
    fno = sys.stdin.fileno()

    # 現在の端末設定を保存
    attr_old = termios.tcgetattr(fno)

    # Enterなしでキー入力を読めるように設定
    attr = termios.tcgetattr(fno)
    attr[3] = attr[3] & ~termios.ECHO & ~termios.ICANON
    termios.tcsetattr(fno, termios.TCSADRAIN, attr)

    # キー入力がなくても待たない設定にする
    fcntl_old = fcntl.fcntl(fno, fcntl.F_GETFL)
    fcntl.fcntl(fno, fcntl.F_SETFL, fcntl_old | os.O_NONBLOCK)

    # 押されたキーの値
    chr = 0

    try:
        # 1文字ずつキー入力を読む
        c = sys.stdin.read(1)
        if len(c):
            while len(c):
                # 文字を数値に変換して保存
                chr = (chr << 8) + ord(c)
                c = sys.stdin.read(1)
    finally:
        # 端末設定を元に戻す
        fcntl.fcntl(fno, fcntl.F_SETFL, fcntl_old)
        termios.tcsetattr(fno, termios.TCSANOW, attr_old)

    # 押されたキーの値を返す
    return chr


if __name__ == "__main__":
    while 1:
        # キー入力を取得
        key = getkey()

        # Enterキーで終了
        if key == 10:
            break

        # キー入力があれば表示
        elif key:
            print(key)
