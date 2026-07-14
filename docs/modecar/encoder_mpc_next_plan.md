# エンコーダ計測からMPC実車確認へ進む次期計画

作成日: 2026-07-13

状態: 2026-07-13、ユーザー方針により段階1・2およびMPC関連の後続計画は一旦保留。次はエンコーダを記録しながら行うPowered runを優先する。

## 目的

新しい実機で、エンコーダによる車輪速度・距離計測を安全に確立し、その結果をMotive、Simulink、Python MPC、Raspberry Pi受信ログと比較する。最終的には、直線参照に沿って前進し、目標位置で停止できるか確認する。

## 現在の確認状況

確認済み:

- A相をBCM GPIO 22で読み取れる。
- B相をBCM GPIO 27で読み取り、正逆方向を判定できる。
- カウントから距離を計算できる。
- パルス間隔から符号付き車輪速度を計算できる。
- 停止後に速度が`0.0 m/s`へ戻る。
- エンコーダ試験コードはESC、モーター、ステアリング、PWMへ出力しない。

暫定採用値:

```text
counts_per_wheel_rev = 36 count/rev
wheel_diameter       = 0.066 m
A phase              = BCM GPIO 22
B phase              = BCM GPIO 27
```

この値での換算:

```text
wheel circumference = pi * 0.066 = 約0.20735 m
distance per count   = pi * 0.066 / 36 = 約0.0057596 m/count
1 m走行時の期待値   = 1 / 0.0057596 = 約173.6 count
```

未確認:

- 接地荷重下の実効タイヤ周長
- Powered run時の電気ノイズとパルス取りこぼし
- エンコーダ車輪速度とMotive車体速度の差
- MPCが負速度を多く出す根本原因
- Pythonの`omega [rad/s]`から実車操舵角へのSimulink変換

## 方針

- `36 count/rev`を現段階の暫定値として使用する。
- 1回転手回しの`-34 count`だけを根拠に34へ変更しない。
- 実車前進方向で生カウントが負になるため、Powered run用ログではソフトウェアで符号を反転する。
- 既知距離手押しとMotive比較はユーザー判断で一旦保留する。
- 次はPowered runを優先するが、最初の動力試験は駆動輪リフトと物理電源カット確認を必須とする。
- エンコーダ追加によって、現在のMPC負速度問題を隠さない。
- Raspberry Pi側の負速度・速度上限・操舵上限の安全制限は維持する。
- 実車側の安全限界を引き上げてMPCへ合わせない。

---

## 段階1: 前進方向と既知距離の手押し確認

### 目的

- 実車前進方向でカウントが正か負か確認する。
- `36 count/rev`とタイヤ直径`0.066 m`による距離換算誤差を測る。

### 条件

- モーター電源は切る。
- PWM出力は行わない。
- 平坦な床で車体をまっすぐ手押しする。
- メジャーで開始点と終了点を測る。
- 可能なら`1.000 m`以上を使い、短距離の目印誤差を減らす。

### 実行例

Raspberry Pi上の現在のコピー位置:

```bash
cd ~/OpenMiniCarWorks/scripts/encoder
python3 encoder_speed_test.py \
  --use-hardware \
  --confirm-3v3-compatible \
  --confirm-common-ground \
  --duration-s 30 \
  --zero-timeout-s 0.6
```

### 記録する値

```text
手押し実距離 [m]
最終count [count]
エンコーダ表示距離 [m]
前進時のcount符号
CSVファイル名
```

### 計算

```text
distance_per_count_actual = 手押し実距離 / abs(count)
実効タイヤ周長           = distance_per_count_actual * 36
実効タイヤ直径           = 実効タイヤ周長 / pi
距離誤差率[%]             = (エンコーダ距離 - 実距離) / 実距離 * 100
```

### 判断

- 前進時にcountが負なら、最終運用で`--invert-direction`を使用するか方向規約を修正する。
- 距離誤差が小さければ`0.066 m`を暫定維持する。
- 距離誤差が再現性を持って大きい場合だけ、実効タイヤ直径を更新する。
- カウントが停止・飛躍・頻繁な正逆反転をする場合はPowered runへ進まない。

---

## 段階2: Motiveとの手押し比較

### 目的

エンコーダの車輪移動距離と、Motiveが計測する床に対する車体移動距離を比較する。

### 条件

- モーター電源は切る。
- 車体を直線に手押しする。
- エンコーダCSVとMotiveログを同じ試行で保存する。

### 比較する値

