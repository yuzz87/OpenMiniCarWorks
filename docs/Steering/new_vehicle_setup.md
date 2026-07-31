z# 新しい機体でのステアリング設定変更メモ

## 目的

既存の `Raspberry Pi + Simulink + Python + モーションキャプチャー` 構成を、新しい機体で動かすときに変更すべき項目を整理する。

特にステアリングについて、制御入力から実機PWMまでの変換を新しい機体に合わせる。

## 想定する制御の流れ

制御器が速度 `v [m/s]` とヨー角速度 `omega [rad/s]` を出す場合、実機ステアリングでは次の流れになる。

```text
v [m/s], omega [rad/s]
  -> 操舵角 delta [rad]
  -> ステアリングPWM duty比 [%]
  -> 実機の前輪角 / 実走行時の曲率
```

モーションキャプチャーは状態取得に使う。

```text
mocap -> x [m], y [m], yaw [rad]
```

## 変更するべき項目

### 1. ホイールベース

新しい機体のホイールベース `wheelbase_m` を実測する。

```text
wheelbase_m = 後輪軸中心から前輪操舵軸中心までの距離 [m]
```

`omega [rad/s]` から操舵角 `delta [rad]` へ変換するときに使う。

```text
delta_rad = atan(wheelbase_m * omega_radps / speed_mps)
```

`speed_mps` が小さいと操舵角が過大になるため、低速時は制限を入れる。

```text
abs(delta_rad) <= max_steer_rad
```

### 2. 最大ステア角

新しい機体で安全に使える最大操舵角を決める。

最初は小さめにする。

```text
max_steer_rad = 0.05 rad から 0.10 rad 程度
```

実測と低速走行で問題がなければ、段階的に広げる。

角度変換:

```text
steer_angle_rad = steer_angle_deg * pi / 180
```

### 3. ステアリング中立PWM

新しい機体ではステアリングサーボ、リンケージ、取り付け方向が異なるため、中立PWMを必ず測り直す。

記録する値:

```text
steering_neutral_duty_percent
```

中立確認では、前輪が直進に近く、サーボが無理に保持していない値を選ぶ。

### 4. ステアリング角からPWMへの変換式

現在の機体で使っている式は次である。

```text
steer_angle_rad = -0.186785136654 * steering_duty_percent + 2.018473280947
```

逆変換:

```text
steering_duty_percent = (target_steer_rad - 2.018473280947) / -0.186785136654
```

この係数は新しい機体へそのまま使わない。

新しい機体では、次の形で係数を作り直す。

```text
steer_angle_rad = steering_fit_a * steering_duty_percent + steering_fit_b
```

制御で使う逆変換:

```text
steering_duty_percent = (target_steer_rad - steering_fit_b) / steering_fit_a
```

左右差が大きい場合は、左側と右側で係数を分ける。

### 5. ステアリングPWM安全範囲

サーボやリンケージに無理が出ない範囲を決める。

記録する値:

```text
steering_safe_min_duty_percent
steering_safe_max_duty_percent
```

接地時に角度が出ないからといって、すぐに安全範囲を広げない。
サーボ音、リンケージ干渉、戻り不良があるduty比は使わない。

### 6. ESC中立PWM

新しい機体ではESCの中立も測り直す。

記録する値:

```text
esc_neutral_duty_percent
```

駆動輪を浮かせた状態で、モーターが前進も後退もしない値を確認する。

### 7. 速度からESC PWMへの変換式

現在の機体で使っている式は次である。

```text
velocity_mps = -2.4618 * esc_duty_percent + 25.347
```

逆変換:

```text
esc_duty_percent = (25.347 - target_velocity_mps) / 2.4618
```

この係数も新しい機体へそのまま使わない。

新しい機体では、低速から複数点を測定して次を作る。

```text
velocity_mps = speed_fit_a * esc_duty_percent + speed_fit_b
```

制御で使う逆変換:

```text
esc_duty_percent = (target_velocity_mps - speed_fit_b) / speed_fit_a
```

停止指令 `0.0 m/s` は外挿せず、ESC中立PWMを直接使う。

### 8. モーションキャプチャー座標系

モーションキャプチャーの座標系を制御座標系に合わせる。

確認する項目:

```text
x [m] の正方向
y [m] の正方向
yaw [rad] のゼロ方向
yaw [rad] の正方向
剛体マーカー中心と車体基準点のオフセット [m]
```

制御で使う車体基準点が後輪軸中心なら、モーションキャプチャーの剛体中心から後輪軸中心へのオフセットを補正する。

### 9. yaw角の符号とゼロ方向

新しい機体で、左旋回と右旋回の符号が制御側と一致しているか確認する。

確認方法:

```text
車体を反時計回りに少し回す
制御側の yaw [rad] が増えるか確認する
```

反時計回りを正とするなら、増えない場合は符号変換が必要である。

### 10. Raspberry Piへ送る指令形式

Simulink/PythonからRaspberry Piへ送る値の意味を統一する。

推奨する形式:

```text
target_speed_mps      [m/s]
target_steer_rad      [rad]
timestamp_s           [s]
```

制御器が `omega [rad/s]` を出す場合は、Raspberry Piへ送る前に操舵角 `target_steer_rad` へ変換する。

```text
target_steer_rad = atan(wheelbase_m * omega_radps / target_speed_mps)
```

`target_speed_mps` が小さいときは、ゼロ割りと過大操舵を避ける。

## 最初の実験手順

1. ステアリング中立PWMを確認する。
2. ESC中立PWMを確認する。
3. ステアリングPWM安全範囲を小さめに決める。
4. 浮遊状態でステアリング角を測る。
5. マット上の静止接地状態でステアリング角を測る。
6. 低速直進走行を確認する。
7. 小さい操舵角で短時間走行する。
8. モーションキャプチャーの軌跡から曲率を確認する。
9. 有効ステア角とPWMの対応を作る。
10. 最大ステア角と最大速度を段階的に広げる。

## 最初に使う安全側の値

初回実験では次のように小さく始める。

```text
max_steer_rad = 0.05 rad
target_speed_mps = 安定して動く最小速度
run_time_s = 1.0 s から 2.0 s
```

`0.05 rad` は約 `2.86 deg` である。

## 記録するデータ

実験ごとに次を記録する。

```csv
timestamp_s,x_m,y_m,yaw_rad,target_speed_mps,target_steer_rad,steering_duty_percent,esc_duty_percent,memo
```

固定ステア走行で有効ステア角を求める場合は、次も記録する。

```csv
target_steer_rad,steering_duty_percent,turn_radius_m,curvature_1pm,effective_steer_rad,memo
```

## 注意

- 別機体のPWM係数をそのまま使わない。
- 浮遊時に合っていても、マット上で同じ角度が出るとは限らない。
- 走行制御では、前輪角そのものより実走行時の曲率が重要である。
- 物理的に電源を切れる状態で実験する。
- 通信途絶、例外、停止操作ではESCとステアリングを中立へ戻す。
