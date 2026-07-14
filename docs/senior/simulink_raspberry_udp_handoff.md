# Simulink Raspberry Pi UDP Handoff

作成日: 2026-07-07

更新日: 2026-07-08

2026-07-08時点の未解決問題は、SimulinkまたはPC側のUDP送信直前で `raw1/raw2/raw3` の最終制限が効いていないことである。
詳細は `docs/senior/mpc_udp_send_limit_issue_2026-07-08.md` を参照する。

## 目的

Simulink、Python MPC、Raspberry Pi間のUDP通信確認で分かったことを記録する。
このメモは、下段Simulinkブロック「実機に入力を送信」からRaspberry Piへ送っている値の確認作業の引き継ぎである。

初期段階では、Raspberry Pi側でGPIO、pigpio、ESC、ステアリングPWMには接続せず、UDP受信値の表示だけで確認した。

その後、`UDP/legacy_double3_rc_pwm_receiver.py` の実PWMモードで、現在のRCカーが実際に走ることを確認した。

## 現在分かっている通信経路

### Simulink下段からRaspberry Pi

Simulink下段の「実機に入力を送信」領域にあるUDP Sendが、Raspberry Pi側のUDP受信スクリプトへ値を送っている。

現在確認できている形式:

```text
送信元: 192.168.11.2, 192.168.11.5 など
受信ポート: 5005
データ形式: little-endian float64 x 3
サイズ: 24 bytes
```

送信元IPアドレスはPC側ネットワーク状態で変わる。UDP送信元ポートも毎回変わるため、形式確認では重視しない。

Raspberry Pi側では次で確認する。

```bash
cd /home/ubuntuyuzz/Desktop/OpenMiniCarWorks
python3 -u UDP/float_receive.py
```

現在の `UDP/float_receive.py` は、24 byteのUDPパケットを `double x 3` として受信し、`value_1`, `value_2`, `value_3` として表示する。

### SimulinkとPython MPC

SimulinkとPython MPCの閉ループは動作しており、MPCのログからグラフが取れている。
このグラフが取れていることは、SimulinkとPython MPCの経路が動いていることを示す。

ただし、これはRaspberry Piへ実車用の正しい入力が送れていることを意味しない。
Raspberry Piへ送られているのは、Simulink下段のUDP Sendから出ている別経路の値である。

## これまでの誤読と修正

最初はRaspberry Pi側で、受信データを次のように読んでいた。

```text
float32 x 6
FMT = "<ffffff"
NBYTES = 24
```

このとき、次のような表示が出ていた。

```text
0.0 0.0 0.0 0.0 0.0 3.3515625
```

これは `float32 x 6` として正しい値ではなく、`double x 3` の24 byteを誤って `float32 x 6` として読んだ結果だった。
特に `3.3515625` は、`double` の `90.0` の一部を `float32` として読んだ誤読である。

その後、24 byteのパケットを `double x 3` として読むと、次のように自然な値になった。

```text
0.0 0.0 90.0
```

したがって、現在のRaspberry Pi側受信形式は `double x 3` に合わせている。

## 確認済みの値

Simulink下段からRaspberry Piへ送られている値として、次を確認した。

```text
6.111111111111111 6.111111111111111 85.99757458161532
```

停止時、待機時、または切り替え後には次が送られている。

```text
0.0 0.0 90.0
```

この `0.0 0.0 90.0` は、Simulink下段の `Param_init` の値であると判断した。

現時点の理解:

```text
実行中:  PWM計算側の出力らしき値
待機時:  Param_init = [0, 0, 90]
```

## 重要な未解決点

Simulink下段は「実機に入力を送信」する領域である。
しかし、現在Raspberry Piへ届いている3要素の意味と単位はまだ確定していない。

未確認:

```text
out.PWM(1) = 何か、単位は何か
out.PWM(2) = 何か、単位は何か
out.PWM(3) = 何か、単位は何か
```

