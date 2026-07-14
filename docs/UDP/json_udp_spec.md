# JSON UDP通信仕様書

## 目的

外部PCとRaspberry Pi間で、MPPI制御や自律走行制御に使う前段階としてJSON形式のUDP通信を確認する。

この段階では通信確認のみを行い、GPIO、pigpio、ESC、ステアリングPWM、実車制御には接続しない。

## 現在のネットワーク構成

| 機器 | IPアドレス | 想定役割 |
| --- | --- | --- |
| Raspberry Pi | `192.168.11.4` | 実機I/O側 |
| 外部PC | `192.168.11.5` | 制御計算側 |

使用ポートは次を基本とする。

| 通信方向 | 受信側 | UDPポート |
| --- | --- | ---: |
| 外部PC -> Raspberry Pi | Raspberry Pi | `5005` |
| Raspberry Pi -> 外部PC | 外部PC | `5006` |

## 到達済みの文字列UDP通信

双方向の文字列UDP通信は確認済みである。

- 外部PCからRaspberry Piへ、`192.168.11.4:5005` に `"hello from pc"` を送信して受信確認済み。
- Raspberry Piから外部PCへ、`192.168.11.5:5006` に `"hello from raspberry pi"` を送信して受信確認済み。

これにより、SSH操作だけでなく、両機器間で直接UDPパケットを送受信できる通信経路を確認できている。

## JSONメッセージ形式

送信するJSONは1パケットにつき1個のJSON objectとする。

```json
{
  "target_steer_rad": 0.0,
  "target_speed_mps": 0.0,
  "timestamp": 1782800000.0
}
```

フィールドの単位はSI単位を使う。

| フィールド | 型 | 単位 | 説明 |
| --- | --- | --- | --- |
| `target_steer_rad` | number | rad | 目標ステア角 |
| `target_speed_mps` | number | m/s | 目標速度 |
| `timestamp` | number | s | UNIX時刻 |

角度は度[deg]ではなくラジアン[rad]で送る。

## 実装ファイル

実装は `UDP/` に置く。

| ファイル | 役割 |
| --- | --- |
| `UDP/json_protocol.py` | JSONメッセージの生成、検査、エンコード、デコード |
| `UDP/json_send.py` | JSON UDPパケットを1回送信する |
| `UDP/json_receive.py` | JSON UDPパケットを受信して検査・表示する |

## 外部PCからRaspberry Piへの確認手順

Raspberry Pi側で受信する。

```bash
python3 json_receive.py --host 0.0.0.0 --port 5005
```

外部PC側から送信する。

```bash
python3 json_send.py 192.168.11.4 --port 5005 --target-steer-rad 0.0 --target-speed-mps 0.0
```

## Raspberry Piから外部PCへの確認手順

外部PC側で受信する。

```bash
python3 json_receive.py --host 0.0.0.0 --port 5006
```

Raspberry Pi側から送信する。

```bash
python3 json_send.py 192.168.11.5 --port 5006 --target-steer-rad 0.0 --target-speed-mps 0.0
```

## 受信側の検査内容

受信側では次を確認する。

- UTF-8として読めること。
- JSONとして読めること。
- JSON objectであること。
- `target_steer_rad`、`target_speed_mps`、`timestamp` が存在すること。
- 各値が有限の数値であること。

現段階では、安全範囲制限やPWM変換は行わず、受信値を表示するだけにする。

## JSON UDP通信確認結果

2026-06-30に、外部PCとRaspberry Pi間でJSON UDP通信を双方向に確認した。

### 外部PCからRaspberry Pi

Raspberry Pi側で `0.0.0.0:5005` を待ち受け、外部PC `192.168.11.5` からRaspberry Pi `192.168.11.4:5005` へ送信した。

受信側では次のJSONを確認した。

```json
{"target_speed_mps":0.0,"target_steer_rad":0.0,"timestamp":1782802572.3358905}
```

受信値は次である。

```text
target_steer_rad=0.000000000 rad
target_speed_mps=0.000000000 m/s
timestamp=1782802572.335891 s
```

送信元は `('192.168.11.5', 58729)` と表示された。`58729` は外部PC側で一時的に使われた送信元UDPポートである。

### Raspberry Piから外部PC

外部PC側で `0.0.0.0:5006` を待ち受け、Raspberry Pi `192.168.11.4` から外部PC `192.168.11.5:5006` へ送信した。

受信側では次のJSONを確認した。

```json
{"target_speed_mps":0.0,"target_steer_rad":0.0,"timestamp":1782802651.1887527}
```

受信値は次である。

```text
target_steer_rad=0.000000000 rad
target_speed_mps=0.000000000 m/s
timestamp=1782802651.188753 s
```

送信元は `('192.168.11.4', 39057)` と表示された。`39057` はRaspberry Pi側で一時的に使われた送信元UDPポートである。

### 停止方法

`json_receive.py` は `--once` を指定しない場合、受信待ちを継続する。手動で `Ctrl-C` 停止したときに `KeyboardInterrupt` が表示されるのは正常である。

## 次の段階

JSON通信確認後は、UDP受信値を実車PWMへ接続する。

UDP通信を使わないPWM単体確認は成功済みと仮定し、次段階では最初から低速走行指令を扱う。詳細は `docs/UDP/pwm_control_plan.md` に記載する。

初回の実車確認では、駆動輪を浮かせ、`target_speed_mps = 0.10 m/s` 程度の低速指令から始める。通信途絶時はウォッチドッグでステアリング中立、ESC中立へ戻す。
