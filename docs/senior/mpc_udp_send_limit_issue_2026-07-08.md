# MPC UDP Send Limit Issue Handoff

作成日: 2026-07-08

## 要約

2026-07-08時点で、Raspberry Pi側のUDP受信、RCカー向け変換、安全拒否、ニュートラル復帰は正常に動いている。

現在の主問題は、SimulinkまたはPC側送信経路で、Raspberry Piへ送る直前の `float64 x 3` 指令が安全範囲に制限されていないことである。

この問題が解決するまで、床走行にも、Raspberry Pi側の実PWM出力再テストにも進まない。

## 関係する構成

Raspberry Pi側の実行場所:

```text
~/OpenMiniCarWorks/UDP_test/ZikkiV1
```

現在使っている受信プログラム:

```text
legacy_double3_rc_pwm_receiver.py
```

UDP形式:

```text
受信ポート: 5005
データ形式: little-endian float64 x 3
パケットサイズ: 24 bytes
値: [raw1, raw2, raw3]
```

現在の変換:

```text
target_speed_mps = average(raw1, raw2) * speed_per_legacy_unit
speed_per_legacy_unit = 0.0050

target_steer_deg = -0.8246 * raw3 + 74.212
target_steer_rad = target_steer_deg * pi / 180
```

角度の符号:

```text
target_steer_deg > 0: 左
target_steer_deg < 0: 右
```

## 確認済みの正常動作

Raspberry Pi側で確認済み:

```text
UDP float64 x3 受信
dry-run表示
実PWM出力
ESCニュートラル duty 10.3 %
ステアリング左右方向
watchdog_neutral
範囲外指令のREJECT
REJECT後のinvalid_neutral出力
Ctrl-Cまたは通信停止時の中立復帰
```

`invalid_neutral` は、REJECT後にRaspberry Pi側が安全のためニュートラルを出した状態である。
`invalid_neutral` 自体が別原因の故障を意味するわけではない。

## 現在の問題

`mpc_chain_dry_limited_03.log`、`mpc_chain_dry_limited_04.log`、`mpc_chain_dry_limited_05.log` で、送信値の最終制限が効いていないことを確認した。

`mpc_chain_dry_limited_05.log` の例:

```text
raw=(-11.805523580, -11.805523580, 85.997574582)
status=negative_speed,clamped_speed
```

これは、Raspberry Pi側へ負の速度指令が届いていることを示す。

`mpc_chain_dry_limited_05.log` のステータス集計:

```text
36  status=clamped_speed
181 status=clamped_speed,clamped_steer
124 status=clamped_steer
565 status=invalid_neutral
164 status=negative_speed,clamped_speed
60  status=negative_speed,clamped_speed,clamped_steer
1   status=neutral
236 status=ok
1   status=watchdog_neutral
```

REJECT系の件数は次の合計である。

```text
36 + 181 + 124 + 164 + 60 = 565
```

これは `status=invalid_neutral` の565件と一致する。
つまり、Raspberry Pi側は範囲外指令を拒否し、そのたびにニュートラルを出している。

## 受信側ではなく送信側が問題と判断する理由

Raspberry Pi側ログには、実際に受信した `raw1`、`raw2`、`raw3` が表示されている。

ログに出ている範囲外値:

```text
raw1/raw2 = -11.805...  -> negative_speed
raw1/raw2 = 60以上/80   -> clamped_speed
raw3 = 40から60程度     -> clamped_steer
raw3 = 112から119程度   -> clamped_steer
```

したがって、Raspberry Pi側の変換前に、すでに危険範囲の値がUDPで届いている。

受信側の安全処理は期待通り動いているため、次に直すべき場所はSimulinkまたはPC側のUDP送信直前である。

## 想定原因

可能性が高い原因:

```text
1. Saturationを入れた場所が、UDP Sendより手前すぎる
2. Simulinkのシミュレーション用経路と実機UDP送信経路が別で、違う信号を直している
3. Saturation後にraw1/raw2/raw3が再計算または上書きされている
4. 古いモデル、別モデル、別のUDP Sendブロック、または別プロセスがUDP 5005へ送っている
```

## 追加切り分け: UDP idle probe

2026-07-08に、SimulinkやPC側送信を止めた状態でRaspberry Pi側のdry-run受信だけを起動した。

実行:

```bash
python -u legacy_double3_rc_pwm_receiver.py \
  --speed-per-legacy-unit 0.0050 \
  --esc-neutral-duty 10.3 \
  2>&1 | tee udp_idle_probe.log
```

送信停止中の初期表示:

```text
DRY sender=- raw=(0.000000000, 0.000000000, 90.000000000) status=neutral
```

この時点では `sender=192.168.11.2` が出ていない。
したがって、少なくともこの確認時点では、別プロセスが常時UDP 5005へ送っている可能性は低い。

その後、意図したSimulink側だけを動かしたときの集計:

```text
2   sender=-
801 sender=192.168.11.2:53142

1   status=neutral
801 status=ok
1   status=watchdog_neutral
```

この確認では、送信元は `192.168.11.2:53142` の1種類だけであり、全受信コマンドが `status=ok` だった。
受信値は主に次の固定値であった。

```text
raw=(6.111111111, 6.111111111, 85.997574582)
target_speed_mps=0.030555556 m/s
target_steer_rad=0.057567940 rad
target_steer_deg=3.2984 deg
```

