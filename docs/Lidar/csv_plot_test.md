# RPLidar CSV保存・プロット確認仕様書

## 目的

RPLidar A1M8 のスキャンデータをCSVに保存し、2Dプロットで距離、角度方向、欠測、外れ値を確認する。

この段階ではLiDAR単体の計測確認のみを行い、GPIO、pigpio、ESC、ステアリングPWM、実車走行制御には接続しない。

## 対象ファイル

現在の接続確認スクリプトは次である。

```text
scripts/device_test/rccar_tests/test_lidar/RPlidarA1M8_test.py
```

CSV保存とプロット確認は、既存の接続確認を壊さないように別スクリプトとして作成する。

```text
scripts/device_test/rccar_tests/test_lidar/rplidar_csv_plot_test.py
```

## 前提

- LiDARはRaspberry PiまたはPCにUSB接続され、`/dev/ttyUSB0` として認識されている。
- `rplidar` Pythonパッケージが使用できる。
- CSV保存にはPython標準ライブラリを使う。
- PNGプロット作成には `matplotlib` を使う。`matplotlib` が無い場合はCSV保存だけ実行し、プロットをスキップする。
- 距離はメートル[m]で扱う。
- 角度はCSVと内部計算ではラジアン[rad]で扱う。
- LiDARライブラリから得られる角度が度[deg]の場合は、保存前にラジアン[rad]へ変換する。

## 入力

LiDARから `iter_scans()` で取得する1スキャン分の測定値を入力とする。

`rplidar` の測定値は一般に次の形で返る。

```python
(quality, angle_deg, distance_mm)
```

各値の扱いは次とする。

| 値 | 入力単位 | 保存単位 | 説明 |
| --- | --- | --- | --- |
| `quality` | なし | なし | LiDAR測定品質 |
| `angle_deg` | deg | rad | LiDAR座標系での測定角 |
| `distance_mm` | mm | m | LiDARから対象物までの距離 |

## 出力ファイル

出力先はLiDARテストスクリプトと同じディレクトリにする。

```text
scripts/device_test/rccar_tests/test_lidar/lidar_scan.csv
scripts/device_test/rccar_tests/test_lidar/lidar_scan.png
```

CSVファイルは実測ログなので、通常はGit管理対象にしない。

## CSV形式

CSVはヘッダ行付きとし、1行を1測定点とする。

```csv
scan_index,sample_index,timestamp_s,quality,angle_rad,range_m,x_m,y_m
0,0,1782800000.000000,15,0.000000000,1.234000,1.234000,0.000000
0,1,1782800000.000000,14,0.017453293,1.250000,1.249810,0.021815
```

| カラム | 型 | 単位 | 説明 |
| --- | --- | --- | --- |
| `scan_index` | int | なし | `iter_scans()` から取得したスキャン番号 |
| `sample_index` | int | なし | 1スキャン内の測定点番号 |
| `timestamp_s` | float | s | スキャン取得時刻。UNIX時刻を使う |
| `quality` | int | なし | LiDAR測定品質 |
| `angle_rad` | float | rad | LiDAR座標系の測定角 |
| `range_m` | float | m | LiDARから対象物までの距離 |
| `x_m` | float | m | `range_m * cos(angle_rad)` |
| `y_m` | float | m | `range_m * sin(angle_rad)` |

`x_m`, `y_m` はLiDAR座標系での点群確認用である。車体座標系への変換はこの仕様の対象外とする。

## 実行仕様

初期値は安全側で短時間の確認にする。

```text
device: /dev/ttyUSB0
max_scans: 10
min_range_m: 0.05
max_range_m: 12.0
csv_path: lidar_scan.csv
png_path: lidar_scan.png
```

実行コマンド例は次である。

```bash
cd scripts/device_test/rccar_tests/test_lidar
python3 rplidar_csv_plot_test.py
```

引数対応を追加する場合は次を基本とする。

```bash
python3 rplidar_csv_plot_test.py --device /dev/ttyUSB0 --max-scans 10 --csv lidar_scan.csv --png lidar_scan.png
```

## 処理手順

1. `RPLidar(device)` でLiDARへ接続する。
2. `get_info()` と `get_health()` を表示する。
3. `iter_scans()` で指定スキャン数を取得する。
4. 各測定点について、距離をメートル[m]へ変換する。
5. 各測定点について、角度をラジアン[rad]へ変換する。
6. `min_range_m <= range_m <= max_range_m` を満たす点だけCSVへ保存する。
7. 保存した点から `x_m`, `y_m` を計算する。
8. CSV保存後、可能ならPNGプロットを作成する。
9. 終了時は必ず `stop()`, `stop_motor()`, `disconnect()` を呼ぶ。

## プロット仕様

PNGはLiDAR座標系のXY散布図とする。

- 横軸は `x_m` [m]。
- 縦軸は `y_m` [m]。
- アスペクト比は1:1にする。
- 原点 `(0 m, 0 m)` をLiDAR位置とする。
- グリッドを表示する。
- タイトルにスキャン数と保存点数を表示する。

角度方向確認のため、LiDARの `0 rad` 方向をプロット上で分かるようにする。

## 確認項目

実行後、次を確認する。

- CSVにヘッダ行と測定点が保存されている。
- `range_m` がメートル[m]として妥当な値になっている。
- `angle_rad` が `0 rad` 以上 `2*pi rad` 未満の範囲に入っている。
- 近くの壁や箱の形がPNG上で実際の配置に近く見える。
- LiDARの `0 rad` 方向が車体のどちらを向くか確認できる。
- 角度増加方向が時計回りか反時計回りか確認できる。
- 欠測や極端な外れ値が多すぎない。

## 合格目安

静止状態で次を満たせば、次段階の座標変換確認へ進める。

- 10スキャン分のCSVを保存できる。
- PNGプロットを作成できる、または `matplotlib` 未導入時にCSV保存だけ正常終了できる。
- 既知の壁や箱までの距離誤差が概ね `0.10 m` 以内である。
- LiDARの向きと角度増加方向を説明できる。
- 終了後にLiDARモータが停止し、USB接続が解放される。

## 安全上の注意

- このテストではESC、ステアリングサーボ、GPIO、pigpioを使わない。
- 自動走行制御や `ellipse_run` にはまだ接続しない。
- LiDARを車体に取り付けて確認する場合でも、車両の駆動電源は切ってよい。
- USBケーブルやLiDAR本体が回転部、タイヤ、ギアに触れないように固定する。

## 次の段階

CSV保存とプロット確認後、次を記録する。

```text
lidar_x_m
lidar_y_m
lidar_yaw_rad
```

これらは車体基準点から見たLiDAR取り付け位置と向きである。角度はラジアン[rad]で記録する。

次段階では、LiDAR座標系の点 `x_m`, `y_m` を車体座標系へ変換し、ログ再生で同じ処理を確認できるようにする。
