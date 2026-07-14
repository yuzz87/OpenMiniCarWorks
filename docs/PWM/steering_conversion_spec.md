# ステアリング変換式作成・検証仕様書

## 目的

ステアリング同定実験で取得したデータから、目標ステア角[rad]をステアリングPWM指令へ変換する式を作成し、実車で妥当性を確認する。

最終的に使う変換は次である。

```text
目標ステア角[rad] -> パルス幅[us] -> duty比[%]
```

## 入力データ

同定実験後、次の形式でCSVに整理する。

```csv
str_pulse_us,str_duty_percent,steer_angle_deg,steer_angle_rad,memo
1490,10.43,-8.0,-0.139626,
1520,10.64,-4.0,-0.069813,
1550,10.85,0.0,0.000000,neutral
1580,11.06,4.2,0.073304,
1610,11.27,8.5,0.148353,
```

角度は測定時に度[deg]でもよいが、変換式ではラジアン[rad]を使う。

```text
steer_angle_rad = steer_angle_deg * pi / 180
```

## 基本方針

ステアリングサーボはduty比[%]よりもパルス幅[us]で扱う方が分かりやすい。

そのため、近似式はまず次の形で作る。

```text
steer_angle_rad = a * str_pulse_us + b
```

制御で使うときは逆変換する。

```text
str_pulse_us = (target_steer_angle_rad - b) / a
```

PWM周波数が `70 Hz` の場合、パルス幅[us]からduty比[%]への変換は次である。

```text
str_duty_percent = str_pulse_us * 70 / 10000
```

## 解析手順

1. 測定CSVを作成する。
2. `str_pulse_us` と `steer_angle_rad` の散布図を作る。
3. 中立付近で単調に変化しているか確認する。
4. 線形近似で係数 `a`, `b` を求める。
5. 逆変換式を作る。
6. いくつかの目標ステア角[rad]を入力し、パルス幅[us]とduty比[%]を計算する。
7. 実車へ出力し、実際のステア角[rad]を測定する。
8. 目標値と実測値の誤差を評価する。

## 左右差への対応

左右で特性が異なる場合は、中立を境に近似式を分ける。

```text
左側: steer_angle_rad = a_left * str_pulse_us + b_left
右側: steer_angle_rad = a_right * str_pulse_us + b_right
```

制御時は目標ステア角[rad]の符号で使う式を切り替える。

```text
target_steer_angle_rad < 0 -> 左側の式
target_steer_angle_rad >= 0 -> 右側の式
```

## 検証データ

変換式を作った後、次の形式で検証結果を記録する。

```csv
target_steer_angle_rad,command_pulse_us,command_duty_percent,measured_steer_angle_rad,error_rad,memo
-0.100,1510,10.57,-0.096,0.004,
-0.050,1530,10.71,-0.052,-0.002,
0.000,1550,10.85,0.003,0.003,neutral
0.050,1570,10.99,0.047,-0.003,
0.100,1590,11.13,0.104,0.004,
```

誤差は次で計算する。

```text
error_rad = measured_steer_angle_rad - target_steer_angle_rad
```

## 合格目安

最初のMVPでは、静的な前輪角度で次を満たせば使用可能とする。

```text
abs(error_rad) <= 0.03 rad
```

`0.03 rad` は約 `1.7 deg` である。

より高精度にしたい場合は、次を確認する。

- 中立付近の誤差が小さい。
- 左右の最大角付近でサーボやリンケージが機械的に当たらない。
- 同じ指令を複数回出したときのばらつきが小さい。
- 左右で必要なら別々の近似式を使う。

## 実装方針

変換関数は次の形にする。

```python
def steer_rad_to_pulse_us(target_steer_rad):
    return (target_steer_rad - b) / a


def pulse_us_to_duty_percent(pulse_us, pwm_hz=70):
    return pulse_us * pwm_hz / 10000.0
```

左右別近似を使う場合は次の形にする。

```python
def steer_rad_to_pulse_us(target_steer_rad):
    if target_steer_rad < 0:
        return (target_steer_rad - b_left) / a_left
    return (target_steer_rad - b_right) / a_right
```

## 注意事項

- この仕様は静的なステアリング角の変換式を作るためのものである。
- 実走時のタイヤすべり、サーボ応答遅れ、バックラッシュは別途確認する。
- 実車へ出力するときは、ESCを中立にし、駆動輪を浮かせて確認する。
- 最終的な実走確認は低速、短距離、物理的に停止できる状態で行う。
