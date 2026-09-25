"""Tests for the Viega Fonterra Modbus client."""

import asyncio
import logging
from types import SimpleNamespace

from custom_components.viega_fonterra_modbus.const import DOMAIN
from custom_components.viega_fonterra_modbus.modbus_handler import (
    ModbusClientError,
    ViegaModbusClient,
)
from custom_components.viega_fonterra_modbus.sensor import ViegaRegisterSensor


def _next_transaction_id() -> int:
    """The class-level transaction counter is shared across the whole test
    session, so frame-building tests must compute the expected transaction
    ID relative to its current value rather than assuming they run first.
    """
    return (ViegaModbusClient._transaction_counter + 1) & 0xFFFF


def test_client_initialization():
    """The client must carry the configured host and port."""
    client = ViegaModbusClient("192.168.1.50", 502)

    assert client.host == "192.168.1.50"
    assert client.port == 502
    assert hasattr(client, "read_holding_registers")


def test_read_request_is_built_with_modbus_tcp_frame():
    """The read request must be encoded as a valid Modbus/TCP frame."""
    expected_transaction_id = _next_transaction_id()
    request = ViegaModbusClient.build_read_request(1000, count=2)

    assert len(request) == 12
    assert request[0:2] == expected_transaction_id.to_bytes(2, "big")
    assert request[2:4] == b"\x00\x00"
    assert request[4:6] == b"\x00\x06"
    assert request[6] == 0x01
    assert request[7] == 0x03
    assert request[8:10] == (1000).to_bytes(2, "big")
    assert request[10:12] == (2).to_bytes(2, "big")


def test_write_request_is_built_with_modbus_tcp_frame():
    """The write request must be encoded as a valid function-code 0x10
    (Write Multiple Registers) frame, matching the manual's own worked
    wire example ("Beispiel 2 - Soll-Temperatur für Raum 2 setzen", page
    95: `00 02 00 00 00 09 01 10 00 35 00 01 02 00 D2`) - not function
    0x06, which no confirmed wire example in the manual ever uses."""
    expected_transaction_id = _next_transaction_id()
    request = ViegaModbusClient.build_write_request(0x35, 0xD2)

    assert request == expected_transaction_id.to_bytes(2, "big") + bytes.fromhex(
        "0000000901100035000102" + f"{0xD2:04x}"
    )
    assert len(request) == 15
    assert request[4:6] == b"\x00\x09"
    assert request[6] == 0x01
    assert request[7] == 0x10
    assert request[8:10] == (0x35).to_bytes(2, "big")
    assert request[10:12] == (1).to_bytes(2, "big")  # quantity of registers
    assert request[12] == 2  # byte count
    assert request[13:15] == (0xD2).to_bytes(2, "big")


def test_build_read_request_rejects_an_out_of_range_count():
    try:
        ViegaModbusClient.build_read_request(0, count=126)
    except ValueError:
        pass
    else:
        raise AssertionError("expected a ValueError for count > 125")


def test_decode_register_response_works_for_two_registers():
    """The decoder must turn a Modbus register payload into a value list."""
    payload = b"\x00\x01\x00\x00\x00\x06\x01\x03\x04\x00\x1e\x00\x2a"
    values = ViegaModbusClient.decode_register_response(payload)

    assert values == [30, 42]


def test_entity_update_reads_value_from_client():
    """The sensor entity should poll the register value from the client."""

    class FakeClient:
        async def read_holding_registers(self, address, count=1):
            assert address == 1000
            assert count == 1
            return [19]

    entity = ViegaRegisterSensor(
        SimpleNamespace(entry_id="abc123"),
        "temperature_flow",
        "Flow temperature",
        "°C",
        1000,
    )
    entity.hass = SimpleNamespace(data={DOMAIN: {"abc123": {"client": FakeClient()}}})

    import asyncio

    asyncio.run(entity.async_update())

    assert entity.state == 19


