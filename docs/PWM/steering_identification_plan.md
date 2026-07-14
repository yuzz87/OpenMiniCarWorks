# ステアリング同定実験計画書

## 目的

ステアリングサーボへ入力するPWM duty比[%]と、実車の前輪ステア角[rad]の対応関係を測定する。

最終的に次の変換式を作る。

```text
ステアリング角[rad] -> ステアリングduty比[%]
```

制御プログラムでは目標ステアリング角[rad]を扱うため、実車へ出力する前にduty比[%]へ変換できるようにする。この仕様書をmd fileとして作成して

## 前提

- PWM周波数は `70 Hz` とする。
- ステアリング中立の初期値は `10.88 %` とする。
- ESCは常に中立にし、同定中は車両を走行させない。
- GPIO番号や中立値は車両固有の校正値として扱う。
- 角度は測定時に度[deg]で記録してよいが、解析ではラジアン[rad]も使う。

## 安全条件

- 駆動輪を床から浮かせる。
- ESCは中立 duty比[%]を出す。
- モーターが回る状態でステアリング同定を行わない。
- Raspberry Pi、ESC/BEC、サーボのGNDを共通にする。
- サーボやモーターをRaspberry PiのGPIOや3.3 Vピンから給電しない。
- `pigpiod` は実機出力時だけ起動する。
- すぐに電源を切れる物理スイッチまたはコネクタを準備する。

## 使用する値

| 項目 | 値 | 単位 | 備考 |
| --- | ---: | --- | --- |
| PWM周波数 | 70 | Hz | ESC/サーボ信号 |
| ステアリング中立 | 10.88 | % | 実車で再確認する |
| ESC中立 | 10.55 | % | 同定中は中立固定 |
| ステアリングGPIO | 13 | BCM GPIO | 現在の `machine.py` 設定 |
| ESC GPIO | 12 | BCM GPIO | 現在の `machine.py` 設定 |

## 測定するduty比

最初は中立付近から小さく振る。

```text
10.48, 10.58, 10.68, 10.78, 10.88, 10.98, 11.08, 11.18, 11.28
```

サーボが機械的に当たる、異音が出る、リンクに無理がある場合は、その時点で停止する。

## 実験手順

1. 車両を台に載せ、前輪が自由に動く状態にする。
2. ESCを中立 duty比[%]に固定する。
3. ステアリングへ `10.88 %` を出し、前輪が直進方向になるか確認する。
4. 中立がずれている場合は、まず中立 duty比[%]を調整する。
5. 測定するduty比[%]を1つずつステアリングへ出す。
6. 各duty比[%]で前輪ステア角を測る。
7. 角度を度[deg]とラジアン[rad]で記録する。
8. 測定が終わったら、ステアリングとESCを中立へ戻す。

## 記録フォーマット

CSV形式で記録する。

```csv
str_duty_percent,steer_angle_deg,steer_angle_rad,memo
10.48,-8.0,-0.139626,
10.58,-6.0,-0.104720,
10.68,-4.0,-0.069813,
10.78,-2.0,-0.034907,
10.88,0.0,0.000000,neutral
10.98,2.1,0.036652,
11.08,4.2,0.073304,
11.18,6.3,0.109956,
11.28,8.4,0.146608,
```

ラジアン変換は次の式を使う。

```text
steer_angle_rad = steer_angle_deg * pi / 180
```

## 解析方法

最初は線形近似で十分とする。

```text
steer_angle_rad = a * str_duty_percent + b
```

制御で使う逆変換は次になる。

```text
str_duty_percent = (steer_angle_rad - b) / a
```

左右で特性が非対称な場合は、中立より左側と右側で別々の近似式にする。

```text
左側: steer_angle_rad = a_left * duty + b_left
右側: steer_angle_rad = a_right * duty + b_right
```

## 成功条件

- 中立 duty比[%]で前輪が直進方向になる。
- 測定範囲内でサーボやリンケージが機械的に当たらない。
- duty比[%]を増減したとき、ステア角[rad]が単調に変化する。
- 同じduty比[%]を複数回出したとき、角度のばらつきが小さい。
- 作成した近似式で、目標ステア角[rad]からduty比[%]を計算できる。

## 次に行う実装

1. ステアリング専用の同定スクリプトを用意する。
2. ESCは常に中立へ固定する。
3. ステアリングduty比[%]だけを変更できるようにする。
4. 終了時は必ずESCとステアリングを中立へ戻す。
5. 測定結果から `steer_angle_rad -> str_duty_percent` の変換関数を作る。

## 注意

