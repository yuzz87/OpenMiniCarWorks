# 現機体で先輩MPC実験を再開するための情報整理

作成日: 2026-07-13

## 1. 目的

先輩のSimulink / Python MPC実験を現在のRCカーで再開し、最終的に次を確認する。

1. Motiveで取得した実車状態をMPCへ入力する。
2. 直線参照に沿って前進する。
3. 指定した目標位置付近で停止する。
4. MPC要求値、実車へ適用したPWM、Motive状態、エンコーダ計測を同じ実験として保存する。
5. シミュレーション結果と実車結果を比較する。

この文書は情報整理のみを目的とし、MPC、Simulink、Raspberry Piのコードや設定は変更しない。

## 2. 情報の優先順位

現在の資料には過去の途中設定と最新の実測値が混在している。再開時は次の順で扱う。

1. 2026-07-13に現在の機体で確認した実測値
2. 現在使用中の個別試験スクリプトの設定
3. 先輩MPC実験の記録にある通信構成と計算構成
4. 古い速度変換式や古い安全上限は参考情報

特に、過去文書にある`0.30 m/s`はRaspberry Pi受信コードのソフトウェア上限であり、現在の機体で新たに測定した物理的な最高速度ではない。

## 3. 先輩実験のデータ経路

確認できている構成は次のとおり。

```text
Motive
  -> Simulinkで状態を作成
  -> localhost UDP 20000
     little-endian float32 x 5
     [flag, phi, x, y, psi]

Python Notebook MPC
  -> 状態 [phi, x, y, psi] を使用
  -> 最適入力 [v, omega] を計算
  -> localhost UDP 5005
     little-endian float32 x 6
     [v, omega, phi, x, y, psi]

Simulink
  -> 実機用の旧形式へ変換
  -> Raspberry Pi UDP 5005
     little-endian float64 x 3
     [raw1, raw2, raw3]

Raspberry Pi
  -> 旧形式を速度・ステア角へ変換
  -> PWM duty比[%]へ変換
  -> ESCとステアリングへ出力
```

PythonからSimulinkへの`5005`と、SimulinkからRaspberry Piへの`5005`は、送信先ホストが異なる別の通信である。

また、どちらも24 byteだが内容は異なる。

| 区間 | 型 | 内容 |
|---|---|---|
| Python -> Simulink | `float32 x 6` | `[v, omega, phi, x, y, psi]` |
| Simulink -> Raspberry Pi | `float64 x 3` | `[raw1, raw2, raw3]` |

## 4. 先輩MPCの確認済み仕様

### 4.1 状態と入力

```text
状態 = [phi, x, y, psi]
入力 = [v, omega]
```

| 記号 | 意味 | 単位 |
|---|---|---|
| `phi` | 車体方位 | rad |
| `x`, `y` | 平面位置 | m |
| `psi` | 前輪舵角 | rad |
| `v` | 車速 | m/s |
| `omega` | 前輪舵角速度 | rad/s |

`omega`は車体ヨーレートでも前輪舵角そのものでもない。

### 4.2 車両モデル

```text
phi_dot = v / L * tan(psi)
x_dot   = v * cos(phi)
y_dot   = v * sin(phi)
psi_dot = omega
```

現在のコード値:

```text
L = 0.25 m
```

`0.25 m`は現在の機体で実測済みとは確認できていないため、暫定値として扱う。

### 4.3 MPC設定

```text
SimTime = 7 s
予測時間 T = 0.4 s
予測分割 K = 40
モデル刻み dt = 0.01 s
```

入力制約:

```text
-0.1 m/s <= v <= 1.2 m/s
-0.70 rad/s <= omega <= 0.70 rad/s
```

前輪舵角の状態制約:

```text
-40 deg <= psi <= 40 deg
```

現在の実車で確認している操舵範囲は主に`±18 deg`以内であり、MPCの`±40 deg`とは一致していない。

### 4.4 参照軌道

既定の参照:

```text
開始状態 = [0 rad, 0 m, -2 m, 0 rad]
進行方向 = x正方向
v_ref     = 0.4 m/s
goal_dist = 4.0 m
```

`v_ref`は参照位置を時間とともに進める値であり、MPC入力`v`を直接`0.4 m/s`へ固定する値ではない。

現在の設定には時間と距離の不一致がある。

```text
4.0 m / 0.4 m/s = 10 s
SimTime          = 7 s
```

