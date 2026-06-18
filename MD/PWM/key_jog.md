# key_jog.py 修正案：表示値と実出力の不一致を解消する

## 背景・目的

`key_jog.py` では、`spd_ref` / `str_ref`（速度・操舵のPWMデューティ比）をキー操作で増減させる。
安全制限（7.50〜13.00）は `duty100()` の中でかけているが、クランプされるのは**引数 `rate`（ローカルコピー）だけ**で、グローバルの `spd_ref` / `str_ref` は無制限のまま増減し続ける。

結果として：

- **実際のPWM出力**は 7.50〜13.00 に制限される（安全）
- **`print()` の表示**は制限外の値（例 `13.28`、`15` など）をそのまま出してしまう

この表示／実出力のズレには副作用がある。`s` を押し続けて表示が `15` まで上がると、戻すときに `15→13` の分まで余計に `w` を押さないと実出力が反応しない「むだ時間」が生じる。

**目的**：`spd_ref` / `str_ref` 自体を安全範囲にクランプし、表示と実出力を一致させる。挙動（範囲・中立値）は現状を維持する。

## 対象ファイル

- `scripts/device_test/rccar_tests/test_PWM/pigpio/key_jog.py`（このファイルのみ）

## 修正方針

安全制限の数値は1か所で管理し、ループ内でも参照できるようにする（マジックナンバーの重複を避ける）。

### 1. 安全制限をモジュールレベルに出し、clampヘルパを追加

`duty100()` 定義（現20〜28行目）の直前に定数とヘルパを置き、`duty100()` 本体をそれを使う形に書き換える。

```python
# safety limits for PWM duty (in %)
PWM_SAFE_MIN = 7.50
PWM_SAFE_MAX = 13.00

def clamp(value, low, high):
    return max(low, min(value, high))

# in pigpio, 1000,000 = 100%
# then duty100(100) = 100% duty rate
def duty100(rate):
    return int(clamp(rate, PWM_SAFE_MIN, PWM_SAFE_MAX) * 10000)
```

- `duty100()` 内のクランプは残す（defense-in-depth：万一クランプ漏れがあってもハードに過大値を出さない安全網）。

### 2. ループ内で、キー処理の直後に `spd_ref` / `str_ref` をクランプ

現状の `if key == ord('n'): ...`（88〜90行目）と PWM出力（92〜94行目）の**間**に追記する。

```python
        # clamp references so displayed values match the actual PWM output
        spd_ref = clamp(spd_ref, PWM_SAFE_MIN, PWM_SAFE_MAX)
        str_ref = clamp(str_ref, PWM_SAFE_MIN, PWM_SAFE_MAX)
```

これにより、98行目の `print("str,spd=", ...)` が表示する `str_ref` / `spd_ref` は常に 7.50〜13.00 に収まり、実際のPWM出力と一致する。

## 補足・設計判断

- 速度・操舵で同じ制限（7.50〜13.00）を共有する点は現状の `duty100()` と同じ挙動を維持。
- 中立値（操舵10.00 / 速度10.48）はいずれも範囲内なので `n` リセットは影響なし。
- 既存の `duty100()` 内コメント（`# min and max for safety input`）の内容はヘルパ/定数側に移すか削除する。

## 検証方法

ハードウェア（RPi + pigpio）がなくてもロジックは確認できる：

1. **挙動の手元確認**：`clamp` の動作を確認。
   - `clamp(15, 7.5, 13.0) == 13.0`
   - `clamp(5, 7.5, 13.0) == 7.5`
   - `clamp(10.48, 7.5, 13.0) == 10.48`
2. **実機（あれば）**：`sudo pigpiod` 後に `python3 key_jog.py` を実行し、
   - `s` を押し続けて表示が `13` で頭打ちになること（以前は `13` を超えて増え続けた）。
   - その状態から `w` を1〜2回押すと即座に表示・出力が下がり始めること（むだ時間が解消されていること）。
   - `n` で `str,spd= 10 10.48` に戻ること。