現状の値を見る限り、RCカーのESC/ステアリングPWM duty比[%]としてそのまま使うのは危険である。

理由:

```text
6.111... は現在の安全duty範囲より低い可能性がある。
85.997... や 90.0 は角度[deg]のように見え、PWM duty[%]としては不自然である。
1個目と2個目が同じ値なので、同じ信号を重複して送っている可能性がある。
```

RCカー側で現在使っている安全目安:

```text
ステアリング duty: 7.50 % から 13.00 %
ESC duty: 9.50 % から 13.00 %
```

したがって、現在の `double x 3` 受信値を実車PWM出力へ直接接続してはいけない。

## 追加した確認用スクリプト

将来、SimulinkからRaspberry PiへMPCの制御入力を直接送る案として、次のスクリプトを追加した。

```text
UDP/mpc_double_receive.py
```

このスクリプトの想定形式:

```text
little-endian float64 x 2
16 bytes
[target_speed_mps, target_steer_rad]
target_speed_mps: m/s
target_steer_rad: rad
```

実行:

```bash
cd /home/ubuntuyuzz/Desktop/OpenMiniCarWorks
python3 -u UDP/mpc_double_receive.py
```

ただし、現在のSimulink下段は `double x 3 = 24 bytes` を送っているため、このスクリプトを現在のモデルのまま使うと次の表示になる。

```text
unexpected packet size 24 bytes
```

これは正常な拒否であり、エラー原因はSimulink側がまだ2要素ではなく3要素を送っているためである。

## Simulinkを変更しない実車出力候補

Simulinkを変更せず、現在の `double x 3` をRaspberry Pi側でRCカー向けに変換する候補として、次のスクリプトを追加した。

```text
UDP/legacy_double3_rc_adapter.py
UDP/legacy_double3_rc_pwm_receiver.py
```

`legacy_double3_rc_adapter.py` はドライラン専用で、GPIO/PWMには触らない。
現在のSimulink値を受けて、RCカー向けの速度、ステア角、PWM duty比を表示する。

実行例:

```bash
cd /home/ubuntuyuzz/Desktop/OpenMiniCarWorks
python3 -u UDP/legacy_double3_rc_adapter.py --speed-per-legacy-unit 0.01636
```

この仮係数では、旧形式のモータ値 `6.111111111` を約 `0.10 m/s` として扱う。

確認できた変換例:

```text
raw=(6.111111111, 6.111111111, 85.997574582)
target_speed_mps=0.099977778 m/s
target_steer_deg=3.2984 deg
target_steer_rad=0.057567940 rad
steering_duty=10.498187 %
esc_duty=10.255513 %
status=ok
```

`Param_init` の値は次である。

```text
raw=(0.0, 0.0, 90.0)
```

実車出力候補の `legacy_double3_rc_pwm_receiver.py` では、この `Param_init` パケットを変換式に通さず、中立PWMとして扱う。

```text
steering_duty=10.895000 %
esc_duty=10.550000 %
status=param_init_neutral
```

`legacy_double3_rc_pwm_receiver.py` もデフォルトはドライランである。
実PWM出力は次のすべてを明示した時だけ有効になる。

```text
--enable-hardware
--confirm-wheels-lifted
--confirm-power-cutoff
--speed-per-legacy-unit 0.01636
```

実車出力前に、GPIO番号が実配線と一致していることを必ず確認する。
このスクリプトのデフォルトGPIOは、現在のステアリング確認値に合わせている。

```text
ESC signal: BCM GPIO 12
Steering signal: BCM GPIO 13
PWM frequency: 70 Hz
```

ドライラン確認:

```bash
cd /home/ubuntuyuzz/Desktop/OpenMiniCarWorks
python3 -u UDP/legacy_double3_rc_pwm_receiver.py --speed-per-legacy-unit 0.01636
```

2026-07-08時点で実走確認できた設定:

```text
speed-per-legacy-unit: 0.03872
esc-neutral-duty: 10.3 %
raw=(6.111111111, 6.111111111, 85.997574582)
target_speed_mps=0.236622222 m/s
target_steer_rad=0.057567940 rad
target_steer_deg=3.2984 deg
steering_duty=10.498187 %
esc_duty=10.200007 %
status=ok
結果: 実PWM出力で実際に走ることを確認した
追加確認: 地面に接地した状態でも走行することを確認した
```

通信途絶時のwatchdog確認:

```text
確認日: 2026-07-08
条件: 駆動輪を浮かせて実PWM出力中に、Raspberry Pi側のUDP 5005受信を遮断
確認方法: iptablesでUDP 5005をDROP
直前状態: status=ok, esc_duty=10.200007 %
watchdog後: status=watchdog_neutral
中立出力: steering_duty=10.895000 %, esc_duty=10.300000 %
結果: 通信途絶時に中立へ戻り、実機挙動も正常に停止することを確認した
```

ステアリング方向確認:

```text
確認日: 2026-07-08
条件: ESC中立、駆動輪を浮かせた状態でステアリングのみ指令
+15 deg: target_steer_rad=0.261799388 rad, steering_duty=9.404784 %, 左に切れる
-15 deg: target_steer_rad=-0.261799388 rad, steering_duty=12.207999 %, 右に切れる
送信停止後: status=watchdog_neutralで中立へ戻る
結果: 正のステア角は左、負のステア角は右として動作することを確認した
```

実走確認時の表示例:

```text
PWM sender=192.168.11.2:63641 raw=(6.111111111, 6.111111111, 85.997574582) target_speed_mps=0.236622222 m/s target_steer_rad=0.057567940 rad target_steer_deg=3.2984 deg steering_duty=10.498187 % esc_duty=10.200007 % status=ok
```

実車出力する場合の基準コマンド:

```bash
python3 -u UDP/legacy_double3_rc_pwm_receiver.py \
  --speed-per-legacy-unit 0.03872 \
  --esc-neutral-duty 10.3 \
  --enable-hardware \
  --confirm-wheels-lifted \
  --confirm-power-cutoff
```

このコマンドは実車が動く可能性がある。
駆動輪を床から浮かせ、物理的な電源遮断手段を準備し、`pigpiod` が起動していることを確認してから使う。

## 次にやること

1. `esc_duty 約 10.200 %` で低速走行できた設定を基準値として扱う。
2. ステアリング方向が期待方向と一致するか確認する。
3. Param_init、watchdog、Ctrl-Cで中立復帰することを再確認する。
4. 短時間の直進低速確認を行う。
5. 短い参照軌道でSimulink/Python MPCの実機閉ループ確認へ進む。

Simulink側の意味をさらに詰める場合は、Simulink下段の `PWM` サブシステムを開き、`out.PWM` を作っている3本の入力を確認する。
それぞれにDisplayを付け、次を確定する。

```text
out.PWM(1) の意味と単位
out.PWM(2) の意味と単位
out.PWM(3) の意味と単位
```

その3要素を今後整理する場合は、Simulink下段からRaspberry Piへ送る値を次のどちらかにすると分かりやすい。

```text
案A: [steering_duty_percent, esc_duty_percent, enable_or_mode]
案B: [target_speed_mps, target_steer_rad]
```

案Bの場合、`target_steer_rad` は角度[rad]で送る。
速度はSI単位の m/s を使う。

## 安全メモ

実PWM出力で走行確認済みである。
ただし、実車へ接続する前には毎回、GPIO番号、PWM周波数、中立値、安全duty範囲、車輪を浮かせていること、物理的な電源遮断手段があることを確認する。

現在のUDP受信値は直接PWM duty[%]として使わず、`legacy_double3_rc_pwm_receiver.py` で速度[m/s]とステア角[rad]へ変換してから、RCカー用のPWM duty[%]へ変換する。