この実験は静的なステアリング角の同定であり、実走時のタイヤすべり、サーボ遅れ、リンクのバックラッシュは含まない。
実走確認は別実験として、低速かつ広い場所で行う。

## 実装プログラム

ステアリング同定で使用するプログラムは、次のディレクトリに置く。

```text
scripts/device_test/rccar_tests/test_PWM/pigpio
```

### pigpio_connection_check.py

pigpioデーモンに接続できるか確認するプログラムである。

確認する内容:

- `pigpiod` が起動しているか。
- Pythonからpigpioへ接続できるか。
- 必要に応じて、指定GPIOへ中立パルス幅[us]を出力できるか。

通常の接続確認ではGPIOへ出力しない。

```python
USE_GPIO_OUTPUT_TEST = False
```

GPIO信号をオシロスコープやロジックアナライザで確認する場合だけ、次を有効にする。

```python
USE_GPIO_OUTPUT_TEST = True
```

実行例:

```bash
cd scripts/device_test/rccar_tests/test_PWM/pigpio
python3 pigpio_connection_check.py
```

### steering_identification.py

ステアリング同定用の実機スクリプトである。

役割:

- ESCを中立 duty比[%]に固定する。
- ステアリングだけを `a` / `d` キーで動かす。
- `n` キーでステアリングを中立へ戻す。
- 現在の `str_duty_percent` と `str_pulse_us` を表示する。
- 終了時にESCとステアリングを中立へ戻す。

実車へ出力する場合は、次を有効にする。

```python
USE_HARDWARE = True
```

操作:

```text
a     ステアリングduty比[%]を小さくする
d     ステアリングduty比[%]を大きくする
n     ステアリングを中立へ戻す
Enter 終了
```

実行例:

```bash
cd scripts/device_test/rccar_tests/test_PWM/pigpio
python3 steering_identification.py
```

### steering_data.csv

`steering_identification.py` で表示された値と、測定したステア角を記録するCSVである。

例:

```csv
str_pulse_us,str_duty_percent,steer_angle_deg,steer_angle_rad,memo
1554.3,10.8800,0.0,0.0,neutral_candidate
1555.7,10.8900,0.0,0.0,neutral_selected
1557.1,10.9000,0.0,0.0,neutral_candidate
```

中立だけを確認する場合は、`steer_angle_deg` と `steer_angle_rad` を `0.0` として記録してよい。

ただし、すべての角度が `0.0` の場合は、ステア角[rad]からPWMへの変換式は作れない。
この場合は中立 duty比[%]と中立パルス幅[us]だけを決める。

### steering_fit.py

`steering_data.csv` からステアリング変換式を作る解析プログラムである。

通常の角度データがある場合は、次の近似式を求める。

```text
steer_angle_rad = a * str_pulse_us + b
```

すべての角度が `0.0` の場合は、中立専用データとして扱い、中立候補を表示する。

実行例:

```bash
cd scripts/device_test/rccar_tests/test_PWM/pigpio
python3 steering_fit.py
```

### steering_check.py

`steering_fit.py` で求めた変換式、または中立パルス幅[us]を実車で確認するプログラムである。

中立だけを確認する場合は、次を使う。

```python
USE_NEUTRAL_ONLY = True
NEUTRAL_PULSE_US = 1555.7
TARGET_STEER_RAD = 0.0
```

角度変換式を確認する場合は、`steering_fit.py` の結果を転記する。

```python
FIT_A = ...
FIT_B = ...
```

実車へ出力する場合は、次を有効にする。

```python
USE_HARDWARE = True
```

実行例:

```bash
cd scripts/device_test/rccar_tests/test_PWM/pigpio
python3 steering_check.py
```

## 実行順序

中立だけを確認する場合:

```text
1. pigpio_connection_check.py でpigpio接続を確認する。
2. steering_identification.py で中立付近のstr_duty_percentとstr_pulse_usを取る。
3. steering_data.csv に中立候補を記録する。
4. steering_fit.py で中立候補を確認する。
5. steering_check.py で中立パルス幅[us]を実車確認する。
6. 問題なければ PWM_NEUTRAL_STR に反映する。
```

ステア角[rad]への変換式まで作る場合:

```text
1. pigpio_connection_check.py でpigpio接続を確認する。
2. steering_identification.py で複数のstr_duty_percentとstr_pulse_usを取る。
3. 各値で前輪ステア角[deg]または[rad]を測定する。
4. steering_data.csv に測定値を記録する。
5. steering_fit.py で変換式を作る。
6. steering_check.py で目標ステア角[rad]を実車へ出して確認する。
7. 誤差が許容範囲なら制御プログラムへ反映する。
```
