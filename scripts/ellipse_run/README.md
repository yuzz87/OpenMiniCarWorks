# ellipse_run — 参照軌道（楕円）走行 MVP

事前に定義した**参照軌道（楕円）**を、外部センサ（LiDAR/カメラ）を使わず
**Raspberry Pi 4 + タイヤエンコーダ + ステアサーボだけ**で追従できるかを確認する MVP。
将来 LiDAR で自己位置推定を足せるよう、**pose 取得部だけ差し替えられる**構成にしてある。

## 構成

```
odometer.py        エンコーダ A/B パルス計数 → 累積走行距離
localizer.py       Localizer 抽象 + DeadReckoningLocalizer（推測航法）
                   ※将来は LidarMCLLocalizer を差し込むだけ
reference_path.py  楕円生成 / CSV 読込, 弧長・符号付き曲率・最小回転半径
pure_pursuit.py    Pure Pursuit → ステア角
car_driver.py      ステア角/スロットル → pigpio サーボ出力（既存流用）
run_ellipse.py     統合メイン（制御ループ）
```

データの流れ（~50Hz）:
`odometer → localizer → reference_path → pure_pursuit → car_driver`

## 実行

### PCドライラン（ハード不要・先に動作確認）
`run_ellipse.py` の `use_hardware = False` にして実行。車両を同じ自転車モデルで
シミュレートし、軌跡を `pose_log.csv` と `ellipse_track.png` に出力する。
```bash
python3 run_ellipse.py
```

### 実機（Raspberry Pi 4）
```bash
sudo pigpiod                 # pigpio デーモン起動（必須）
# run_ellipse.py: use_hardware = True
python3 run_ellipse.py
```
`RPi.GPIO`（エンコーダ）と `pigpio`（サーボ）が必要。停止は Ctrl-C（即ニュートラル）。

## 事前キャリブレーション（`run_ellipse.py` の PARAMETERS を実測値に）

| パラメータ | 内容 | 取り方 |
|---|---|---|
| `WHEELBASE` | 前後車軸間距離[m] | 実測 |
| `WHEEL_DIAMETER` | タイヤ直径[m] | 実測（≈0.066） |
| `MAX_STEER_DEG` | 最大ステア角 | `test_PWM/pigpio/key_calib.py` で確認 |
| `STEER_RANGE_US` | 全舵角時の pulsewidth 振れ幅 | key_calib |
| `STEER_SIGN` | 左右が逆なら -1 | 実走で確認 |
| `THROTTLE_DRIVE_US` | 前進スロットル（このESCは中立より小=前進） | `speed_observer.py` で速度実測 |

## 安全・注意
- **最小回転半径**: 楕円の短軸がきついと曲がりきれない。起動時に警告を表示。
- **ヘディング drift**: IMU 無し・ステア開ループのため周回で誤差が蓄積。MVP は1〜数周で評価。
- 実走は広い屋内・低速から。手元で即ニュートラル停止できる体制で。

## 将来拡張（LiDAR）
`localizer.py` の `LidarMCLLocalizer`（現状 `NotImplementedError`）を実装し、
事前作成した地図に対する Monte Carlo Localization で pose を補正すれば、
`reference_path` / `pure_pursuit` / `car_driver` はそのままで地図参照走行に移行できる。
