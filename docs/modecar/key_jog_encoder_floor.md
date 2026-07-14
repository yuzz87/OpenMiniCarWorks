# 床上の直進Jog＋エンコーダ速度計測

## 使用ファイル

```text
scripts/device_test/rccar_tests/test_encoder/key_jog_encoder_floor.py
```

リフト試験用ファイルは変更していない。この床走行用ファイルも、他のPythonファイルを読み込まない単体版である。

## 前提

駆動輪リフト試験では次を確認済み。

- A相カウントが前進中に正方向へ連続して増えた。
- `10.100 %`で無負荷車輪速度は約`1.7〜1.8 m/s`だった。
- 終了時にESCは`10.300 %`、ステアリングは`10.895 %`へ戻った。

床上の車体速度はまだ不明である。車輪スリップがある場合、エンコーダ距離と実際の移動距離は一致しない。

## 設定

| 項目 | 値 |
|---|---:|
| ESC中立 | 10.300 % |
| ステアリング中立 | 10.895 % |
| 前進下限 | 10.100 % |
| Duty刻み | 0.020 % |
| 実行時間上限 | 10.0 s |
| エンコーダ | A=BCM22、B=BCM27 |
| カウント数 | 36 count/rev |
| タイヤ直径 | 0.066 m |

速度設定はリフト試験から変更していない。ステアリング操作は行わず、中立に固定する。

## 出力なし確認

Raspberry Pi側へこのファイル1本だけを置く。

```text
~/OpenMiniCarWorks/scripts/encoder/key_jog_encoder_floor.py
```

次のコマンドはGPIOやPWMへ出力しない。

```bash
cd ~/OpenMiniCarWorks/scripts/encoder
python3 -m py_compile key_jog_encoder_floor.py
python3 key_jog_encoder_floor.py
```

## 床走行

平坦で十分に広い直線路を使う。人や物を進路から外し、物理電源カットへすぐ手が届く状態にする。

```bash
python3 key_jog_encoder_floor.py \
  --enable-hardware \
  --confirm-floor-clear \
  --confirm-power-cutoff \
  --confirm-forward-duty-decreases \
  --confirm-forward-duty-limit \
  --confirm-steering-neutral \
  --confirm-3v3-compatible \
  --confirm-common-ground
```

操作:

1. 車両前方が空いていることを再確認する。
2. `r`を押してarmする。この時点では動かない。
3. `w`を1回ずつ押す。
4. 停止は`n`、終了は`q`または`Enter`を押す。

異常を感じた場合は、キーボード操作を待たず物理電源を切る。

## ログ

```text
key_jog_encoder_floor_log.csv
```

前進専用のためA相を正に数える。後退方向は判定できない。

- `encoder_speed_mps`: 車輪周速度 `[m/s]`
- `encoder_distance_m`: 車輪回転から計算した累積距離 `[m]`

タイヤの空転、横滑り、タイヤ直径誤差により、実際の車体速度・移動距離との差が生じる。
