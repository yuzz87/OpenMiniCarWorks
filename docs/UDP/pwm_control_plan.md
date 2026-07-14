# UDP PWM走行制御仕様書

## 目的

JSON UDP通信で外部PCからRaspberry Piへ送った制御指令を、Raspberry Pi側でPWM duty比[%]へ変換し、RCカーを実機で低速走行させる。

この仕様では、UDP通信を使わないPWM単体確認は成功済みと仮定する。そのため、UDP実機確認では最初から `target_speed_mps > 0.0` の走行指令を扱う。

ただし、初回確認は床上走行ではなく、駆動輪を床から浮かせた状態で行う。

## 現在の到達点

外部PCとRaspberry Pi間で、JSON UDP通信は双方向に確認済みである。

確認済み通信経路:

| 通信方向 | 送信側 | 受信側 | UDPポート |
| --- | --- | --- | ---: |
| PC -> Raspberry Pi | `192.168.11.5` | `192.168.11.4` | `5005` |
| Raspberry Pi -> PC | `192.168.11.4` | `192.168.11.5` | `5006` |

UDPなしのPWM確認は成功済みと仮定する。

## 対象JSON形式

外部PCからRaspberry Piへ、1パケットにつき1個のJSON objectを送る。

```json
{
  "target_steer_rad": 0.0,
  "target_speed_mps": 0.10,
  "timestamp": 1782800000.0
}
```

単位はSI単位を使う。

| フィールド | 型 | 単位 | 説明 |
| --- | --- | --- | --- |
| `target_steer_rad` | number | rad | 目標ステア角 |
| `target_speed_mps` | number | m/s | 目標速度 |
| `timestamp` | number | s | UNIX時刻 |

角度は度[deg]ではなくラジアン[rad]で送る。

## 実機走行確認の初期条件

初回のUDP PWM走行確認では、次の値から始める。

```text
target_steer_rad = 0.0 rad
target_speed_mps = 0.10 m/s
duration = 2.0 s
rate_hz = 20 Hz
```

ステアリング操作を含める場合も、最初は小さい角度に限定する。

```text
target_steer_rad = -0.05 rad から +0.05 rad
```

## 実機安全条件

実車でPWM出力を行う前に、次を満たすこと。

- 駆動輪を床から浮かせていること。
- 物理的に電源を切れる状態にしていること。
- Raspberry Pi、ESC、サーボ側のGNDが共通であること。
- Raspberry Pi GPIOへ5 V信号を直接入れないこと。
- 実車出力前にGPIO番号、PWM周波数、中立値を再確認すること。
- `pigpiod` が起動していること。
- 実車PWM出力は明示オプションでのみ有効にすること。
- 床上走行はこの仕様の対象外とする。

## PWM設定

現在の実機確認では、ステアリング確認スクリプトの値を基準にする。

| 項目 | 値 |
| --- | ---: |
| PWM周波数 | `70 Hz` |
| ESC GPIO | BCM `12` |
| ステアリング GPIO | BCM `13` |
| ステアリング中立duty | `10.895 %` |
| ESC中立duty | `10.55 %` |
| ステアリングduty安全下限 | `7.50 %` |
| ステアリングduty安全上限 | `13.00 %` |
| ESC duty安全下限 | `9.50 %` |
| ESC duty安全上限 | `13.00 %` |

注意: `scripts/ellipse_run/run_ellipse.py` はステアリングGPIO `17`、ESC GPIO `18` を使っている。今回のUDP PWM走行確認で使う配線がGPIO `12` / `13` なのか、GPIO `17` / `18` なのかを実車側で必ず確認する。

## ステアリング変換

現在のステアリング変換はduty比[%]を基準にしている。

```text
steer_angle_rad = -0.186785136654 * str_duty_percent + 2.018473280947
```

制御では逆変換を使う。

```text
str_duty_percent = (target_steer_rad - 2.018473280947) / -0.186785136654
```

初期安全範囲:

```text
abs(target_steer_rad) <= 0.314 rad
```

`0.314 rad` は約 `18 deg` である。

## ESC速度変換

現在の実測近似式は次である。

```text
speed_mps = -2.4618 * esc_duty_percent + 25.347
```

制御では逆変換を使う。

```text
esc_duty_percent = (25.347 - target_speed_mps) / 2.4618
```

ただし、`target_speed_mps = 0.0 m/s` 付近は近似式で外挿せず、ESC中立duty `10.55 %` をそのまま使う。

初期安全範囲:

```text
0.0 m/s <= target_speed_mps <= 0.30 m/s
```

負の `target_speed_mps` は受け付けない。

## ウォッチドッグ

UDP通信が途切れた場合、最後の走行指令を出し続けずに中立へ戻す。

