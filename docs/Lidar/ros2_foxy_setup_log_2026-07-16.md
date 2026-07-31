# ROS2 Foxy LiDAR環境セットアップ記録 2026-07-16

## 目的

Ubuntu 20.04 環境の個人PCで、RPLidar A1M8-R6 をROS2から扱うための準備状況を記録する。

最終的には次の流れで地図作成と自己位置推定へ進める。

```text
RPLidar A1 -> /scan -> RViz表示 -> TF追加 -> slam_toolboxで地図作成
```

距離はメートル[m]、角度はラジアン[rad]で扱う。

## 環境

確認したPC環境は次である。

```text
OS: Ubuntu 20.04.6 LTS focal
ROS2: Foxy
ROS_DISTRO: foxy
ros2: /opt/ros/foxy/bin/ros2
```

当初は Ubuntu 22.04 + ROS2 Humble も候補だったが、別のシミュレーションがUbuntu 20.04依存の可能性があるため、このPCではUbuntu 20.04を維持する。

このPCではROS2 Foxyで進め、研究用デスクトップPCの最終環境は別途決める。

## 確認済み

ROS2 CLIは使用できる。

```bash
source /opt/ros/foxy/setup.bash
ros2 --help
```

RViz2は使用できる。

```bash
rviz2 --help
```

colconは使用できる。

```bash
colcon --help
```

`slam_toolbox` はインストール済みである。

```bash
ros2 pkg list | grep slam_toolbox
```

確認結果:

```text
slam_toolbox
```

`sllidar_ros2` はROS2ワークスペースに導入済みで、ROS2から認識できる。

```bash
source /opt/ros/foxy/setup.bash
source ~/ros2_ws/install/setup.bash
ros2 pkg list | grep sllidar
```

確認結果:

```text
sllidar_ros2
```

RPLidar A1用launchファイルも存在する。

```bash
ls ~/ros2_ws/src/sllidar_ros2/launch
```

確認済みの主なlaunchファイル:

```text
sllidar_a1_launch.py
view_sllidar_a1_launch.py
```

RPLidar A1用launchの引数確認もできた。

```bash
ros2 launch sllidar_ros2 view_sllidar_a1_launch.py --show-args
```

確認された主な引数:

```text
channel_type
serial_port
serial_baudrate
frame_id
inverted
angle_compensate
scan_mode
```

## sllidar_ros2 ビルド時の問題と対応

最初のビルドでは、condaの `base` 環境が有効だったため失敗した。

失敗時、ROS2ビルドが次のPythonを使っていた。

```text
/home/ubuntuyuzz/anaconda3/bin/python3
```

エラーは次である。

```text
ModuleNotFoundError: No module named 'catkin_pkg'
```

対応として、condaを無効化してからビルドし直した。

```bash
conda deactivate
cd ~/ros2_ws
rm -rf build install log
source /opt/ros/foxy/setup.bash
colcon build --symlink-install
```

その後、`sllidar_ros2` のビルドは成功した。

```text
Finished <<< sllidar_ros2
Summary: 1 package finished
```

ROS2のビルド時は、原則としてconda環境を無効化し、`/usr/bin/python3` を使う。

確認コマンド:

```bash
which python3
python3 -c "import sys; print(sys.executable)"
```

期待値:

```text
/usr/bin/python3
```

## 現時点で未確認の項目

この時点ではLiDAR実機が手元にないため、次は未確認である。

- USB接続時に `/dev/ttyUSB0` または `/dev/ttyACM0` として認識されるか。
- `sllidar_ros2` からRPLidar A1を起動できるか。
- `/scan` がpublishされるか。
- RVizでスキャンが表示されるか。
- `LaserScan` の `ranges` がメートル[m]として妥当か。
- `LaserScan` の `angle_min`, `angle_max`, `angle_increment` がラジアン[rad]として妥当か。

## 次回LiDAR実機があるときの手順

まずconda環境が有効なら無効化する。

```bash
conda deactivate
```

ROS2環境を読み込む。

```bash
source /opt/ros/foxy/setup.bash
source ~/ros2_ws/install/setup.bash
```

LiDARをUSB接続し、デバイス名を確認する。

```bash
ls /dev/ttyUSB* /dev/ttyACM*
```

認識されない場合は、挿し直した直後に次を確認する。

```bash
dmesg | tail -30
lsusb
```

`/dev/ttyUSB0` として認識された場合は、一時的に権限を付ける。

```bash
sudo chmod 666 /dev/ttyUSB0
```

RPLidar A1を起動する。

```bash
ros2 launch sllidar_ros2 view_sllidar_a1_launch.py serial_port:=/dev/ttyUSB0
```

別ターミナルで `/scan` を確認する。

```bash
source /opt/ros/foxy/setup.bash
source ~/ros2_ws/install/setup.bash

ros2 topic list
ros2 topic echo /scan --once
```

確認する値:

```text
header.frame_id
angle_min
angle_max
angle_increment
range_min
range_max
ranges
```

`angle_min`, `angle_max`, `angle_increment` はラジアン[rad]である。

`range_min`, `range_max`, `ranges` はメートル[m]である。

## 次の判断

`/scan` がRVizで表示できたら、次は `base_link -> laser` のTFを定義する。

```text
map -> odom -> base_link -> laser
```

この段階では、まだESC、ステアリング、GPIO、pigpio、自動走行制御には接続しない。