def test_entity_update_handles_modbus_errors_without_crashing():
    """A Modbus fault should not break the entity update cycle."""

    class FaultyClient:
        async def read_holding_registers(self, address, count=1):
            raise RuntimeError("device offline")

    entity = ViegaRegisterSensor(
        SimpleNamespace(entry_id="abc123"),
        "temperature_flow",
        "Flow temperature",
        "°C",
        1000,
    )
    entity.hass = SimpleNamespace(data={DOMAIN: {"abc123": {"client": FaultyClient()}}})

    import asyncio

    asyncio.run(entity.async_update())

    assert entity.state == 0


def test_entity_keeps_previous_value_on_error_sentinel():
    """A sentinel error value must retain the previous safe value."""
    class ErrorSentinelClient:
        async def read_holding_registers(self, address, count=1):
            return [-99]

    entity = ViegaRegisterSensor(
        SimpleNamespace(entry_id="abc123"),
        "temperature_flow",
        "Flow temperature",
        "°C",
        1000,
    )
    entity._attr_native_value = 21.5
    entity.hass = SimpleNamespace(data={DOMAIN: {"abc123": {"client": ErrorSentinelClient()}}})

    import asyncio

    asyncio.run(entity.async_update())

    assert entity.state == 21.5
    assert entity.last_error_message == "error: sensor invalid"


def test_entity_sets_error_message_on_communication_failure():
    """Communication failures must be recorded as a textual sensor error."""
    entity = ViegaRegisterSensor(
        SimpleNamespace(entry_id="abc123"),
        "temperature_flow",
        "Flow temperature",
        "°C",
        1000,
    )
    entity._attr_native_value = 18.0
    entity.hass = SimpleNamespace(data={DOMAIN: {"abc123": {"client": type("Client", (), {"read_holding_registers": lambda self, address, count=1: (_ for _ in ()).throw(RuntimeError("offline"))})()}}})

    import asyncio

    asyncio.run(entity.async_update())

    assert entity.state == 18.0
    assert entity.last_error_message == "error: communication timeout"


def test_transaction_id_is_checked_on_response():
    """A response with a mismatching transaction ID should be rejected."""
    response = b"\x00\x02\x00\x00\x00\x06\x01\x03\x04\x00\x1e\x00\x2a"

    try:
        ViegaModbusClient.validate_transaction_id(response, expected=1)
    except ValueError:
        pass
    else:
        raise AssertionError("Expected mismatched transaction ID to raise ValueError")


def test_frame_debug_logging_includes_protocol_metadata(caplog):
    """Debug logging must expose enough metadata to trace a frame exchange."""
    client = ViegaModbusClient("192.168.8.20", 502)
    frame = b"\x00\x01\x00\x00\x00\x06\x01\x03\x00\x00\x00\x01"

    with caplog.at_level(
        logging.DEBUG,
        logger="custom_components.viega_fonterra_modbus.modbus",
    ):
        client._log_frame("TX", frame)

    assert "Modbus TX frame" in caplog.text
    assert "transaction_id=1" in caplog.text
    assert "unit_id=1" in caplog.text
    assert "function=0x03" in caplog.text
    assert "hex=00 01 00 00 00 06 01 03 00 00 00 01" in caplog.text


def test_decode_register_response_is_signed_and_detects_error_sentinel():
    """Holding-register decoding must be signed so the -99 sentinel (spec.md
    10) is representable; unsigned decoding would turn it into 65437."""
    payload = b"\x00\x01\x00\x00\x00\x06\x01\x03\x02\xff\x9d"

    values = ViegaModbusClient.decode_register_response(payload)

    assert values == [-99]


