import socket
import struct

PORT = 5005
FMT = "<ddd"
NBYTES = struct.calcsize(FMT)
MAX_PACKET_BYTES = 1024


def decode_packet(data):
    if len(data) != NBYTES:
        return None
    return struct.unpack(FMT, data)

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(("0.0.0.0", PORT))

print(f"waiting UDP on port {PORT}...")
print(f"accepting {NBYTES} byte float64x3 packets")

while True:
    data, addr = sock.recvfrom(MAX_PACKET_BYTES)
    values = decode_packet(data)
    if values is None:
        print(f"skip {addr}: unexpected packet size {len(data)} bytes")
        continue

    value_1, value_2, value_3 = values
    print(
        addr,
        f"value_1={value_1:.9f}",
        f"value_2={value_2:.9f}",
        f"value_3={value_3:.9f}",
    )
