# Current Vehicle MPC Experiment Plan

作成日: 2026-07-08

更新日: 2026-07-08

予定期間: 2026-07-08 から 2026-07-10

## 最終ゴール

今のRCカー機体で、先輩のSimulink/Python MPC実験を実機で再現できるか確認する。

具体的には、SimulinkとPython MPCを使って参照軌道を実機で走らせ、シミュレーションと同じような追従結果になるかを確認し、走行データと比較グラフを残す。

## 前提

- Simulink/Python MPCの閉ループ計算は動いており、シミュレーション相当のグラフは取得できている。
- Simulink下段の「実機に入力を送信」からRaspberry Piへ `float64 x 3` のUDPが届いている。
- 現在はRaspberry Pi側で旧形式の `double x 3` を受け、今のRCカー向けのESC/ステアリングPWM duty比[%]へ変換している。
- `legacy_double3_rc_pwm_receiver.py` の実PWMモードで、現在のRCカーが実際に走ることを確認済みである。
- 駆動輪を浮かせた状態だけでなく、地面に接地した状態でも走行することを確認済みである。
- 角度は、MPC内部ではradを基本とし、表示・確認ではdegも併記する。
- 速度はm/s、PWM dutyは%で扱う。

## 現在のブロッカー

2026-07-08時点で、Raspberry Pi側の受信、変換、安全拒否、ニュートラル復帰は正常に動いている。
一方で、SimulinkまたはPC側からRaspberry Piへ送られる `float64 x 3` の最終UDP値が安全範囲に制限されていない。

このため、dry-runログで `negative_speed`、`clamped_speed`、`clamped_steer`、`invalid_neutral` が出ている。
この問題が解決するまで、リフト状態の実PWM再テストにも床走行にも進まない。

詳細な問題点、改善策、合格条件は次に記録した。

```text
docs/senior/mpc_udp_send_limit_issue_2026-07-08.md
```

## 計画

## 3日間の進め方

### 2026-07-08

目的: Raspberry Pi側の受信・変換・PWM出力手順を固める。

やること:

```text
Simulink下段UDPの double x 3 受信確認
legacy_double3_rc_pwm_receiver.py のドライラン確認
実PWMモードで中立出力確認
駆動輪を浮かせて esc_duty 約 10.200 % の反応確認
ステアリング duty 約 10.498 % の反応確認
```

完了条件:

```text
PWM sender=... status=ok が出る
Param_initで中立に戻る
Ctrl-Cで中立に戻る
ESCまたはステアリングの反応有無を記録する
```

実走確認結果:

```text
確認日: 2026-07-08
使用スクリプト: legacy_double3_rc_pwm_receiver.py
モード: 実PWM出力
送信元: 192.168.11.2:63641
raw=(6.111111111, 6.111111111, 85.997574582)
speed-per-legacy-unit=0.03872
target_speed_mps=0.236622222 m/s
target_steer_rad=0.057567940 rad
target_steer_deg=3.2984 deg
steering_duty=10.498187 %
esc-neutral-duty=10.3 %
esc_duty=10.200007 %
status=ok
結果: 実際に走ることを確認した
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

### 2026-07-09

目的: 実車が安全に低速で動く設定を決める。

やること:

```text
ESC中立 duty と動き始める duty を確認する
speed-per-legacy-unit を低速範囲で調整する
ステアリング方向と中立付近を確認する
短時間の直進低速確認を行う
停止・watchdog・Param_init復帰を確認する
```

完了条件:

```text
低速で車輪が回る設定が分かる
ステアリング方向が分かる
安全停止が確認できる
床上走行へ進めるか判断できる
```

### 2026-07-10

目的: 短い参照軌道で実機走行し、比較用データを残す。

やること:

```text
短い参照軌道でSimulink/Python MPCを実行する
実車位置と入力ログを保存する
シミュレーション結果と実車結果を数値やログで一次確認する
余裕があればx-y軌跡、x/y応答、角度応答、入力応答をグラフ化する
```

完了条件:

```text
実車ログが保存できている
シミュレーションとの差分を大まかに説明できる
追従できた点とできなかった点が説明できる
今の機体で先輩実験を再現できるか一次判断できる
```

### 1. 実車I/O確認

目的: Raspberry PiからESCとステアリングへ安全にPWM出力できることを確認する。

確認項目:

```text
ステアリングが動く
ESCが反応する
Param_initで中立に戻る
通信途絶でwatchdog_neutralになる
Ctrl-Cで中立に戻る
```

最初は必ず駆動輪を浮かせ、物理的に電源を切れる状態で確認する。

### 2. ESCとステアリングの向き確認

目的: Simulink/Pythonの指令方向と実車の動作方向が一致しているか確認する。

確認項目:

```text
ESC dutyを下げたときに前進方向か
ステア角が正のときに想定方向へ切れるか
中立dutyで停止・直進付近になるか
```

向きが逆なら、Raspberry Pi側の変換符号かSimulink側の信号定義を見直す。

### 3. 低速スケール調整

目的: 旧形式のモータ値を、今のRCカーの速度[m/s]へ仮対応させる。

現在の候補:

```text
--speed-per-legacy-unit 0.03872
raw motor value 6.111111111 -> target_speed_mps 0.2366 m/s
esc_duty 約 10.200 %
```

確認しながら、実車が安全に低速で動く範囲へ調整する。

記録する値:

```text
speed-per-legacy-unit
esc-neutral-duty
実際に動き始めたesc_duty [%]
車輪浮かせ状態での反応
床上での反応
```

### 4. 単純走行確認

目的: 参照軌道前に、基本動作ができるか確認する。

順番:

```text
直進低速
小さいステア角で低速
短時間の停止復帰
```

最初の床上走行は短時間、低速、広い場所で行う。

### 5. Simulink/Python MPCとの実機閉ループ確認

目的: Simulink/Python MPCの指令で実車が動くことを確認する。

最初は短い参照軌道で確認する。

見る項目:

```text
実車位置 x [m]
実車位置 y [m]
車体方位 phi [rad]
ステア角 psi [rad]
MPC入力 v [m/s]
MPC入力 omega または psi指令 [rad/s または rad]
Raspberry Pi出力 esc_duty [%]
Raspberry Pi出力 steering_duty [%]
```

### 6. データ保存

目的: シミュレーションと実機を比較できるログを残す。

最低限保存したい列:

```text
timestamp [s]
x_ref [m]
y_ref [m]
phi_ref [rad]
x_actual [m]
y_actual [m]
phi_actual [rad]
target_speed_mps [m/s]
target_steer_rad [rad]
esc_duty [%]
steering_duty [%]
status
```

### 7. 比較グラフ作成

目的: 先輩のシミュレーション結果と同じ観点で実機結果を見る。

作るグラフ:

```text
x_ref と x_actual
y_ref と y_actual
x-y軌跡
phi応答
ステア角応答
速度入力
PWM duty出力
位置誤差
RMSE
```

## 現在の次の作業

1. `esc_duty 約 10.200 %` で低速走行できた設定を基準値として扱う。
2. ステアリング方向が期待方向と一致するか確認する。
3. Param_init、watchdog、Ctrl-Cで中立復帰することを再確認する。
4. 短時間の直進低速確認を行う。
5. 短い参照軌道でSimulink/Python MPCの実機閉ループ確認へ進む。

## 判断基準

次へ進んでよい条件:

```text
PWM sender=... status=ok が出る
ステアリングが想定通り動く
ESCが低速で反応する
Param_initで中立に戻る
watchdogで中立に戻る
Ctrl-Cで中立に戻る
```

止める条件:

```text
ステアリング方向が不明
ESCが急に強く回る
中立に戻らない
REJECTが出続ける
GPIO配線が確認できない
GND共通が確認できない
物理的な電源遮断ができない
```