そのため、現在のコードは4.0 m地点へ到達する前に終了する。`t_eval = 0.00 ... 6.99 s`なら参照終端は約`2.796 m`であり、4.0 m地点での停止実験にはなっていない。

## 5. 現在の機体で確認済みの実機設定

| 項目 | 現在値 |
|---|---:|
| ESC信号 | BCM GPIO 12 |
| ステアリング信号 | BCM GPIO 13 |
| PWM周波数 | 70 Hz |
| ESC中立 | `10.300 %` |
| ステアリング中立 | `10.895 %` |
| 前進方向 | ESC duty比を下げる |
| 現在確認済みの最小ESC duty比 | `10.100 %` |
| エンコーダA相 | BCM GPIO 22 |
| エンコーダB相 | BCM GPIO 27 |
| 暫定カウント数 | `36 count/rev` |
| タイヤ直径 | `0.066 m` |
| 1カウント距離 | 約`0.005759587 m` |

`10.100 %`より小さいESC duty比は、現在確認済みの前進上限を強める変更になるため使用しない。

## 6. 現在の床走行実測値

現在得られている対応は2点である。

| ESC duty比 | エンコーダ車輪周速度 | 実車観察 |
|---:|---:|---|
| `10.160 %` | 終盤約`0.37 m/s` | 完全に走行開始 |
| `10.100 %` | 終盤約`0.61 m/s` | 連続走行 |

この速度はエンコーダから計算した車輪周速度であり、Motiveで測定した車体速度ではない。タイヤ空転、タイヤ変形、床面、バッテリー電圧の影響を含む。

2点だけなので、ESC duty比と車体速度の一般的な線形変換式はまだ確定しない。

### 中立指令後の車輪回転

| 走行duty比 | 中立直前の速度 | 中立後の追加車輪回転相当距離 |
|---:|---:|---:|
| `10.160 %` | 約`0.355 m/s` | 約`0.0864 m` |
| `10.100 %` | 約`0.615 m/s` | 約`0.236 m` |

目標位置で停止する実験では、この惰性相当分を無視できない。ただし、これもMotiveで測定した車体の実停止距離ではない。

## 7. エンコーダの現在の扱い

現在の前進専用試験では次の方式を使用している。

```text
A相立ち上がりを常に +1 count
B相は方向判定に使用しない
```

理由は、高速時にPythonコールバック内でB相を読む方式では、前進中でも速度符号が正負に交互反転したためである。

この方式で前進速度は安定したが、次は判定できない。

- 後退方向
- 停止後のわずかな逆回転
- 前後振動

MPC実験ではエンコーダを補助ログとして使い、車体位置の基準はMotiveとする。

## 8. 既存のRaspberry Pi受信コード

対象:

```text
UDP/legacy_double3_rc_pwm_receiver.py
```

受信形式:

```text
little-endian float64 x 3
[raw1, raw2, raw3]
```

現在の解釈:

```text
target_speed_mps
  = average(raw1, raw2) * speed_per_legacy_unit

target_steer_deg
  = legacy_steer_a * raw3 + legacy_steer_b
```

過去のMPC床走行で採用されたオプション値:

```text
speed_per_legacy_unit = 0.0090
max_speed_mps         = 0.38 m/s
legacy_steer_b        = 70.9136
esc_neutral_duty      = 10.3 %
```

この条件では、MPCチェーンからのUDP受信、PWM出力、床上前進、停止復帰、概ね直進することまで確認された記録がある。

ただし、現在の実機校正としてそのまま確定できない。

### 8.1 速度変換が古い

受信コード内の速度からESC duty比への変換は次である。

```text
speed_mps = -2.4618 * esc_duty_percent + 25.347
```

この式は今回の床走行2点から求めたものではない。

過去ログでは次の表示だった。

```text
target_speed_mps = 約0.355 m/s
esc_duty         = 約10.152 %
```

しかし、現在の実測では`10.160 %`で車輪周速度が約`0.37 m/s`である。したがって、ログ上の`target_speed_mps`を現在の実車速度の実測値として扱わない。

### 8.2 ESC中立の既定値が異なる

コードの既定値:

```text
DEFAULT_ESC_NEUTRAL_DUTY = 10.55 %
```

現在の機体で使用する値:

```text
ESC neutral = 10.300 %
```

旧受信コードを使用する場合は、既定値任せにせず`10.300 %`を明示する必要がある。