初期値:

```text
watchdog_timeout = 0.30 s
```

判定はJSON内の `timestamp` ではなく、Raspberry PiがUDPパケットを受信した時刻で行う。PCとRaspberry Piの時計が完全に同期していなくても安全処理が働くようにするためである。

ウォッチドッグ発動時の出力:

```text
steering_duty_percent = 10.895 %
esc_duty_percent = 10.55 %
```

## 実装ファイル

実装は `UDP/` に置く。

| ファイル | 役割 |
| --- | --- |
| `UDP/json_protocol.py` | JSONメッセージの生成、検査、エンコード、デコード |
| `UDP/json_send.py` | JSON UDPパケットを1回送信する |
| `UDP/json_receive.py` | JSON UDPパケットを受信して検査・表示する |
| `UDP/json_stream_send.py` | PC側からJSON UDP指令を一定周期で送信する |
| `UDP/udp_pwm_receiver.py` | Raspberry Pi側でUDP JSONを受信し、PWM duty比[%]へ変換する |

`udp_pwm_receiver.py` はデフォルトではドライランである。実車PWM出力には次の3つのオプションが必要である。

```text
--enable-hardware
--confirm-wheels-lifted
--confirm-power-cutoff
```

## 実行手順

### 1. Raspberry Pi側ドライラン

まずPWMを出さずに、受信値と計算されたPWM duty比[%]だけを確認する。

Raspberry Pi側:

```bash
cd UDP
python3 -u udp_pwm_receiver.py --host 0.0.0.0 --port 5005 --max-speed-mps 0.30
```

PC側:

```bash
cd UDP
python3 json_stream_send.py 192.168.11.4 --port 5005 --target-steer-rad 0.0 --target-speed-mps 0.10 --duration 2.0 --rate-hz 20 --send-neutral-on-exit
```

期待する表示例:

```text
target_steer_rad=0.000000 rad
target_speed_mps=0.100000 m/s
steering_duty=10.806391 %
esc_duty=10.255504 %
status=ok
```

送信停止後、`watchdog_neutral` で中立へ戻ることを確認する。

### 2. Raspberry Pi側実PWM出力

駆動輪を浮かせ、物理停止手段を準備したうえで実行する。

Raspberry Pi側:

```bash
cd UDP
python3 -u udp_pwm_receiver.py --host 0.0.0.0 --port 5005 --max-speed-mps 0.30 --enable-hardware --confirm-wheels-lifted --confirm-power-cutoff
```

PC側:

```bash
cd UDP
python3 json_stream_send.py 192.168.11.4 --port 5005 --target-steer-rad 0.0 --target-speed-mps 0.10 --duration 2.0 --rate-hz 20 --send-neutral-on-exit
```

この時点で、駆動輪が低速で回り、送信終了後に停止することを確認する。

### 3. ステアリング付き低速走行

直進低速走行が確認できた後、小さいステア角を含める。

PC側:

```bash
python3 json_stream_send.py 192.168.11.4 --port 5005 --target-steer-rad 0.05 --target-speed-mps 0.10 --duration 2.0 --rate-hz 20 --send-neutral-on-exit
```

逆方向:

```bash
python3 json_stream_send.py 192.168.11.4 --port 5005 --target-steer-rad -0.05 --target-speed-mps 0.10 --duration 2.0 --rate-hz 20 --send-neutral-on-exit
```

## 合格条件

- PCから送ったJSONがRaspberry Pi側で受信される。
- `target_steer_rad` [rad] がステアリングduty[%]へ変換される。
- `target_speed_mps` [m/s] がESC duty[%]へ変換される。
- 駆動輪を浮かせた状態で低速回転する。
- `--send-neutral-on-exit` またはウォッチドッグにより中立へ戻る。
- Ctrl-C、例外、異常JSON、UDP途絶時に中立へ戻る。
- 安全範囲外の速度・ステア角がそのまま出力されない。

## 中止条件

次の状態が起きたら確認を中止し、中立PWMまたは電源遮断へ移る。

- 駆動輪が想定より速く回る。
- ステアリングが機械的限界へ当たる。
- ESCが中立で止まらない。
- UDP指令が途絶しても中立へ戻らない。
- GPIO番号や配線に不明点がある。
- Raspberry Pi、ESC、サーボのGND共通が確認できない。

## 次の拡張

初回の駆動輪浮かせ走行が成功した後、次を検討する。

1. 速度上限 `max_speed_mps` の段階的な引き上げ。
2. 速度指令のレート制限。
3. ステアリング指令のレート制限。
4. PC側で時系列のステア角・速度を送る走行パターン送信。
5. 床上低速走行のための停止エリアと物理安全手順の追加。