この結果から、常時動作している別UDP送信プロセスよりも、Simulinkの特定モード、特定軌道、または特定実行条件で範囲外値が出ている可能性が高い。
過去の `mpc_chain_dry_limited_03` から `05` で出ていた `negative_speed` や `clamped_steer` を再現するには、同じMPCチェーン条件でdry-runを取り直す必要がある。

## 追加切り分け: MPCチェーン条件での再現

2026-07-08に、問題が出たときと同じMPCチェーン条件でdry-runを取り直した。

実行ログ:

```text
mpc_chain_dry_repro_06.log
```

結果として、範囲外指令が再現した。

先頭のREJECT例:

```text
raw=(-11.805523580, -11.805523580, 85.997574582)
status=negative_speed,clamped_speed
```

送信元集計:

```text
570 sender=-
801 sender=192.168.11.2:59461
```

ステータス集計:

```text
36  status=clamped_speed
174 status=clamped_speed,clamped_steer
133 status=clamped_steer
568 status=invalid_neutral
168 status=negative_speed,clamped_speed
57  status=negative_speed,clamped_speed,clamped_steer
1   status=neutral
233 status=ok
1   status=watchdog_neutral
```

この結果から、単純な固定値送信時は正常だが、MPCチェーン条件では `raw1/raw2` が負値または上限超過になり、`raw3` も操舵上限を超えることが分かった。

送信元は `192.168.11.2:59461` の1種類であるため、この再現条件では複数UDP送信元の混在よりも、MPCチェーンからUDP Sendへ入る信号自体が範囲外になっている可能性が高い。

次に見るべき場所は、MPCチェーン条件でのSimulink側 `Byte Pack` / `UDP Send` 入力直前の3要素信号である。

## 追加切り分け: MPCチェーン条件のDRY合格

その後、同じ `mpc_chain_dry_repro_06.log` 名で再実行されたログでは、REJECT系が消えた。
同名ファイルが再生成または上書きされた可能性があるため、以下は最新ログの結果として扱う。

送信元集計:

```text
2   sender=-
801 sender=192.168.11.2:61483
```

ステータス集計:

```text
1   status=neutral
701 status=ok
100 status=param_init_neutral
1   status=watchdog_neutral
```

この最新結果では、`REJECT`、`clamped_speed`、`clamped_steer`、`negative_speed`、`invalid_neutral` が出ていない。
したがって、このDRY条件ではMPCチェーンからRaspberry Piへ届く最終UDP値は受信側の安全範囲内に収まっている。

この変化が初期値合わせ、Simulinkモード変更、Saturation位置修正、または別の実行条件変更によるものかは、Simulink側で別途確認する必要がある。
ただし、Raspberry Pi側DRY判定としては合格であり、次は駆動輪を浮かせた実PWM確認へ進める候補になる。

## 追加確認: MPCチェーン条件のリフト実PWM合格

DRY合格後、駆動輪を浮かせた状態で実PWM確認を行った。

実行ログ:

```text
mpc_chain_lifted_repro_06.log
```

ステータス集計:

```text
1   status=neutral
701 status=ok
100 status=param_init_neutral
1   status=watchdog_neutral
```

このリフト実PWM確認では、`REJECT`、`clamped_speed`、`clamped_steer`、`negative_speed`、`invalid_neutral` は出ていない。
したがって、Raspberry Pi側の実PWM出力中でも、MPCチェーンから届く最終UDP値は受信側の安全範囲内に収まっている。

次に進む場合は、床走行ではなく、まず1秒から2秒程度の最短床確認に限定する。
物理的な電源遮断手段を手元に置き、広い場所で、すぐ停止できる状態で実施する。

## 追加確認: 床短時間確認で発進せず

DRY確認とリフト実PWM確認は合格したが、床短時間確認では車体が発進しなかった。

観測値:

```text
esc_duty 約 10.227295 %
```

この値はESCニュートラル `10.3 %` に近く、床上で静止摩擦を越えるには弱い可能性が高い。

現在のESC速度変換は次である。

```text
speed_mps = -2.4618 * esc_duty_percent + 25.347
esc_duty_percent = (25.347 - speed_mps) / 2.4618
```

現在の受信側速度上限:

```text
max_speed_mps = 0.30 m/s
```

この上限内で出せる最小ESC dutyは、およそ次である。

```text
0.250 m/s -> esc_duty 約 10.195 %
0.300 m/s -> esc_duty 約 10.174 %
```

一方で、目標としている `esc_duty=10.1 %` から `10.0 %` は、現在の変換式では次の速度に相当する。

```text
10.1 % -> 約 0.483 m/s
10.0 % -> 約 0.729 m/s
```

したがって、現在の `max_speed_mps=0.30 m/s` のままでは `esc_duty=10.1 %` から `10.0 %` には到達しない。

次の安全な改善候補:

```text
1. まず送信側raw1/raw2上限を50から58程度へ上げる
2. 受信側max_speed_mpsは0.30 m/sのままにする
3. DRY、リフト実PWM、床短時間の順に再確認する
```

`raw1/raw2=58`、`speed_per_legacy_unit=0.0050` では、目標速度は約 `0.290 m/s`、ESC dutyは約 `10.178 %` になる。

それでも発進しない場合は、`max_speed_mps` を0.30 m/sより上げる必要がある。
ただしこれは車速上限を上げる変更であり、床走行前にリスクを明示して、駆動輪を浮かせた状態から再確認する。