### 8.3 ステアリングのゼロ点が異なる

現在の角度変換式では、目標ステア角`0 rad`から次が計算される。

```text
steering duty = 約10.8064 %
```

一方、現在の実車で確認した中立は次である。

```text
steering neutral = 10.895 %
```

そのため、現在の受信コードでは次が一致していない。

- 通常走行中の`0 rad`指令: 約`10.8064 %`
- Param_init、watchdog、終了時の中立: `10.895 %`

現在の機体でMPC操舵を行う前に、このゼロ点の扱いを明示的に決める必要がある。

## 9. 先輩実験へ戻る前に解決が必要な項目

### 9.1 PC / Simulink側

- 実際のNotebookファイルとSimulinkモデルは、このリポジトリ内に存在しない。
- 最新実行時の`[FIRST_RX] = [flag, phi, x, y, psi]`が未記録。
- Motive座標からMPC座標への原点、軸、符号、方位ゼロの変換が未確認。
- `psi [rad]`をSimulinkがどのように取得しているか未確認。
- `omega [rad/s]`から`raw3`への変換が未確認。
- Python MPCの求解時間と実際の制御周期が未確認。
- Python停止時にSimulinkが最後の指令を保持するか未確認。

### 9.2 MPC設定

- 前進専用実験に対して、MPCが`v >= -0.1 m/s`を許している。
- MPC速度上限`1.2 m/s`は現在の実機確認範囲と一致しない。
- MPC操舵角範囲`±40 deg`は現在の確認範囲`±18 deg`より大きい。
- `4.0 m`、`0.4 m/s`、`7 s`では目標位置での停止を確認できない。
- 目標位置到達後にESC中立を保証する明示的な停止処理がない。
- `L = 0.25 m`が現在の機体の実測ホイールベースか未確認。

### 9.3 Raspberry Pi / 実機側

- 今回の床実測値に基づく`v [m/s]`からESC duty比[%]への変換は未確定。
- ステアリング`0 rad`と実測中立`10.895 %`が一致していない。
- 既存MPC受信コードにはエンコーダログが統合されていない。
- Motive車体速度とエンコーダ車輪周速度の差が未確認。

## 10. 現時点で確定してよい基準

```text
ESC neutral                 = 10.300 %
steering neutral            = 10.895 %
forward direction           = ESC duty比を下げる
strongest confirmed command = 10.100 %
initial low-speed reference = 10.160 %付近
encoder                      = 36 count/rev, diameter 0.066 m
```

`10.160 %`は現在の床条件で約`0.37 m/s`の車輪周速度だったため、先輩参照の`0.4 m/s`に比較的近い確認済み指令である。ただし、車輪周速度とMotive車体速度はまだ同一視しない。

## 11. 再開時の最初の確認対象

実車PWMを出す前に、先輩のPC / Simulink / PythonチェーンをDRYで再接続し、1回のログへ次を記録する。

```text
実時刻
FIRST_RX: flag, phi, x, y, psi
参照状態
MPC要求: v, omega
IPOPT成功状態
solve time
Simulink変換後: raw1, raw2, raw3
Raspberry Pi変換後: target_speed_mps, target_steer_rad
計算されたESC duty比、steering duty比
statusと停止理由
```

このDRY確認により、現在の機体校正を変更する前に、次を分離できる。

1. Motive座標と参照開始位置の問題
2. MPCが出す`v`と`omega`の問題
3. Simulink内の旧形式変換の問題
4. Raspberry Pi側の速度・操舵変換の問題

DRYで正方向の速度、妥当な操舵、終了時中立が確認できるまでは、MPCによる実車走行へ進まない。

## 12. 関連ファイル

先輩実験:

```text
docs/senior/current_vehicle_mpc_experiment_plan.md
docs/senior/simulink_raspberry_udp_handoff.md
docs/senior/mpc_udp_send_limit_issue_2026-07-08.md
docs/senior/ipynb/notebook_cell_review.md
docs/senior/ipynb/new_vehicle_mpc.py
UDP/legacy_double3_rc_pwm_receiver.py
```

現在のエンコーダ・床走行:

```text
docs/modecar/encoder_floor_test_result_2026-07-13.md
docs/modecar/encoder_floor_test_run2_2026-07-13.md
scripts/device_test/rccar_tests/test_encoder/key_jog_encoder_floor.py
```