def test_concurrent_reads_are_serialized_on_shared_connection():
    """Two concurrent reads on the same client must not interleave their
    TX/RX frames on the wire (spec.md 11b), since a real device only ever
    sees one connection shared by every entity of a config entry."""
    import asyncio

    log: list[tuple[str, bytes]] = []

    class FakeWriter:
        def write(self, data: bytes) -> None:
            log.append(("TX", bytes(data)))

        async def drain(self) -> None:
            await asyncio.sleep(0)

    class FakeReader:
        async def read(self, n: int) -> bytes:
            await asyncio.sleep(0.01)
            direction, last_tx = log[-1]
            assert direction == "TX", "a second request was sent before the first response was read"
            transaction_id = last_tx[0:2]
            response = transaction_id + b"\x00\x00\x00\x05\x01\x03\x02\x00\x01"
            log.append(("RX", response))
            return response

    client = ViegaModbusClient("192.168.1.50", 502)
    client._reader = FakeReader()
    client._writer = FakeWriter()
    client._connected = True

    async def run() -> None:
        await asyncio.gather(
            client.read_holding_registers(0, 1),
            client.read_holding_registers(1, 1),
        )

    asyncio.run(run())

    assert [direction for direction, _ in log] == ["TX", "RX", "TX", "RX"]


def test_frame_debug_logging_is_disabled_by_default(caplog):
    """No frame log should be emitted unless the Modbus logger is at DEBUG.

    Frame logging (spec.md 11a) is gated purely on Home Assistant's standard
    `logger.logs` mechanism (`_LOGGER.isEnabledFor(logging.DEBUG)`) - there
    is no separate per-client flag to keep in sync. Without raising the
    logger's level, `isEnabledFor(DEBUG)` is false and nothing is logged.
    """
    client = ViegaModbusClient("192.168.8.20", 502)

    with caplog.at_level(
        logging.WARNING,
        logger="custom_components.viega_fonterra_modbus.modbus",
    ):
        client._log_frame("TX", b"\x00\x01")

    assert not caplog.records


def test_frame_logging_is_safe_for_a_malformed_or_truncated_frame(caplog):
    """spec.md 11a: a malformed/truncated frame must still be safe to log
    and must not cause a secondary logging exception."""
    client = ViegaModbusClient("192.168.8.20", 502)

    with caplog.at_level(
        logging.DEBUG,
        logger="custom_components.viega_fonterra_modbus.modbus",
    ):
        client._log_frame("RX", b"")
        client._log_frame("RX", b"\x00")
        client._log_frame("RX", b"\x00\x01\x00\x00\x00")

    assert len(caplog.records) == 3


def test_frame_logging_follows_the_logger_level_directly(caplog):
    """Raising the Modbus logger to DEBUG is the only thing needed to turn
    frame logging on, and dropping back below DEBUG turns it back off - one
    control surface, not a separate per-client toggle."""
    client = ViegaModbusClient("192.168.8.20", 502)
    frame = b"\x00\x01\x00\x00\x00\x06\x01\x03\x00\x00\x00\x01"
    logger_name = "custom_components.viega_fonterra_modbus.modbus"

    with caplog.at_level(logging.WARNING, logger=logger_name):
        client._log_frame("TX", frame)
        assert not caplog.records

    with caplog.at_level(logging.DEBUG, logger=logger_name):
        client._log_frame("TX", frame)
        assert len(caplog.records) == 1


def test_validate_transaction_id_accepts_a_matching_response():
    response = b"\x00\x05\x00\x00\x00\x06\x01\x03\x04\x00\x1e\x00\x2a"

    # Must not raise.
    ViegaModbusClient.validate_transaction_id(response, expected=5)


def test_read_holding_registers_rejects_a_modbus_exception_response():
    """A device that rejects the request answers with the request's function
    code with its high bit set (0x03 -> 0x83) plus a one-byte exception code,
    not a valid data payload - this must be surfaced distinctly from a
    generic length error (spec.md 11)."""
    log: list[bytes] = []

    class FakeWriter:
        def write(self, data: bytes) -> None:
            log.append(bytes(data))

        async def drain(self) -> None:
            return None

    class FakeReader:
        async def read(self, n: int) -> bytes:
            transaction_id = log[-1][0:2]
            # MBAP header + function 0x83 (0x03 | 0x80) + exception code 02
            # ("illegal data address").
            return transaction_id + b"\x00\x00\x00\x03\x01\x83\x02"

    client = ViegaModbusClient("192.168.1.50", 502)
    client._reader = FakeReader()
    client._writer = FakeWriter()
    client._connected = True

    try:
        asyncio.run(client.read_holding_registers(0, 1))
    except ModbusClientError as err:
        assert "exception code 2" in str(err)
    else:
        raise AssertionError("expected a ModbusClientError for an exception response")