## 追加確認: raw上限58では実出力がまだ弱い

送信側 `raw1/raw2` 上限を58程度に上げた条件で、DRYとリフト実PWMは合格した。

DRY結果:

```text
1   status=neutral
701 status=ok
100 status=param_init_neutral
1   status=watchdog_neutral
```

リフト実PWM結果:

```text
1   status=neutral
701 status=ok
100 status=param_init_neutral
1   status=watchdog_neutral
```

ただし、リフト実PWMログの `status=ok` 行を集計したところ、最大速度指令は次だった。

```text
max_target_speed_mps = 0.197167446 m/s
min_esc_duty = 10.216034 %
raw=(39.433489276, 39.433489276, 85.997574582)
```

つまり、送信側上限を58にしても、MPCチェーン実行中の実際の `raw1/raw2` は約39.43までしか上がっていない。
そのため、床上で発進しない原因は、raw上限ではなく、MPCまたは参照条件が出している速度指令そのものが弱いことにある。

現在の `speed_per_legacy_unit=0.0050` では、`raw=39.43` は約 `0.197 m/s`、ESC dutyは約 `10.216 %` である。

次の改善候補:

```text
案A: Simulink/MPC側の参照速度または速度指令を上げ、raw1/raw2が55から58程度まで出るようにする
案B: speed_per_legacy_unitを0.0070程度へ上げる代わりに、送信側raw1/raw2上限を42程度へ下げ、受信側max_speed_mps=0.30 m/sを超えないようにする
案C: 10.1 %から10.0 %を目標にする場合はmax_speed_mpsを0.30 m/sより上げる必要があるが、これは速度上限を上げる変更なのでリフト状態から段階的に確認する
```

## 追加確認: speed_per_legacy_unit 0.0070 と raw上限42

`speed_per_legacy_unit=0.0070` に上げ、Simulink側の `raw1/raw2` 上限を42程度に下げた条件で確認した。
この組み合わせでは、`raw=42` が来ても目標速度は約 `0.294 m/s` で、受信側の `max_speed_mps=0.30 m/s` を超えない。

DRYログ:

```text
mpc_chain_dry_scale0070_raw42_01.log
```

DRY結果:

```text
1   status=neutral
701 status=ok
100 status=param_init_neutral
1   status=watchdog_neutral
```

リフト実PWMログ:

```text
mpc_chain_lifted_scale0070_raw42_01.log
```

リフト実PWM結果:

```text
1   status=neutral
701 status=ok
100 status=param_init_neutral
1   status=watchdog_neutral
```

リフト実PWMでの最大速度と最小ESC duty:

```text
raw=(39.433507903, 39.433507903, 85.997574582)
target_speed_mps=0.276034555 m/s
esc_duty=10.183998 %
```

この条件では、REJECT、clamped、negative_speed、invalid_neutralは出ていない。
また、以前の `esc_duty=10.216 %` 付近より強い前進指令になっている。

次に進む場合は、この `speed_per_legacy_unit=0.0070`、`raw1/raw2上限42`、`raw3上限70.6から109.4` の条件で床1秒から2秒の短時間確認を行う。
床確認で発進しない場合でも、いきなり `10.1 %` から `10.0 %` を狙わず、速度上限変更はリフト確認から段階的に行う。

## 追加確認: speed_per_legacy_unit 0.0070 / raw上限42 の床短時間結果

床1秒から2秒の短時間確認を行った。

ログ:

```text
mpc_chain_floor_short_scale0070_raw42_01.log
```

ログ上のステータス:

```text
1   status=neutral
701 status=ok
100 status=param_init_neutral
1   status=watchdog_neutral
```

REJECT、clamped、negative_speed、invalid_neutralは出ていない。

実車挙動:

```text
車体は前に進んだ
発進は少し弱い
ステア方向はやや左曲がり
停止時に確実に停止した
走行距離と姿勢は安全範囲だった
```

この条件は、現時点の安全な実走候補として扱える。
ただし、速度はまだ弱く、ESC dutyの理想値としては `10.1 %` から `10.0 %` が挙がっている。

現在の実出力はおよそ次である。

```text
target_speed_mps 約 0.276 m/s
esc_duty 約 10.184 %
```

`esc_duty=10.1 %` から `10.0 %` は、現在の変換式では `0.48 m/s` から `0.73 m/s` 程度に相当する。
これは現在の受信側速度上限 `0.30 m/s` を超えるため、目標にする場合は速度上限を上げる変更になる。

次の候補は、いきなり `10.1 %` から `10.0 %` を狙わず、まず `esc_duty` 約 `10.15 %` 程度をリフト状態から段階的に確認することである。

## 次回実装設定: 速度強化と直進補正

床短時間確認の結果から、次は次の2点を実装する。

```text
1. 速度を少し強くする
2. やや左曲がりを補正する
```

速度側の設定:

```text
Simulink側 raw1/raw2 上限: 42
Raspberry Pi側 speed_per_legacy_unit: 0.0090
Raspberry Pi側 max_speed_mps: 0.38
```

この条件では、現在代表的に出ている `raw1/raw2=39.4335` は次になる。

```text
target_speed_mps 約 0.355 m/s
esc_duty 約 10.152 %
```

`raw1/raw2=42` まで出た場合:

```text
target_speed_mps 約 0.378 m/s
esc_duty 約 10.143 %
```

