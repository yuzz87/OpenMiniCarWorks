"""RCカー通信テスト用のJSON UDP共通処理。

このモジュールはJSONメッセージの作成、検査、エンコード、デコードだけを行う。
GPIO、pigpio、ESC、ステアリングPWM、実車ハードウェアにはアクセスしない。

単位:
- target_steer_rad: 目標ステア角[rad]
- target_speed_mps: 目標速度[m/s]
- timestamp: UNIX時刻[s]
"""

import json
import math
import time


# JSONメッセージに必ず含めるフィールド名。
REQUIRED_FIELDS = ("target_steer_rad", "target_speed_mps", "timestamp")

# 1個のUDPパケットとして受け取る最大サイズ[byte]。
MAX_PACKET_BYTES = 4096


def require_finite_number(value, field_name):
    """値が有限の数値であることを確認し、floatとして返す。"""
    if not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{field_name} must be finite")
    return result


def make_control_message(target_steer_rad, target_speed_mps, timestamp=None):
    """SI単位の制御指令メッセージを作る。"""
    # timestampが指定されない場合は、送信時点のUNIX時刻[s]を入れる。
    if timestamp is None:
        timestamp = time.time()

    return {
        "target_steer_rad": require_finite_number(
            target_steer_rad, "target_steer_rad"
        ),
        "target_speed_mps": require_finite_number(
            target_speed_mps, "target_speed_mps"
        ),
        "timestamp": require_finite_number(timestamp, "timestamp"),
    }


def validate_control_message(message):
    """デコード済みJSONが制御指令として正しいか検査し、正規化して返す。"""
    # JSON object以外、例えば配列や文字列だけのJSONは受け付けない。
    if not isinstance(message, dict):
        raise ValueError("message must be a JSON object")

    # 必須フィールドが欠けている場合は、どのフィールドが無いか表示する。
    missing_fields = [field for field in REQUIRED_FIELDS if field not in message]
    if missing_fields:
        raise ValueError("missing field(s): " + ", ".join(missing_fields))

    # make_control_messageを通すことで、各値が有限の数値かをまとめて確認する。
    return make_control_message(
        message["target_steer_rad"],
        message["target_speed_mps"],
        message["timestamp"],
    )


def encode_control_message(message):
    """制御指令メッセージをUDP送信用のUTF-8 JSON bytesへ変換する。"""
    normalized_message = validate_control_message(message)
    # separatorsを指定して、余分な空白を入れないコンパクトなJSONにする。
    text = json.dumps(
        normalized_message,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return text.encode("utf-8")


def decode_control_packet(packet):
    """UDPで受け取ったbytesをUTF-8 JSONとして読み、制御指令として検査する。"""
    text = packet.decode("utf-8")
    decoded_message = json.loads(text)
    return text, validate_control_message(decoded_message)
