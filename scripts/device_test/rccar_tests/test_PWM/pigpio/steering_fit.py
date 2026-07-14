# ステアリング同定データから線形変換式を作る。
#
# 入力CSVは同じディレクトリの steering_data.csv とする。
# 必須列:
#   str_pulse_us
#   steer_angle_rad
#
# steer_angle_rad が空の場合は steer_angle_deg から変換する。

import csv
import math
from pathlib import Path


CSV_PATH = Path(__file__).with_name("steering_data.csv")
PWM_HZ = 70
MIN_ABS_SLOPE = 1.0e-12


def load_samples(csv_path):
    """CSVから(str_pulse_us, steer_angle_rad)を読み込む。"""
    samples = []
    with csv_path.open(newline="") as f:
        reader = csv.DictReader(f)
        for row_number, row in enumerate(reader, start=2):
            pulse_text = row.get("str_pulse_us", "").strip()
            if not pulse_text:
                continue
            pulse_us = float(pulse_text)
            angle_rad_text = row.get("steer_angle_rad", "").strip()
            if angle_rad_text:
                angle_rad = float(angle_rad_text)
            else:
                angle_deg_text = row.get("steer_angle_deg", "").strip()
                if not angle_deg_text:
                    print(f"skip line {row_number}: steer_angle_deg/rad is empty")
                    continue
                angle_deg = float(angle_deg_text)
                angle_rad = angle_deg * math.pi / 180.0
            samples.append((pulse_us, angle_rad))
    return samples


def fit_line(samples):
    """steer_angle_rad = a * str_pulse_us + b の係数を求める。"""
    if len(samples) < 2:
        raise ValueError(
            f"at least two valid samples are required, got {len(samples)}"
        )

    xs = [sample[0] for sample in samples]
    ys = [sample[1] for sample in samples]
    x_mean = sum(xs) / len(xs)
    y_mean = sum(ys) / len(ys)

    numerator = sum((x - x_mean) * (y - y_mean) for x, y in samples)
    denominator = sum((x - x_mean) ** 2 for x in xs)
    if denominator == 0:
        raise ValueError("str_pulse_us values must not all be the same")

    a = numerator / denominator
    b = y_mean - a * x_mean
    return a, b


def pulse_us_to_duty_percent(pulse_us):
    """パルス幅[us]をduty比[%]へ変換する。"""
    return pulse_us * PWM_HZ / 10000.0


def print_neutral_result(samples):
    """角度変化がない場合の中立候補を表示する。"""
    neutral_pulse_us = sum(pulse_us for pulse_us, _ in samples) / len(samples)
    neutral_duty_percent = pulse_us_to_duty_percent(neutral_pulse_us)
    print("中立専用データとして扱います。")
    print("角度がすべて同じため、ステア角[rad]からPWMへの変換式は作れません。")
    print()
    print("中立候補")
    print(f"NEUTRAL_PULSE_US = {neutral_pulse_us:.1f}")
    print(f"PWM_NEUTRAL_STR = {neutral_duty_percent:.4f}")
    print()
    print("steering_check.py で中立確認だけを行う場合は、")
    print("USE_NEUTRAL_ONLY = True")
    print(f"NEUTRAL_PULSE_US = {neutral_pulse_us:.1f}")
    print("として使ってください。")


def print_result(samples, a, b):
    """係数と各サンプルの誤差を表示する。"""
    if abs(a) < MIN_ABS_SLOPE:
        print_neutral_result(samples)
        return

    print("近似式")
    print(f"steer_angle_rad = {a:.12f} * str_pulse_us + {b:.12f}")
    print()
    print("逆変換")
    print(f"str_pulse_us = (target_steer_angle_rad - ({b:.12f})) / {a:.12f}")
    print()
    print("検証")
    print("str_pulse_us, measured_rad, predicted_rad, error_rad")
    for pulse_us, measured_rad in samples:
        predicted_rad = a * pulse_us + b
        error_rad = predicted_rad - measured_rad
        print(
            f"{pulse_us:.1f}, "
            f"{measured_rad:.6f}, "
            f"{predicted_rad:.6f}, "
            f"{error_rad:.6f}"
        )


def main():
    if not CSV_PATH.exists():
        print(f"CSVが見つかりません: {CSV_PATH}")
        print("同じディレクトリに steering_data.csv を作成してください。")
        return

    samples = load_samples(CSV_PATH)
    print(f"loaded samples: {len(samples)}")
    a, b = fit_line(samples)
    print_result(samples, a, b)


if __name__ == "__main__":
    main()