def test_read_input_registers_rejects_a_mismatched_function_code():
    """A response echoing a function code that is neither the request's own
    nor its exception variant indicates a misrouted/corrupted frame and must
    be rejected, not silently decoded (spec.md 11)."""
    log: list[bytes] = []

    class FakeWriter:
        def write(self, data: bytes) -> None:
            log.append(bytes(data))

        async def drain(self) -> None:
            return None

    class FakeReader:
        async def read(self, n: int) -> bytes:
            transaction_id = log[-1][0:2]
            # Echoes function 0x03 (holding registers) for a request that
            # asked for function 0x04 (input registers).
            return transaction_id + b"\x00\x00\x00\x05\x01\x03\x02\x00\x01"

    client = ViegaModbusClient("192.168.1.50", 502)
    client._reader = FakeReader()
    client._writer = FakeWriter()
    client._connected = True

    try:
        asyncio.run(client.read_input_registers(0, 1))
    except ValueError:
        pass
    else:
        raise AssertionError("expected a ValueError for a mismatched function code")


def test_read_holding_registers_rejects_a_register_count_that_does_not_match_the_request():
    """A device that echoes fewer/more registers than requested must not be
    decoded silently - the caller would otherwise read the wrong value at a
    given list index (spec.md 11)."""
    log: list[bytes] = []

    class FakeWriter:
        def write(self, data: bytes) -> None:
            log.append(bytes(data))

        async def drain(self) -> None:
            return None

    class FakeReader:
        async def read(self, n: int) -> bytes:
            transaction_id = log[-1][0:2]
            # Only one register's worth of data (byte_count=2) although two
            # registers (count=2) were requested.
            return transaction_id + b"\x00\x00\x00\x05\x01\x03\x02\x00\x01"

    client = ViegaModbusClient("192.168.1.50", 502)
    client._reader = FakeReader()
    client._writer = FakeWriter()
    client._connected = True

    try:
        asyncio.run(client.read_holding_registers(0, 2))
    except ModbusClientError as err:
        assert "1 register(s), expected 2" in str(err)
    else:
        raise AssertionError("expected a ModbusClientError for a register-count mismatch")


def test_validate_transaction_id_rejects_a_response_too_short_to_contain_one():
    try:
        ViegaModbusClient.validate_transaction_id(b"\x00\x01", expected=1)
    except ValueError:
        pass
    else:
        raise AssertionError("expected a ValueError for a response shorter than 6 bytes")


def test_decode_register_response_rejects_a_response_that_is_too_short():
    try:
        ViegaModbusClient.decode_register_response(b"\x00\x01\x00\x00\x00\x06\x01")
    except ModbusClientError:
        pass
    else:
        raise AssertionError("expected a ModbusClientError for a truncated response")


def test_decode_int16_response_rejects_an_odd_byte_count():
    # byte_count (index 8) is 3, which cannot represent whole 16-bit registers.
    payload = b"\x00\x01\x00\x00\x00\x06\x01\x04\x03\x00\x01\x00"
    try:
        ViegaModbusClient.decode_int16_response(payload)
    except ModbusClientError:
        pass
    else:
        raise AssertionError("expected a ModbusClientError for an odd byte_count")


def test_read_holding_registers_raises_when_not_connected():
    client = ViegaModbusClient("192.168.1.50", 502)

    try:
        asyncio.run(client.read_holding_registers(0, 1))
    except ModbusClientError:
        pass
    else:
        raise AssertionError("expected a ModbusClientError when not connected")


