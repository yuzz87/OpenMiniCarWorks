# RPi.GPIOでよく使うメソッド

## ライブラリの読み込み

```python
import RPi.GPIO as GPIO
```

Raspberry PiのGPIOを操作するライブラリを、`GPIO`という名前で読み込みます。

## GPIO番号の指定

### BCM番号を使用

```python
GPIO.setmode(GPIO.BCM)
```

`GPIO22`などのBCM番号で指定します。通常はこちらを使用します。

### 物理ピン番号を使用

```python
GPIO.setmode(GPIO.BOARD)
```

Raspberry Pi基板上の物理ピン番号で指定します。

## 入力ピンの設定

```python
GPIO.setup(22, GPIO.IN)
```

GPIO22を入力に設定します。

### プルアップを有効化

```python
GPIO.setup(22, GPIO.IN, pull_up_down=GPIO.PUD_UP)
```

未入力時の状態をHIGHに安定させます。

### プルダウンを有効化

```python
GPIO.setup(22, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
```

未入力時の状態をLOWに安定させます。

## 出力ピンの設定

```python
GPIO.setup(17, GPIO.OUT)
```

GPIO17を出力に設定します。

## GPIOの入力状態を取得

```python
state = GPIO.input(22)
```

GPIO22のHIGHまたはLOWを取得します。

```python
if GPIO.input(22) == GPIO.HIGH:
    print("HIGH")
else:
    print("LOW")
```

## HIGH・LOWを出力

```python
GPIO.output(17, GPIO.HIGH)
GPIO.output(17, GPIO.LOW)
```

- `GPIO.HIGH`：3.3V
- `GPIO.LOW`：0V

## 信号の変化を検出

```python
GPIO.add_event_detect(
    22,
    GPIO.RISING,
    callback=callback
)
```

GPIO22の信号変化を検出します。

検出方法は次の3種類です。

```python
GPIO.RISING   # LOWからHIGH
GPIO.FALLING  # HIGHからLOW
GPIO.BOTH     # 両方の変化
```

## コールバック関数

```python
def callback(channel):
    print("信号を検出したGPIO:", channel)
```

信号変化を検出したときに自動実行される関数です。

```python
GPIO.add_event_detect(
    22,
    GPIO.RISING,
    callback=callback
)
```

## チャタリング対策

```python
GPIO.add_event_detect(
    22,
    GPIO.FALLING,
    callback=callback,
    bouncetime=200
)
```

`bouncetime`で、信号検出後に次の信号を無視する時間を指定します。

単位はミリ秒です。

高速エンコーダではパルスを取りこぼす可能性があるため、基本的には使用しません。

## イベント検出を解除

```python
GPIO.remove_event_detect(22)
```

GPIO22の信号監視を終了します。

## PWMを使用

```python
GPIO.setup(18, GPIO.OUT)

# GPIO18、周波数50Hz
pwm = GPIO.PWM(18, 50)

# デューティ比7.5%で開始
pwm.start(7.5)

# デューティ比を変更
pwm.ChangeDutyCycle(10.0)

# 周波数を変更
pwm.ChangeFrequency(100)

# PWMを停止
pwm.stop()
```

サーボやESCを精密に制御する場合は、`RPi.GPIO.PWM`より`pigpio`が適しています。

## GPIO設定を解除

```python
GPIO.cleanup()
```

使用したGPIOを入力状態へ戻します。

プログラム終了時に実行します。

```python
try:
    # GPIOを使用する処理
    pass
finally:
    GPIO.cleanup()
```

特定のGPIOだけ解除することもできます。

```python
GPIO.cleanup(22)
```

## エンコーダでの使用例

```python
import RPi.GPIO as GPIO

ENCODER_A_PIN = 22
ENCODER_B_PIN = 27


def on_a_rising(channel):
    # A相の立ち上がり時にB相を確認
    if GPIO.input(ENCODER_B_PIN):
        print("後退")
    else:
        print("前進")


# BCM番号を使用
GPIO.setmode(GPIO.BCM)

# A相とB相を入力に設定
GPIO.setup(
    ENCODER_A_PIN,
    GPIO.IN,
    pull_up_down=GPIO.PUD_UP
)

GPIO.setup(
    ENCODER_B_PIN,
    GPIO.IN,
    pull_up_down=GPIO.PUD_UP
)

# A相の立ち上がりを検出
GPIO.add_event_detect(
    ENCODER_A_PIN,
    GPIO.RISING,
    callback=on_a_rising
)

try:
    while True:
        pass
finally:
    # イベント検出とGPIO設定を解除
    GPIO.remove_event_detect(ENCODER_A_PIN)
    GPIO.cleanup()
```

## エンコーダでよく使うメソッド

```python
GPIO.setmode(GPIO.BCM)
GPIO.setup()
GPIO.input()
GPIO.add_event_detect()
GPIO.remove_event_detect()
GPIO.cleanup()
```

## 注意点

Raspberry PiのGPIOは3.3V用です。

5V信号をGPIOへ直接入力すると、Raspberry Piが故障する可能性があります。
