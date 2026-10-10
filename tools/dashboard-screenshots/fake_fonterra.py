"""Simulated Viega Fonterra base unit (Modbus TCP) for README screenshots.

Anonymous example installation: 4 rooms, 5 heating circuits. Register layout
as in spec.md 5b (PDU addresses = last four digits of the manual address).
"""
import asyncio
import math
import struct
import sys
import time

ROOMS = {  # room number: (name, actuators, current, target, power level)
    1: ("Bad", [1], 224, 230, 5),
    2: ("Schlafzimmer", [2, 3], 186, 190, 3),
    3: ("Arbeitszimmer", [4], 208, 205, 4),
    4: ("Kinderzimmer", [5], 199, 200, 4),
}
OPEN = {1: 1, 2: 1, 3: 0, 4: 0, 5: 1}
RETURN = {1: 301, 2: 274, 3: 229, 4: 262, 5: 288}

holding: dict[int, int] = {1: 1, 2: 0}
inputs: dict[int, int] = {24: 0, 25: 345}


def put_text(start: int, count: int, text: str) -> None:
    raw = text.encode("ascii").ljust(count * 2, b"\0")
    for i in range(count):
        inputs[start + i] = int.from_bytes(raw[2 * i : 2 * i + 2], "big")


put_text(1, 5, "WM-0000001")
put_text(6, 5, "BU-0000001")
put_text(11, 12, "Fonterra Basis")
for n, (name, actors, cur, target, level) in ROOMS.items():
    inputs[48 + 2 * n] = cur
    inputs[49 + 2 * n] = 0
    holding[48 + 2 * n] = level
    holding[49 + 2 * n] = target
    put_text(74 + 12 * (n - 1), 12, name)
    for m in actors:
        base = 250 + 3 * (m - 1)
        inputs[base] = OPEN[m]
        inputs[base + 1] = RETURN[m]
        inputs[base + 2] = n
for m in range(1, 13):  # unused actuator slots report no room
    base = 250 + 3 * (m - 1)
    inputs.setdefault(base, 0)
    inputs.setdefault(base + 1, -99)
    inputs.setdefault(base + 2, 0)
START = time.time()


def live_value(table: dict[int, int], address: int) -> int:
    value = table.get(address, -99)
    if table is inputs:
        for n, (_, _, cur, _, _) in ROOMS.items():
            if address == 48 + 2 * n:  # gentle drift of room temperatures
                value = cur + round(2 * math.sin((time.time() - START) / 300 + n))
    return value


async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while True:
            header = await reader.readexactly(7)
            tid, pid, length, unit = struct.unpack(">HHHB", header)
            pdu = await reader.readexactly(length - 1)
            function = pdu[0]
            if function in (3, 4):
                address, count = struct.unpack(">HH", pdu[1:5])
                table = holding if function == 3 else inputs
                values = [live_value(table, address + i) for i in range(count)]
                body = bytes([function, 2 * count]) + b"".join(
                    struct.pack(">h", v) for v in values
                )
            elif function == 16:
                address, count, _ = struct.unpack(">HHB", pdu[1:6])
                for i in range(count):
                    holding[address + i] = struct.unpack(">H", pdu[6 + 2 * i : 8 + 2 * i])[0]
                body = bytes([16]) + struct.pack(">HH", address, count)
            else:
                body = bytes([function | 0x80, 1])
            writer.write(struct.pack(">HHHB", tid, pid, len(body) + 1, unit) + body)
            await writer.drain()
    except (asyncio.IncompleteReadError, ConnectionError):
        writer.close()


async def main(port: int) -> None:
    server = await asyncio.start_server(handle, "127.0.0.1", port)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 5020))