直進補正:

現在の代表値:

```text
raw3=85.997574582
target_steer_deg=+3.2984 deg
```

正のステア角は左なので、床確認での「やや左曲がり」と一致する。
直進0 degへ寄せるには、実機送信用の `raw3` を約 `+4.0024` だけ増やす。

Simulink側のUDP送信直前で推奨する処理:

```text
raw1_limited = Saturation(raw1, lower=0.0, upper=42.0)
raw2_limited = Saturation(raw2, lower=0.0, upper=42.0)

raw3_corrected = raw3 + 4.0024
raw3_limited = Saturation(raw3_corrected, lower=70.6, upper=109.4)

[raw1_limited, raw2_limited, raw3_limited]
  -> Byte Pack / Byte Packing
  -> UDP Send
```

この方法では、Raspberry Pi側の既存操舵変換式は変更しない。

Raspberry Pi側のDRY確認コマンド:

```bash
python -u legacy_double3_rc_pwm_receiver.py \
  --speed-per-legacy-unit 0.0090 \
  --max-speed-mps 0.38 \
  --esc-neutral-duty 10.3 \
  2>&1 | tee mpc_chain_dry_scale0090_raw42_steerfix_01.log
```

DRY確認後、REJECT、clamped、negative_speed、invalid_neutralが0件であることを確認してから、リフト実PWM確認へ進む。

## 追加確認: 速度強化は有効、直進補正は未反映

`speed_per_legacy_unit=0.0090`、`max_speed_mps=0.38`、`raw1/raw2上限42` の条件でDRYとリフト実PWMを確認した。

リフト実PWMログ:

```text
mpc_chain_lifted_scale0090_raw42_steerfix_01.log
```

ステータス集計:

```text
1   status=neutral
701 status=ok
100 status=param_init_neutral
1   status=watchdog_neutral
```

速度側の結果:

```text
raw=(39.480413447, 39.480413447, 85.997574582)
target_speed_mps=0.355323721 m/s
esc_duty=10.151790 %
```

速度強化は想定通り効いている。

一方で、直進補正はログに反映されていない。

```text
raw3=85.997574582
target_steer_deg=+3.2984 deg
avg_target_steer_deg=+3.2984 deg
```

Simulink側で `raw3 + 4.0024` を入れた場合、Raspberry Pi側ログには `raw3` が約 `90.000` と表示され、`target_steer_deg` は約 `0 deg` になるはずである。
したがって、現状ではSimulink側の直進補正がUDP Send直前の最終値に入っていない。

## 追加確認: 左曲がり条件で床走行成功

直進補正は未反映だったが、左曲がりを許容して床走行を実施した。

実行ログ:

```text
mpc_chain_floor_scale0090_raw42_leftcurve_01.log
```

実行条件:

```text
Simulink側 raw1/raw2 上限: 42
Simulink側 raw3: 未補正
Raspberry Pi側 speed_per_legacy_unit: 0.0090
Raspberry Pi側 max_speed_mps: 0.38 m/s
Raspberry Pi側 esc_neutral_duty: 10.3 %
```

代表値:

```text
target_speed_mps 約 0.355 m/s
esc_duty 約 10.152 %
target_steer_deg 約 +3.298 deg
target_steer_rad 約 +0.0576 rad
```

実車結果:

```text
車体は前に進んだ
左曲がりだった
停止した
走行は安全範囲だった
十分な成果として扱える
```

この条件により、MPCチェーンからRaspberry PiへのUDP実機送信、Raspberry Pi側変換、実PWM出力、床上前進、停止復帰までを確認できた。

## 次回作業: 受信側オプションによる直進補正

Simulink側の `raw3 + 4.0024` 補正はログに反映されなかった。
そのため、次回の直進補正はRaspberry Pi側の既存オプション `--legacy-steer-b` を使って行う。

現在の操舵変換:

```text
target_steer_deg = -0.8246 * raw3 + 74.212
```

床走行時の代表値:

```text
raw3 = 85.997574582
target_steer_deg = +3.2984 deg
```

この代表値を直進 `0 deg` に合わせるため、切片を次に変更する。

```text
legacy_steer_b = 70.9136
```

補正後の操舵変換:

```text
target_steer_deg = -0.8246 * raw3 + 70.9136
```

この補正では、`raw3=85.997574582` がほぼ `0 deg` になる。

補正後の推奨raw3制限:

```text
raw3: 66.6 から 105.4
```

これは補正後の操舵角を約 `+16 deg` から `-16 deg` に収める範囲である。
従来の `70.6 から 109.4` のままだと、上側で `-18 deg` を少し超える可能性がある。

直進補正の確認順:

```text
1. DRY
2. リフト実PWM
3. 床1秒から2秒
```

DRY確認コマンド:

```bash
python -u legacy_double3_rc_pwm_receiver.py \
  --speed-per-legacy-unit 0.0090 \
  --max-speed-mps 0.38 \
  --legacy-steer-b 70.9136 \
  --esc-neutral-duty 10.3 \
  2>&1 | tee mpc_chain_dry_scale0090_raw42_straight_b709136_01.log
```

## 追加確認: legacy_steer_b 70.9136 の直進補正成功

Raspberry Pi側オプション `--legacy-steer-b 70.9136` による直進補正を確認した。

DRYログ:

```text
mpc_chain_dry_scale0090_raw42_straight_b709136_01.log
```

