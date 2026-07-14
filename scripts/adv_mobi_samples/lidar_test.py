from rplidar import RPLidar


# RPLidarが接続できるかを確認する最小テスト。
# LiDARは /dev/ttyUSB0 に接続されている前提。
lidar = RPLidar('/dev/ttyUSB0')

# デバイス情報を取得して表示する。
info = lidar.get_info()
print(info)

# LiDARの状態を取得して表示する。
health = lidar.get_health()
print(health)

# スキャンを繰り返し取得し、各スキャンに含まれる測距点数を表示する。
for i, scan in enumerate(lidar.iter_scans()):
    print('%d: Got %d measures' % (i, len(scan)))

# 終了時はモーター停止とシリアル切断を行う。
lidar.stop()
lidar.stop_motor()
lidar.disconnect()