def test_read_input_registers_raises_when_not_connected():
    client = ViegaModbusClient("192.168.1.50", 502)

    try:
        asyncio.run(client.read_input_registers(0, 1))
    except ModbusClientError:
        pass
    else:
        raise AssertionError("expected a ModbusClientError when not connected")


def test_write_register_raises_when_not_connected():
    client = ViegaModbusClient("192.168.1.50", 502)

    try:
        asyncio.run(client.write_register(0, 1))
    except ModbusClientError:
        pass
    else:
        raise AssertionError("expected a ModbusClientError when not connected")


def test_read_holding_registers_reassembles_a_response_split_across_reads():
    """TCP is a byte stream, not message-framed: `StreamReader.read(n)` can
    legitimately return fewer bytes than a full frame even without EOF, if
    the response arrives split across more than one TCP segment. A response
    delivered one byte at a time must still decode correctly instead of
    being rejected as "too short" or silently truncated."""
    log: list[bytes] = []

    class FakeWriter:
        def write(self, data: bytes) -> None:
            log.append(bytes(data))

        async def drain(self) -> None:
            return None

    class OneByteAtATimeReader:
        def __init__(self, response: bytes) -> None:
            self._remaining = response

        async def read(self, n: int) -> bytes:
            if not self._remaining:
                return b""
            byte, self._remaining = self._remaining[:1], self._remaining[1:]
            return byte

    expected_transaction_id = _next_transaction_id()
    response = expected_transaction_id.to_bytes(2, "big") + (
        b"\x00\x00\x00\x05\x01\x03\x02\x00\x2a"
    )

    client = ViegaModbusClient("192.168.1.50", 502)
    client._reader = OneByteAtATimeReader(response)
    client._writer = FakeWriter()
    client._connected = True

    values = asyncio.run(client.read_holding_registers(0, 1))

    assert values == [42]


def test_read_input_registers_uses_function_code_0x04():
    """read_input_registers must send function code 0x04 on the wire, not
    the 0x03 used for holding registers."""
    log: list[bytes] = []

    class FakeWriter:
        def write(self, data: bytes) -> None:
            log.append(bytes(data))

        async def drain(self) -> None:
            return None

    class FakeReader:
        async def read(self, n: int) -> bytes:
            transaction_id = log[-1][0:2]
            return transaction_id + b"\x00\x00\x00\x05\x01\x04\x02\x00\x2a"

    client = ViegaModbusClient("192.168.1.50", 502)
    client._reader = FakeReader()
    client._writer = FakeWriter()
    client._connected = True

    values = asyncio.run(client.read_input_registers(49, 1))

    assert log[-1][7] == 0x04
    assert values == [42]


def test_write_register_sends_the_value_and_validates_the_response():
    log: list[bytes] = []

    class FakeWriter:
        def write(self, data: bytes) -> None:
            log.append(bytes(data))

        async def drain(self) -> None:
            return None

    class FakeReader:
        async def read(self, n: int) -> bytes:
            transaction_id = log[-1][0:2]
            # Echo response for function code 0x10 (manual page 95,
            # "Beispiel 2"): transaction/protocol/length, unit, function,
            # start register, quantity written - no value echoed back.
            return transaction_id + b"\x00\x00\x00\x06\x01\x10\x00\x32\x00\x01"

    client = ViegaModbusClient("192.168.1.50", 502)
    client._reader = FakeReader()
    client._writer = FakeWriter()
    client._connected = True

    asyncio.run(client.write_register(50, 205))

    assert log[-1][7] == 0x10
    assert log[-1][8:10] == (50).to_bytes(2, "big")
    assert log[-1][10:12] == (1).to_bytes(2, "big")  # quantity of registers
    assert log[-1][12] == 2  # byte count
    assert log[-1][13:15] == (205).to_bytes(2, "big")


