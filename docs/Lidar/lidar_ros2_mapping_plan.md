# LiDAR地図作成・自己位置推定計画

## 目的

RPLidar A1M8-R6 を使い、RCカーが地図上で自己位置を推定できる状態まで進める。

最終的には、LiDARスキャンと車輪オドメトリから車体の姿勢を推定する。

```text
LiDAR scan + wheel odometry -> localization -> x_m, y_m, yaw_rad
```

位置はメートル[m]、角度はラジアン[rad]で扱う。

## 現状

LiDAR単体のPython確認は完了している。

現在のPython確認では、RPLidarからスキャンを取得し、CSV保存と2Dプロットで距離、角度方向、欠測、外れ値を確認する。

関連文書は次である。

```text
docs/Lidar/csv_plot_test.md
```

関連スクリプトは次である。

```text
scripts/device_test/rccar_tests/test_lidar/RPlidarA1M8_test.py
scripts/device_test/rccar_tests/test_lidar/rplidar_csv_plot_test.py
```

## 方針

PythonとROS2は役割を分けて並行で使う。

| 領域 | 担当 | 目的 |
| --- | --- | --- |
| LiDAR単体確認 | Python | 接続確認、CSV保存、点群プロット、ログ確認 |
| 地図作成 | ROS2 | `/scan`、TF、SLAM、map保存 |
| 自己位置推定 | ROS2 | 保存地図上での `x_m`, `y_m`, `yaw_rad` 推定 |
| 実車制御との接続 | PythonまたはROS2 | 推定姿勢を制御へ渡す |

Pythonだけで地図作成と自己位置推定まで実装することは可能だが、地図、TF、オドメトリ、自己位置推定、可視化を自作する必要がある。

そのため、Pythonは確認とログ取得に使い、地図作成と自己位置推定はROS2で進める。

## 注意

PythonスクリプトとROS2ドライバを同時に同じLiDARへ接続しない。

RPLidarが `/dev/ttyUSB0` として接続されている場合、同時に使えるのは次のどちらか一方である。

```text
Python script
ROS2 sllidar driver
```

同時接続すると、シリアル通信の競合やLiDARモータ制御の競合が起きる。

## 座標系

ROS2側では次のTF構成を目標にする。

```text
map -> odom -> base_link -> laser
```

各座標系の意味は次である。

| frame | 意味 |
| --- | --- |
| `map` | SLAMまたは保存地図の座標系 |
| `odom` | 車輪オドメトリなどから積分した連続座標系 |
| `base_link` | 車体基準点 |
| `laser` | LiDAR本体の座標系 |

最初に必ず記録する取り付け値は次である。

```text
lidar_x_m
lidar_y_m
lidar_z_m
lidar_yaw_rad
```

`lidar_x_m`, `lidar_y_m`, `lidar_z_m` は `base_link` から見た `laser` の位置[m]である。

`lidar_yaw_rad` は `base_link` から見た `laser` のヨー角[rad]である。

## Phase 1: Python確認

### 目的

LiDAR単体のスキャン取得、CSV保存、2Dプロットができることを確認する。

### 状態

完了。

### 合格条件

- LiDARからスキャンを取得できる。
- 距離をメートル[m]で保存できる。
- 角度をラジアン[rad]で保存できる。
- CSVから `x_m`, `y_m` の散布図を作れる。
- LiDARの `0 rad` 方向と角度増加方向を説明できる。

## Phase 2: ROS2で `/scan` を表示

### 目的

ROS2上でRPLidar A1を起動し、`sensor_msgs/msg/LaserScan` として `/scan` を出す。

### 作業

1. ROS2ワークスペースを用意する。
2. SlamtecのROS2ドライバを導入する。
3. RPLidar A1用launchでLiDARを起動する。
4. `ros2 topic list` で `/scan` が出ていることを確認する。
5. `ros2 topic echo /scan --once` で値を確認する。
6. RVizで `/scan` を表示する。

### 合格条件

- `/scan` が publish される。
- `ranges` がメートル[m]として妥当である。
- `angle_min`, `angle_max`, `angle_increment` がラジアン[rad]で出ている。
- RViz上で壁や障害物の形が見える。
- LiDAR停止時にプロセスを終了できる。

## Phase 3: `base_link -> laser` TF定義

### 目的

LiDAR座標系を車体座標系へ接続する。

### 作業