```text
エンコーダ総距離 [m]
Motive開始・終了位置から求めた距離 [m]
エンコーダ平均速度 [m/s]
Motive位置差分から求めた平均速度 [m/s]
```

Motiveの平面移動距離:

```text
sqrt((x_end - x_start)^2 + (y_end - y_start)^2)
```

### 注意

エンコーダは車輪周速度、Motiveは床に対する車体速度を測る。Powered runではタイヤ空転・横滑りにより差が生じ得る。

---

## 段階3: 低速Powered runのリフト確認

### 目的

モーター動作中でもエンコーダが安定してカウントできるか確認する。

### 実施前に必要な確認

- 駆動輪を床から浮かせる。
- 物理電源カットへすぐ手が届く。
- GPIO 12/13がESC・ステアリング出力、GPIO 22/27がエンコーダ入力である。
- ESC中立値、ステアリング中立値、前進方向を再確認する。
- Raspberry Pi、エンコーダ、BEC、ESC信号のGNDを共通にする。
- エンコーダ出力が3.3 V互換である。

### コード方針

元の`key_jog.py`は変更せず、別ファイル`key_jog_with_encoder.py`を作る。

必須機能:

- 起動時は速度・操舵とも中立。
- 最小の速度Jogから始める。
- BCM 22/27のcount、distance、speedを記録する。
- Duty比、エンコーダ速度、距離、時刻を同じCSVへ保存する。
- Enter、`n`、時間上限、Ctrl-C、例外で中立へ戻る。
- `finally`で中立を出し、コールバックとpigpio接続を終了する。

このPowered run用コードは、安全準備の明示確認後に作成する。

### 合格条件

- 前進指令中にcountが一方向へ連続して変化する。
- モーター動作時に不自然な高速カウントや符号反転がない。
- 中立後に速度が`0.0 m/s`へ戻る。
- Ctrl-Cと時間上限で中立へ戻る。

---

## 段階4: 短距離の床上直進とMotive比較

### 目的

接地時の実車速度・距離をエンコーダとMotiveで測り、ESC Duty比から速度への実測対応を得る。

### 条件

- 広い平坦な場所。
- 最初は短距離・低出力。
- ステアリングは中立固定。
- 物理電源カットを手元に置く。
- 走行上限距離と時間上限を両方設定する。

### 保存する値

```text
実時刻 [s]
ESC duty [%]
steering duty [%]
encoder count [count]
encoder distance [m]
encoder wheel speed [m/s]
Motive x, y [m]
Motive yaw [rad]
停止理由
```

### 評価

- エンコーダ速度とMotive速度の平均・最大・RMSEを比較する。
- 空転がある場合、エンコーダ速度がMotive速度より大きくなる。
- 直線でも操舵ずれや左右タイヤ差がある場合、Motiveの横方向変位を記録する。

---

## 段階5: Simulink/Python MPCのDRY原因確認

### 目的

実車を動かす前に、MPCが継続的な正速度を生成するか確認する。

### 条件

- Raspberry PiのPWM出力は無効。
- Motiveを見て実車を固定参照開始位置へ合わせる。
- 参照開始状態は現在のNotebook設定を維持する。

```text
[phi, x, y, psi] = [0 rad, 0 m, -2 m, 0 rad]
```

### 必須ログ

```text
[FIRST_RX] (flag, phi, x, y, psi)
ref_window[:, 0]
ref_window[:, -1]
U_log[:, 0]、すなわちMPC要求速度 [m/s]
U_log[:, 1]、すなわち操舵角速度 [rad/s]
solve time [s]
IPOPT success / return_status
Simulink変換後 raw1, raw2, raw3
Raspberry Pi DRY status
```

### 判断

- `FIRST_RX`と参照開始状態が一致するか確認する。
- 走行区間でMPC要求速度が正値を継続するか確認する。
- `negative_speed`が支配的なら実PWMへ進まない。
- `clamped_speed`が支配的なら参照速度・MPC上限・実車上限を合わせる。
- `omega [rad/s]`をSimulinkが操舵角として誤使用していないか確認する。

---

## 段階6: 原因に応じたMPC変更

DRY結果が出るまで、次を先に変更しない。

- 初期参照の自動シフト
- 速度下限`-0.1 m/s`から`0.0 m/s`への変更
- MPC最大速度`1.2 m/s`の変更
- `Q`、`R`、`Q_f`の変更

DRY結果に応じて変更する。

### 座標・方位不一致の場合

MotiveからPythonまでの原点、軸、yawゼロ、yaw正方向、単位を修正する。

### 前進専用設計を確定した場合