def test_read_holding_registers_raises_on_timeout():
    class FakeWriter:
        def write(self, data: bytes) -> None:
            return None

        async def drain(self) -> None:
            return None

    class HangingReader:
        async def read(self, n: int) -> bytes:
            await asyncio.sleep(10)
            return b""

    client = ViegaModbusClient("192.168.1.50", 502, timeout=0.01)
    client._reader = HangingReader()
    client._writer = FakeWriter()
    client._connected = True

    try:
        asyncio.run(client.read_holding_registers(0, 1))
    except ModbusClientError:
        pass
    else:
        raise AssertionError("expected a ModbusClientError on read timeout")


def test_connect_opens_a_connection_and_marks_the_client_connected(monkeypatch):
    class FakeWriter:
        def close(self) -> None:
            return None

        async def wait_closed(self) -> None:
            return None

    class FakeReader:
        pass

    async def fake_open_connection(host, port):
        assert host == "192.168.1.50"
        assert port == 502
        return FakeReader(), FakeWriter()

    monkeypatch.setattr(asyncio, "open_connection", fake_open_connection)

    client = ViegaModbusClient("192.168.1.50", 502)
    asyncio.run(client.connect())

    assert client._connected is True
    assert client._reader is not None
    assert client._writer is not None


def test_connect_raises_modbus_client_error_on_timeout(monkeypatch):
    async def hanging_open_connection(host, port):
        await asyncio.sleep(10)

    monkeypatch.setattr(asyncio, "open_connection", hanging_open_connection)

    client = ViegaModbusClient("192.168.1.50", 502, timeout=0.01)

    try:
        asyncio.run(client.connect())
    except ModbusClientError:
        pass
    else:
        raise AssertionError("expected a ModbusClientError on connection timeout")

    assert client._connected is False


def test_disconnect_closes_the_writer_and_resets_state():
    closed = {"close": False, "wait_closed": False}

    class FakeWriter:
        def close(self) -> None:
            closed["close"] = True

        async def wait_closed(self) -> None:
            closed["wait_closed"] = True

    client = ViegaModbusClient("192.168.1.50", 502)
    client._writer = FakeWriter()
    client._reader = object()
    client._connected = True

    asyncio.run(client.disconnect())

    assert closed == {"close": True, "wait_closed": True}
    assert client._reader is None
    assert client._writer is None
    assert client._connected is False


def test_disconnect_is_a_noop_when_never_connected():
    """Must not raise even if disconnect() is called on a fresh client."""
    client = ViegaModbusClient("192.168.1.50", 502)

    asyncio.run(client.disconnect())

    assert client._connected is False


def test_disconnect_does_not_hang_when_wait_closed_never_returns():
    """spec.md 6a/13: removal must succeed even when the device's socket is
    already broken. `wait_closed()` has no built-in timeout and can hang
    forever if the peer never completes the TCP close handshake (e.g. the
    device just went offline) - disconnect() must bound it and still reset
    state instead of blocking the caller (and thus config entry removal)
    indefinitely."""

    class HangingWriter:
        def close(self) -> None:
            pass

        async def wait_closed(self) -> None:
            await asyncio.sleep(999)

    client = ViegaModbusClient("192.168.1.50", 502, timeout=0.01)
    client._writer = HangingWriter()
    client._reader = object()
    client._connected = True

    asyncio.run(asyncio.wait_for(client.disconnect(), timeout=2))

    assert client._reader is None
    assert client._writer is None
    assert client._connected is False


def test_disconnect_resets_state_even_when_wait_closed_raises():
    """A disconnect failure (e.g. ConnectionResetError) must still leave the
    client in a clean, reconnectable state rather than stuck 'connected'."""

    class RaisingWriter:
        def close(self) -> None:
            pass

        async def wait_closed(self) -> None:
            raise ConnectionResetError("connection reset by peer")

    client = ViegaModbusClient("192.168.1.50", 502)
    client._writer = RaisingWriter()
    client._reader = object()
    client._connected = True

    asyncio.run(client.disconnect())

    assert client._reader is None
    assert client._writer is None
    assert client._connected is False