1. 車体基準点 `base_link` を決める。
2. `base_link` から見たLiDAR位置を測る。
3. LiDARの向き、特に `0 rad` 方向を確認する。
4. `static_transform_publisher` またはURDFで `base_link -> laser` を出す。
5. RVizでTFと `/scan` の向きが合っていることを確認する。

### 合格条件

- TF treeに `base_link` と `laser` が出る。
- `/scan` の `frame_id` とTFがつながる。
- 車体前方、左右方向、LiDAR点群の向きが説明できる。

## Phase 4: 地図作成

### 目的

`slam_toolbox` を使い、実験場所の2D地図を作る。

### 初期方針

最初の地図作成は手押しで行う。

ESC、ステアリング、GPIO、pigpioを地図作成の最初の確認には接続しない。車両制御の問題を切り離し、LiDAR、TF、SLAMだけを先に確認する。

### 作業

1. 壁や大きな物体がある場所を選ぶ。
2. LiDARを車体へ固定する。
3. ROS2ドライバで `/scan` を出す。
4. `base_link -> laser` TFを出す。
5. `slam_toolbox` を起動する。
6. 車体をゆっくり手押しで動かす。
7. RVizで地図の形が崩れないか確認する。
8. 地図を保存する。

### 合格条件

- 地図に壁や大きな障害物の形が出る。
- 大きな回転や移動で地図が極端に二重化しない。
- 保存地図を再読み込みできる。

## Phase 5: 車輪オドメトリ追加

### 目的

自己位置推定で使う `odom -> base_link` を出す。

### 作業

1. エンコーダから車輪速度を取得する。
2. 車体モデルから `x_m`, `y_m`, `yaw_rad` を積分する。
3. `nav_msgs/msg/Odometry` をpublishする。
4. `odom -> base_link` TFをpublishする。
5. RVizでオドメトリの向きと移動量を確認する。

### 注意

デッドレコニングは、車輪スリップ、ステアリング校正誤差、機械的バックラッシュで姿勢誤差が蓄積する。

オドメトリは単独の正解として扱わず、LiDARによる地図照合と組み合わせる。

### 合格条件

- 車体を前進させると `x_m` または設定した前方軸方向に増える。
- 旋回させると `yaw_rad` が妥当に変化する。
- 静止中に大きなドリフトが出ない。
- `/odom` とTFがRVizでつながる。

## Phase 6: 保存地図で自己位置推定

### 目的

作成済み地図上で、現在の車体位置と向きを推定する。

### 作業

1. 保存済み地図を読み込む。
2. `slam_toolbox` のlocalization mode、またはROS2 Nav2 AMCLを検討する。
3. `/scan`、`/odom`、TFを入力する。
4. RVizで推定姿勢を確認する。
5. 手で車体を動かし、推定位置が追従するか確認する。

### 合格条件

- 地図上で `base_link` の位置が表示される。
- 車体を動かすと推定位置が追従する。
- 同じ場所へ戻したときに、姿勢推定が大きく破綻しない。
- `x_m`, `y_m`, `yaw_rad` を制御側へ渡せる見通しが立つ。

## Phase 7: 実車制御との接続

### 目的

自己位置推定結果を、RCカーの制御に接続する。

### 作業

1. 推定姿勢の取得方法を決める。
2. 既存のPython制御へ渡すか、ROS2ノードとして制御するか決める。
3. 低速、短時間、手動停止可能な条件で確認する。
4. 位置推定が破綻した場合は停止する安全条件を入れる。

### 注意

この段階までは、LiDAR系と車両駆動系を不用意に結合しない。

実車を動かす場合は、駆動輪を浮かせた確認、低速、物理的な電源遮断手段を準備する。

## 推奨ROS2ワークスペース構成

ROS2へ移行する場合、最初は次のように分ける。

```text
ros2_ws/src/
  openminicar_description/    # base_link, laser, URDF, static TF
  openminicar_lidar_bringup/  # RPLidar, RViz, SLAM launch/config
  openminicar_base/           # encoder, odom, base_link TF
```

最初に作るべきものは `openminicar_lidar_bringup` である。

## 次に行う作業

次の作業は、ROS2でRPLidar A1を起動して `/scan` をRVizに表示することである。

```text
Phase 2: ROS2で /scan を表示
```

この段階では、まだESC、ステアリング、GPIO、pigpio、自動走行制御には接続しない。