```text
v_min = 0.0 m/s
```

を候補とする。負速度を禁止する前に、負速度の根本原因を記録する。

### 速度範囲不一致の場合

- 参照速度を実測可能速度以下へ設定する。
- MPC最大速度を実車安全上限以下へ設定する。
- 実車安全上限を引き上げてMPCへ合わせない。

### 時間・距離不一致の場合

```text
SimTime >= goal_dist / v_ref + 減速・停止確認時間
```

を満たすよう、短い目標距離・低い参照速度・十分な実験時間を設定する。

---

## 段階7: MPCリフト確認

段階5のDRYが合格した後だけ実施する。

### 合格条件

- 正速度区間で車輪が意図方向へ回る。
- エンコーダ速度が有限かつ妥当。
- 負速度区間が想定外に支配しない。
- 送信停止、Ctrl-C、例外、watchdogで中立へ戻る。
- ステアリング方向がモデルと一致する。

---

## 段階8: 短いMPC床走行

段階7合格後だけ実施する。

### 最初の目的

参照追従性能の最適化ではなく、次を確認する。

1. 継続して前進できる。
2. 目標付近で減速・停止する。
3. Motive位置とエンコーダ距離を保存できる。
4. MPC要求値とRaspberry Pi適用値を区別できる。

### 保存する系列

```text
MPC要求v [m/s]
MPC要求omega [rad/s]
Simulink raw1, raw2, raw3
Raspberry Pi制限後速度・操舵
ESC・steering duty [%]
encoder distance・speed
Motive x・y・yaw
各データの実時刻
status、停止理由
```

### 注意

エンコーダだけでデッドレコニングすると、タイヤ滑り、タイヤ径誤差、操舵校正誤差、機械的バックラッシュが位置・姿勢ドリフトとして累積する。Motiveを基準に比較する。

---

## 直近で一つだけ行う作業

エンコーダ速度・距離を同じCSVへ記録する低速Powered run用コードを準備する。

ユーザー方針により、既知距離手押し、Motive比較、MPC関連計画は一旦飛ばす。ただし実車を動かすため、次の安全情報をコード作成・実行前に確定する。

```text
駆動輪を床から浮かせているか
物理電源カットへ手が届くか
現在のESC中立Duty比[%]
前進時にDuty比を下げる規約でよいか
ステアリング中立Duty比[%]
```

前進方向のエンコーダ符号は確認済みであり、Powered run用コードでは`invert_direction = True`を使用する。

### 安全条件の確認結果

```text
駆動輪リフト: 確認済み
物理電源カット: 確認済み
前進はDuty比を下げる: 確認済み
ESC中立: 10.3 %
ステアリング中立: 10.895 %
```

### 実装済みファイル

```text
scripts/device_test/rccar_tests/test_encoder/key_jog_with_encoder.py
```

主な既定値:

```text
ESC GPIO                 = BCM 12
steering GPIO            = BCM 13
PWM frequency            = 70 Hz
ESC neutral              = 10.3 %
steering neutral         = 10.895 %
initial forward limit    = 10.1 %
forward step             = 0.02 %
encoder A/B              = BCM 22/27
counts per wheel rev     = 36
wheel diameter           = 0.066 m
encoder forward inversion = enabled
run time limit           = 10 s
```

このファイルは床走行を許可せず、駆動輪リフト、物理電源カット、前進Duty方向、3.3 V互換、共通GNDの確認フラグをすべて要求する。

操作:

```text
r       arm。これだけでは動かない
w       前進を1段増やす。Duty比を0.02 %下げる
s       1段中立へ戻す
n       即時中立・disarm
Enter/q 中立にして終了
```

正常終了、時間上限、Ctrl-C、例外のすべてでESCとステアリングを中立へ戻し、CSVへ終了理由を保存する。

### DRY確認結果

2026-07-13、Raspberry Pi上の次の場所でDRY実行した。

```text
~/OpenMiniCarWorks/scripts/encoder/key_jog_with_encoder.py
```

表示値:

```text
ESC neutral          = 10.300 %
steering neutral     = 10.895 %
forward range        = 10.300 % -> 10.200 %
forward step         = 0.020 %
encoder              = BCM22/27、36 count/rev、0.066 m
encoder forward sign = software inversion enabled
run time limit       = 10.0 s
```

結果:

```text
[DRY] GPIO、PWM、モーター、ステアリングへアクセスしていません。
```

DRY設定確認は合格。

### Powered runで判明したESC・ステアリング値

ユーザー実測:

```text
ESC 10.2 %: 駆動輪リフト時に空転を開始する下限付近
ESC 10.1 %: 接地時に車体が動き始める下限付近
steering 10.895 %: 中立を確認
```

`10.2 %`から`10.1 %`へDuty比を下げる変更は前進出力を強める。ユーザーの明示依頼に基づき、Powered runコードの既定前進上限を`10.1 %`へ変更した。

将来の誤実行防止のため、ハードウェア実行時に次の確認フラグを追加する。

```text
--confirm-forward-duty-limit
```

コードは引き続き駆動輪リフト専用であり、床走行を許可する変更は行っていない。

### リフトPowered runログ結果

キーイベント:

```text
armed: 確認
forward_step: 確認
```

実ログでは`10.28 %`と`10.26 %`でカウント変化がなく、`10.24 %`から回転を検出した。Duty比を下げるにつれて無負荷車輪速度の絶対値が増加した。

```text
10.24 %: 最大約0.62 m/s
10.22 %: 最大約0.83 m/s
10.20 %: 最大約1.04 m/s
10.18 %: 最大約1.09 m/s
```

10秒の時間上限で終了したため、今回のログでは`10.10 %`まで到達していない。

終了時:

```text
neutral_exit:time_limit
ESC = 10.3 %
steering = 10.895 %
encoder speed = 0.0 m/s
```

中立復帰は合格。

符号確認結果:

- ユーザー確認により、Powered runの車輪は物理的な前進方向だった。
- `invert_direction = True`で負ログになったため、統合コードを`invert_direction = False`へ修正した。
- 手回し時の方向認識ではなく、実際の駆動前進方向を運用基準とする。

残る確認:

- 修正後の低出力リフト試験でcountとspeedが主に正になること。
- 高速域に少数混ざった逆符号カウントが再発しないか。
- 中立終了行が維持されること。

床走行へ進む前に、この短い符号確認だけを実施する。

速度設定についてはユーザー判断で現状を維持する。

```text
ESC neutral        = 10.3 %
forward duty limit = 10.1 %
forward duty step  = 0.02 %
```

`10.24 %`への一時制限は必須変更ではなく、低出力の符号確認に使える任意オプションとする。コード既定値は`10.1 %`から変更しない。

### 未更新版で10.1 %まで実行した結果

ユーザーは速度設定を変更せず、物理的な前進方向で`10.1 %`までリフト試験した。

確認済み:

- `r`と`w`のキー入力は正常。
- Duty比は`10.30 %`から`10.10 %`まで`0.02 %`刻みで変化。
- 物理的な車輪回転は前進。
- 時間上限後にESC`10.3 %`、ステアリング`10.895 %`へ復帰。
- 最終速度は`0.0 m/s`。

問題:

- `10.1 %`付近で速度符号が約`±1.7 m/s`に頻繁に反転。
- countも増減し、符号付き累積距離が信頼できない。
- 車輪自体は逆転していないため、B相方向判定のソフトウェア遅延または信号タイミングが原因と考えられる。

対策:

- 前進専用JogではA相立ち上がりを常に正として数える。
- `WheelEncoder`へ`fixed_direction=1`を追加。
- `key_jog_with_encoder.py`から`fixed_direction=1`を指定。
- B相方向判定は汎用手回し試験では維持する。
- ESC・ステアリング・速度設定は変更しない。

この修正では共有クラスも変わるため、Raspberry Piへ`encoder_speed_test.py`と`key_jog_with_encoder.py`の両方を更新する必要がある。

### Raspberry Pi上のファイル版不一致

新版`key_jog_with_encoder.py`を実行した際、次の例外を確認した。

```text
TypeError: __init__() got an unexpected keyword argument 'fixed_direction'
```

原因:

- `key_jog_with_encoder.py`は`fixed_direction=1`を渡す新版。
- 同じ実行ディレクトリの`encoder_speed_test.py`は、`fixed_direction`をまだ持たない旧版。
- Pythonは`~/OpenMiniCarWorks/scripts/encoder/encoder_speed_test.py`をimportするため、2ファイルの版を揃える必要がある。

例外は中立出力後、キーボードループ開始前に発生した。`finally`でも中立処理を実行するため、この失敗では前進Dutyを出していない。

再実行前に、import元とコンストラクタ署名を確認する。

```bash
python3 -c "import encoder_speed_test, inspect; print(encoder_speed_test.__file__); print(inspect.signature(encoder_speed_test.WheelEncoder.__init__))"
```

署名に`fixed_direction`が含まれることを合格条件とする。