DRY結果:

```text
1   status=neutral
701 status=ok
100 status=param_init_neutral
1   status=watchdog_neutral
avg_target_steer_deg = 0 deg
```

リフト実PWMログ:

```text
mpc_chain_lifted_scale0090_raw42_straight_b709136_01.log
```

リフト実PWM結果:

```text
1    status=neutral
2103 status=ok
300  status=param_init_neutral
3    status=watchdog_neutral
```

リフト実PWMでの代表集計:

```text
max_target_speed_mps = 0.369126 m/s
min_esc_duty = 10.1462 %
avg_target_steer_deg = 0 deg
```

床でも同条件で実験し、直進精度はかなり良かった。
少し右に曲がったが、このまま採用できる範囲と判断した。

現時点の採用設定:

```text
Simulink側 raw1/raw2 上限: 42
Simulink側 raw3: 未補正
Raspberry Pi側 speed_per_legacy_unit: 0.0090
Raspberry Pi側 max_speed_mps: 0.38 m/s
Raspberry Pi側 legacy_steer_b: 70.9136
Raspberry Pi側 esc_neutral_duty: 10.3 %
```

この設定で、MPCチェーンからのUDP実機送信、Raspberry Pi側変換、実PWM出力、床上前進、停止復帰、直進補正まで確認できた。

## 必要な改善策

Simulink側では、`Byte Pack` または `Byte Packing` へ入る直前の3要素信号を制限する。
MPC出力直後ではなく、UDPで送信される最終値を制限することが重要である。

推奨ブロック構成:

```text
[raw1 raw2 raw3]
   -> Demux(3)
      raw1 -> Saturation lower=0.0,  upper=50.0
      raw2 -> Saturation lower=0.0,  upper=50.0
      raw3 -> Saturation lower=70.6, upper=109.4
   -> Mux(3)
   -> Byte Pack / Byte Packing
   -> UDP Send
   -> Raspberry Pi port 5005
```

安全範囲:

```text
raw1: 0.0 から 50.0
raw2: 0.0 から 50.0
raw3: 70.6 から 109.4
```

この範囲の意味:

```text
raw1/raw2 <= 50.0 with speed_per_legacy_unit=0.0050
  -> target_speed_mps <= 0.250 m/s

raw3 70.6から109.4
  -> target_steer_deg 約 +16 deg から -16 deg
  -> target_steer_rad 約 +0.279 rad から -0.279 rad
```

受信側の絶対上限は次である。

```text
speed <= 0.300 m/s
steering <= +/-18 deg
steering <= +/-0.314 rad
```

ただし、送信側の推奨制限は余裕を持たせるため `0.250 m/s` と `+/-16 deg` とする。

## Simulinkで確認する場所

確認すべき場所は、Simulinkモデル内の `UDP Send` ブロックの入力直前である。

探す順番:

```text
1. Simulinkモデル内でUDP Sendを探す
2. UDP Send直前のByte Pack / Byte Packingを探す
3. Byte Packに入る3要素信号を探す
4. その信号にDisplayまたはScopeを付ける
5. 表示される3値が安全範囲内か確認する
```

DisplayまたはScopeで、次が1回でも出る場合は未修正である。

```text
raw1 < 0.0
raw2 < 0.0
raw1 > 50.0
raw2 > 50.0
raw3 < 70.6
raw3 > 109.4
```

## Simulinkモードについて

Raspberry Pi側で実PWM出力を有効にする必要はない。
今の段階ではPi側はdry-runのままにする。

Simulink側に「simulation mode」と「real mode」または「実機に入力を送信」の切替がある場合は、Raspberry PiへUDPを送っている実機UDP経路を確認対象にする。

目的は実車を動かすことではなく、Raspberry Piに届く最終UDP値が安全範囲に収まることをdry-runで確認することである。

## 次の確認手順

SimulinkでUDP Send直前の最終3値を制限し、DisplayまたはScopeで安全範囲内であることを確認する。

その後、Raspberry Pi側でdry-runを実行する。

```bash
python -u legacy_double3_rc_pwm_receiver.py \
  --speed-per-legacy-unit 0.0050 \
  --esc-neutral-duty 10.3 \
  2>&1 | tee mpc_chain_dry_limited_06.log
```

結果確認:

```bash
grep -E "REJECT|clamped|negative_speed|invalid_neutral" mpc_chain_dry_limited_06.log | head
grep -o "status=[^ ]*" mpc_chain_dry_limited_06.log | sort | uniq -c
```

合格条件:

```text
1つ目のgrepが空
statusが基本的にneutral / ok / watchdog_neutralだけ
REJECTが0件
clampedが0件
negative_speedが0件
invalid_neutralが0件
```

## 合格後に進めること

dry-run合格後に、初めてリフト状態の実PWMテストへ進む。

実PWMテスト条件:

```text
駆動輪を浮かせる
物理的な電源遮断手段を手元に置く
pigpiodが起動している
Raspberry Pi側のGPIO設定が実配線と一致している
床走行はまだ行わない
```

実PWMテスト例:

```bash
python -u legacy_double3_rc_pwm_receiver.py \
  --speed-per-legacy-unit 0.0050 \
  --esc-neutral-duty 10.3 \
  --enable-hardware \
  --confirm-wheels-lifted \
  --confirm-power-cutoff \
  2>&1 | tee mpc_chain_lifted_limited_06.log
```

