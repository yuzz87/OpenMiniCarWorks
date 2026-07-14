# このスクリプトは、実測した近似式を使って速度[m/s]とESC duty比[%]を相互変換する。
# 実機処理は含めない。

# 速度[m/s] = -ALPHA * duty比[%] + BETA
# 実測データから求めた車両固有の近似係数として扱う。
ALPHA = 2.7936
BETA = 28.833

# 変換結果を確認するためのduty比サンプル[%]。
DUTY_SAMPLES = [10.2, 10.1, 10.0, 9.9, 9.8, 9.7]

# 計算表示用の速度指令リスト[m/s]。
TARGET_SPEEDS_MPS = [0.25575, 0.634048, 0.968199, 1.238765, 1.464154, 1.6591]


def duty_to_speed_mps(duty_percent):
    """ESC duty比[%]から近似速度[m/s]を求める。"""
    return -ALPHA * duty_percent + BETA


def speed_to_duty(speed_mps):
    """目標速度[m/s]から必要なESC duty比[%]を求める。"""
    return (BETA - speed_mps) / ALPHA


def print_calculations(target_speeds_mps):
    """速度[m/s]とduty比[%]の変換結果だけを表示する。"""
    print("PWM変換計算")

    print("duty比[%] -> 速度[m/s]")
    for duty_percent in DUTY_SAMPLES:
        speed_mps = duty_to_speed_mps(duty_percent)
        print(f"duty比: {duty_percent:.3f} %, 速度: {speed_mps:.6f} m/s")

    print()
    print("速度[m/s] -> duty比[%]")
    for speed_mps in target_speeds_mps:
        duty_percent = speed_to_duty(speed_mps)
        print(f"速度: {speed_mps:.6f} m/s, duty比: {duty_percent:.3f} %")


def main():
    """計算結果だけを表示する。"""
    print_calculations(TARGET_SPEEDS_MPS)


if __name__ == "__main__":
    main()
