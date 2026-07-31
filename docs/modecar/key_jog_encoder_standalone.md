# 前進Jog＋エンコーダ速度計測（単体版）
# 前進Jog＋エンコーダ速度計測（単体版）

## 何を直したか

新しいファイルを作成した。

```text
scripts/device_test/rccar_tests/test_encoder/key_jog_encoder_standalone.py
```

このファイルだけで動作し、`encoder_speed_test.py`を読み込まない。そのため、2ファイルの版違いによる次のエラーは発生しない。

```text
TypeError: __init__() got an unexpected keyword argument 'fixed_direction'
```

元のファイルは変更していない。

## 設定値

| 項目 | 値 |
|---|---:|
| ESC信号 | BCM GPIO 12 |
| ステアリング信号 | BCM GPIO 13 |
| PWM周波数 | 70 Hz |
| ESC中立 | 10.300 % |
| ステアリング中立 | 10.895 % |
| 前進下限 | 10.100 % |
| 1操作の刻み | 0.020 % |
| エンコーダA相 | BCM GPIO 22 |
| エンコーダB相 | BCM GPIO 27 |
| カウント数 | 36 count/rev |
| タイヤ直径 | 0.066 m |

速度設定は変更していない。

## エンコーダの数え方

この試験は前進専用である。A相の立ち上がりを常に正の1カウントとして記録する。高速時に誤判定していたB相は方向判定に使わない。

したがって、正常な前進試験では次が正に増える。

```text
encoder_count
encoder_distance_m
encoder_speed_mps
```

この方法では後退方向を判定できない。前進速度の確認だけに使用する。

## Raspberry Piへ置くファイル

次の1ファイルだけをコピーする。

```text
key_jog_encoder_standalone.py
```

Raspberry Pi側の配置例:

```text
~/OpenMiniCarWorks/scripts/encoder/key_jog_encoder_standalone.py
```

## PC側・出力なし確認

```bash
python3 -m py_compile key_jog_encoder_standalone.py
python3 key_jog_encoder_standalone.py
```

2番目のコマンドは設定を表示するだけで、GPIOやPWMへアクセスしない。

## 駆動輪リフト試験

実機出力前に、駆動輪を床から浮かせ、物理電源カットへ手が届くことを確認する。エンコーダ出力は3.3 V互換とし、Raspberry Pi、エンコーダ、ESC信号のGNDを共通にする。

```bash
python3 key_jog_encoder_standalone.py \
  --enable-hardware \
  --confirm-wheels-lifted \
  --confirm-power-cutoff \
  --confirm-forward-duty-decreases \
  --confirm-forward-duty-limit \
  --confirm-3v3-compatible \
  --confirm-common-ground
```

操作順:

1. `r`でarmする。この時点では動かない。
2. `w`を1回ずつ押す。ESC Duty比が`0.020 %`ずつ下がる。
3. 緊急時は`n`を押す。
4. `Enter`または`q`で終了する。

正常終了、時間上限、Ctrl-C、例外のいずれでも、ESCを`10.300 %`、ステアリングを`10.895 %`へ戻す。

## 合格条件

- 車輪が物理的に前進する。
- `encoder_count`と`encoder_distance_m`が正に増える。
- 回転中の`encoder_speed_mps`が主に正になる。
- 終了行が`neutral_exit:...`になる。
- 終了時にESCが`10.300 %`、ステアリングが`10.895 %`になる。

この確認が終わるまでは床へ降ろして走行させない。