床走行は、dry-runとリフト状態の両方で、REJECT、clamped、negative_speed、invalid_neutralが0件であることを確認してから判断する。

## 現在やってはいけないこと

```text
Raspberry Pi側で--enable-hardwareを付けて再試行する
床に置いて走行させる
speed_per_legacy_unitを上げる
操舵上限を広げる
受信側のREJECTを無効化する
受信側のclamp後値をそのままPWM出力させる
```

送信側が直るまで、受信側で同じdry-runを繰り返しても結果は変わらない。

## 判断

現状は、Raspberry Pi側の実装問題ではなく、SimulinkまたはPC側のUDP送信直前の信号制限問題である。

次の作業者は、Raspberry Pi側ログをさらに増やすより先に、Simulinkの `UDP Send` / `Byte Pack` 入力直前の3要素信号を確認すること。

## 2026-07-08更新: 現在の成功条件と直線停止テスト

上の古い判断は、初期の `speed_per_legacy_unit=0.0050` / 送信値未制限時点のもの。
その後、以下の条件でDRY、リフト、床走行まで進み、直線走行は実車で十分に成功した。

現在採用する受信側条件:

```bash
python -u legacy_double3_rc_pwm_receiver.py \
  --speed-per-legacy-unit 0.0090 \
  --max-speed-mps 0.38 \
  --legacy-steer-b 70.9136 \
  --esc-neutral-duty 10.3
```

実PWM出力時は、従来通り次を明示する。

```bash
  --enable-hardware \
  --confirm-wheels-lifted \
  --confirm-power-cutoff
```

成功ログ例:

```text
mpc_chain_lifted_scale0090_raw42_straight_b709136_01.log
1    status=neutral
2103 status=ok
300  status=param_init_neutral
3    status=watchdog_neutral
max_target_speed_mps=0.369126 m/s
min_esc_duty=10.1462 %
avg_target_steer_deg=0 deg
```

床走行の観察:

```text
前進した。
発進は安全範囲内。
直進性はかなり良い。
わずかに右へ曲がったが、現時点では許容。
停止した。
走行距離と姿勢は危険ではなかった。
```

次の目的は、参照軌道・位置ログ評価へ進む前に、直線で目的距離に到達したら止まるかを確認すること。
先輩コード `scripts/ellipse_run/run_ellipse.py` はGPIO17/18へpigpioで直接PWMを出す古い構成なので、現在の成功条件ではそのまま実機走行に使わない。
代わりに、同じディレクトリの `Odometer` だけを再利用し、駆動指令は現在成功しているUDP受信機へ送る。

追加した直線距離停止用スクリプト:

```text
UDP/straight_distance_legacy_sender.py
```

役割:

```text
1. エンコーダ距離またはシミュレーション距離を読む
2. legacy float64 x3 UDPを5005番へ送る
3. 目標距離[m]または最大時間[s]で停止する
4. 終了時に raw=(0,0,90) を複数回送って受信側を param_init_neutral に戻す
5. 距離ログCSVを保存する
```

デフォルトの送信値:

```text
raw1/raw2 = 39.5
raw3      = 85.997574582
```

この値は、受信側で `--speed-per-legacy-unit 0.0090`、`--legacy-steer-b 70.9136` を使う前提で、直進かつ安全な前進を狙う値である。

直線停止の最初の床目標は短くする。

```text
target_distance_m = 0.30 m
max_run_s         = 2.0 s
```

注意:

```text
エンコーダGPIOは先輩コード由来で BCM22/BCM27。
エンコーダ出力がRaspberry Pi GPIO互換の3.3 Vであることを確認する。
5 V出力をGPIOへ直結しない。
車輪すべり、ステアリング微小偏り、バックラッシュにより、エンコーダ距離と実際の車体位置には誤差が出る。
```

## 2026-07-08更新: 実機想定モードでの再発

同じファイル名 `mpc_chain_lifted_scale0090_raw42_straight_b709136_01.log` で、実機想定にした後に再度REJECTが発生した。

受信側条件:

```bash
python -u legacy_double3_rc_pwm_receiver.py \
  --speed-per-legacy-unit 0.0090 \
  --max-speed-mps 0.38 \
  --legacy-steer-b 70.9136 \
  --esc-neutral-duty 10.3 \
  --enable-hardware \
  --confirm-wheels-lifted \
  --confirm-power-cutoff
```

代表例:

```text
raw=(80.000000000, 80.000000000, 85.997574582)
target_speed_mps=0.380000000 m/s
status=clamped_speed
```

ステータス集計:

```text
46  status=clamped_speed
694 status=invalid_neutral
648 status=negative_speed,clamped_speed
1   status=neutral
7   status=ok
100 status=param_init_neutral
1   status=watchdog_neutral
```

`status=ok` のみを集計すると、実際にPWM出力された最大速度は非常に小さい。

```text
max_target_speed_mps=0.055 m/s
min_esc_duty=10.2738 %
avg_target_steer_deg=0 deg
```

判断:

```text
受信機、GPIO、PWM出力の問題ではない。
実機想定にしたSimulink/PC側送信経路が、raw42制限済みの経路ではなく、raw=80や負値を送る経路に戻っている。
受信機は安全設計通り、clamped_speed/negative_speedを拒否し、invalid_neutralを出している。
```

次の修正対象:

```text
Simulinkの実機想定モードで、UDP Send / Byte Pack 入力直前の raw1/raw2 を 0.0 から 42.0 程度へ制限する。
raw1/raw2 の負値は 0.0 にする。
raw3 は現在の legacy_steer_b=70.9136 前提で、おおむね 66.6 から 105.4 に制限する。
```

再試験は、必ず同じ実機想定モードをdry-runで先に確認する。

```bash
python -u legacy_double3_rc_pwm_receiver.py \
  --speed-per-legacy-unit 0.0090 \
  --max-speed-mps 0.38 \
  --legacy-steer-b 70.9136 \
  --esc-neutral-duty 10.3 \
  2>&1 | tee mpc_chain_dry_realmode_scale0090_b709136_01.log
```

合格条件:

```text
REJECTなし
clamped_speedなし
negative_speedなし
invalid_neutralなし
status=ok が主
param_init_neutral と watchdog_neutral は許容
```

## 2026-07-08更新: Simulinkは変更しない方針

ユーザー方針として、Simulinkモデルは変更しない。

このため、現在のSimulink実機想定モードから来るUDP指令は、直線停止の実機検証には使わない。
理由は、同モードで `raw1/raw2=80` と負値が送信され、受信機が `clamped_speed` / `negative_speed` として拒否するためである。

直線で目的距離に到達したら止まるかの検証は、Simulinkを経由せず、以下の構成で行う。

```text
UDP/straight_distance_legacy_sender.py
  -> fixed safe raw command
  -> encoder distance stop
  -> legacy_double3_rc_pwm_receiver.py
  -> PWM output
```

この検証で使う固定raw値:

```text
raw1 = 39.5
raw2 = 39.5
raw3 = 85.997574582
```

受信側条件:

```text
speed_per_legacy_unit = 0.0090
max_speed_mps         = 0.38 m/s
legacy_steer_b        = 70.9136
esc_neutral_duty      = 10.3 %
```

この条件では、受信側DRY確認で以下になる。

```text
target_speed_mps = 0.3555 m/s
target_steer_deg = 0.0 deg
esc_duty         = 10.151718 %
status           = ok
```

将来、Simulinkを変更せずにSimulink出力をそのまま使いたい場合は、Raspberry Pi受信機側に明示的な入力リミッタを追加する必要がある。
ただし、その場合は今までREJECTしていた指令を制限後に動かす仕様変更になるため、必ずDRYでログ確認してからリフト実機へ進む。

## 2026-07-08更新: Simulink実機想定モードを使うための受信側制限出力

Simulink実機想定モードを使わないと参照軌道ログやグラフが作れないため、Simulinkモデルは変更せず、受信機側に明示フラグ付きの制限出力モードを追加した。

追加フラグ:

```text
--allow-limited-output
```

通常モードは従来通りで、`clamped_speed`、`negative_speed`、`clamped_steer` はREJECTされる。
`--allow-limited-output` を付けた時だけ、以下の範囲外指令を受信機側の設定値へ制限して出力する。

```text
negative_speed -> target_speed_mps = 0.0 m/s
clamped_speed  -> target_speed_mps = max_speed_mps
clamped_steer  -> target_steer_rad = +/- max_steer_rad
```

それ以外の異常は引き続きREJECTする。

```text
nonfinite_raw
legacy_motor_mismatch
speed_scale_unset
steering_duty_out_of_range
esc_duty_out_of_range
invalid packet size
```

ハードウェア出力でこのモードを使う場合は、追加で次の確認フラグが必要。

```text
--confirm-accept-limited-output
```

このモードのログでは、制限後に出力した行は `LIMITED_DRY` または `LIMITED_PWM` と表示される。
`status=clamped_speed` が出ても、このモードでは即失敗ではない。
失敗として見るべきものは `REJECT`、`invalid_neutral`、`nonfinite_raw`、`out_of_range` である。

最初のDRY確認例:

```bash
python -u legacy_double3_rc_pwm_receiver.py \
  --speed-per-legacy-unit 0.0090 \
  --max-speed-mps 0.30 \
  --legacy-steer-b 70.9136 \
  --esc-neutral-duty 10.3 \
  --allow-limited-output \
  2>&1 | tee mpc_chain_dry_realmode_limited_output_01.log
```

最初の実PWM確認はリフト状態で行い、床走行前にログを確認する。

```bash
python -u legacy_double3_rc_pwm_receiver.py \
  --speed-per-legacy-unit 0.0090 \
  --max-speed-mps 0.30 \
  --legacy-steer-b 70.9136 \
  --esc-neutral-duty 10.3 \
  --allow-limited-output \
  --enable-hardware \
  --confirm-wheels-lifted \
  --confirm-power-cutoff \
  --confirm-accept-limited-output \
  2>&1 | tee mpc_chain_lifted_realmode_limited_output_01.log
```

`max_speed_mps` は安全側に 0.30 m/s から再開する。
0.38 m/sへ戻すのは、DRY、リフト、短い床走行のログが安全に見えることを確認した後にする。

### DRY確認結果

ログ:

```text
mpc_chain_dry_realmode_limited_output_01.log
```

確認結果:

```text
REJECTなし
invalid_neutralなし
nonfinite/out_of_range/legacy_motor_mismatch/speed_scale_unsetなし
LIMITED_DRYが出ている
```

代表例:

```text
DRY raw=(6.111111111, 6.111111111, 85.997574582)
target_speed_mps=0.055000000 m/s
status=ok

LIMITED_DRY raw=(80.000000000, 80.000000000, 85.997574582)
target_speed_mps=0.300000000 m/s
status=clamped_speed
```

ステータス集計:

```text
47  status=clamped_speed
648 status=negative_speed,clamped_speed
1   status=neutral
6   status=ok
100 status=param_init_neutral
1   status=watchdog_neutral
```

判断:

```text
受信側の制限出力モードは動作している。
clamped_speed/negative_speed はREJECTされず、LIMITED_DRYとして制限後の値になる。
負速度指令は target_speed_mps=0.0 m/s、ESC中立として扱われる。
```

注意:

```text
このログでは、648サンプルが負速度由来の中立出力になる。
そのため、実車では常時走るのではなく、正速度区間だけ前進し、負速度区間は停止する挙動になる。
次はリフト状態で、車輪が短く回って安全に中立へ戻るかを確認する。
床走行はリフトログ確認後に判断する。
```

### リフト実PWM確認結果

ログ:

```text
mpc_chain_lifted_realmode_limited_output_01.log
```

確認コマンド結果:

```text
REJECTなし
invalid_neutralなし
nonfinite/out_of_range/legacy_motor_mismatch/speed_scale_unsetなし
```

ステータス集計:

```text
48  status=clamped_speed
647 status=negative_speed,clamped_speed
1   status=neutral
6   status=ok
100 status=param_init_neutral
1   status=watchdog_neutral
```

判断:

```text
リフト状態の実PWM確認は安全判定として合格。
受信側の --allow-limited-output は実PWM出力でも機能している。
```

床走行へ進む場合の注意:

```text
max_speed_mps は 0.30 m/s のまま。
負速度区間はESC中立になるため、車体は断続的に前進または停止する可能性がある。
まず短距離・低リスクの床走行に限る。
物理電源遮断を手元に置く。
```

### 床走行確認結果

ログ:

```text
mpc_chain_floor_realmode_limited_output_01.log
```

ユーザー観察:

```text
前進と安全距離は大きな問題なし。
発進/継続走行に問題あり。
ステアリングが右へ曲がり、走行が停止するように見える。
```

ログ確認結果:

```text
REJECTなし
invalid_neutralなし
nonfinite/out_of_range/legacy_motor_mismatch/speed_scale_unsetなし
```

ステータス集計:

```text
94   status=clamped_speed
1296 status=negative_speed,clamped_speed
1    status=neutral
12   status=ok
200  status=param_init_neutral
2    status=watchdog_neutral
```

判断:

```text
受信機の安全制限は機能している。
ただし、全体の大半が negative_speed であり、受信機側では 0.0 m/s、ESC中立へ制限される。
そのため、実車は正速度区間だけ短く前進し、負速度区間で停止する。
```

右曲がりについて:

```text
現在の変換は target_steer_deg = -0.8246 * raw3 + legacy_steer_b。
legacy_steer_b=70.9136 では raw3=85.997574582 が 0 deg。
raw3 がこれより大きいと target_steer_deg は負、つまり右方向になる。
```

直線の目的位置停止だけを先に検証する場合は、Simulinkのraw3を使わず、受信機側で直進固定にする。
既存オプションで以下を指定すれば、raw3に関係なく `target_steer_deg=0 deg` になる。

```text
--legacy-steer-a 0
--legacy-steer-b 0
```

これで右曲がりが残る場合は、機械的な直進ずれまたは床面/タイヤ差の可能性が高い。
その場合は `--legacy-steer-b` を小さく左右補正するのではなく、直進固定値を `+0.5 deg` などにする専用オプションを追加して調整する。

### 強制直進モードの床確認結果

ログ:

```text
mpc_chain_floor_realmode_limited_output_forcestraight_01.log
```

実行条件:

```bash
python -u legacy_double3_rc_pwm_receiver.py \
  --speed-per-legacy-unit 0.0090 \
  --max-speed-mps 0.30 \
  --legacy-steer-a 0 \
  --legacy-steer-b 0 \
  --esc-neutral-duty 10.3 \
  --allow-limited-output \
  --enable-hardware \
  --confirm-wheels-lifted \
  --confirm-power-cutoff \
  --confirm-accept-limited-output
```

観察:

```text
一瞬前進して止まった。
モーションキャプチャーとの位置合わせは未実施。
```

判断:

```text
強制直進によりステアリング右曲がり要因は切り分け済み。
一瞬前進して止まる主因は、Simulink側が継続的な正速度を送っていないことが疑わしい。
これまでのログ傾向では negative_speed が大半で、受信機側では 0.0 m/s、ESC中立へ制限される。
```

モーションキャプチャー位置合わせ未実施の影響:

```text
現在位置、向き、参照軌道始点が合っていない場合、MPCは車体が目標を通過済み、逆向き、または軌道外にいると判断し得る。
その結果、負速度、停止、または右左の補正ステアが出る。
目的位置で止まるかの検証には、少なくとも初期位置 [m] と初期ヨー角 [radまたはdeg] の座標系合わせが必要。
```

次の優先作業:

```text
1. 床ログで negative_speed 件数と target_speed_mps の分布を確認する。
2. モーションキャプチャー座標とSimulink参照軌道の原点・向き・単位を合わせる。
3. 位置合わせ後にDRYで、正速度区間が十分に続くか確認する。
4. その後にリフト、短い床走行へ戻る。
```
