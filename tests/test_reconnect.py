"""Connection loss and automatic reconnection (spec.md 11c)."""

from __future__ import annotations

import asyncio
import logging

import pytest

from custom_components.viega_fonterra_modbus.modbus_handler import (
    RECONNECT_BACKOFF_INITIAL,
    ModbusClientError,
    ModbusConnectionLost,
    ViegaModbusClient,
)


class FakeConnection:
    """One scripted TCP connection to a fake Modbus device.

    `script` holds one action per request on this connection: "ok" (answer
    normally), "eof" (peer closed), "hang" (never answer), "bad_tid" (answer
    with a wrong transaction ID), "exception" (Modbus exception response),
    or an exception instance raised from `drain()`. Requests beyond the
    script are answered normally.
    """

    def __init__(self, *script) -> None:
        self.script = list(script)
        self.sent: list[bytes] = []
        self.closed = False
        self._pending = b""
        self._drain_error: BaseException | None = None
        self.reader = _FakeReader(self)
        self.writer = _FakeWriter(self)

    def _next_action(self):
        return self.script.pop(0) if self.script else "ok"

    def build_response(self, action: str) -> bytes:
        request = self.sent[-1]
        transaction_id = b"\xff\xff" if action == "bad_tid" else request[0:2]
        function_code = request[7]
        if action == "exception":
            pdu = bytes([function_code | 0x80, 0x02])
        elif function_code in (0x03, 0x04):
            count = int.from_bytes(request[10:12], "big")
            data = b"".join((210 + i).to_bytes(2, "big") for i in range(count))
            pdu = bytes([function_code, len(data)]) + data
        else:
            pdu = bytes([function_code]) + request[8:12]
        return transaction_id + b"\x00\x00" + (len(pdu) + 1).to_bytes(2, "big") + b"\x01" + pdu


class _FakeWriter:
    def __init__(self, conn: FakeConnection) -> None:
        self.conn = conn

    def write(self, data: bytes) -> None:
        self.conn.sent.append(bytes(data))
        action = self.conn._next_action()
        if isinstance(action, BaseException):
            self.conn._drain_error = action
        else:
            self.conn._action = action

    async def drain(self) -> None:
        error, self.conn._drain_error = self.conn._drain_error, None
        if error is not None:
            raise error

    def close(self) -> None:
        self.conn.closed = True

    async def wait_closed(self) -> None:
        return None


class _FakeReader:
    def __init__(self, conn: FakeConnection) -> None:
        self.conn = conn

    async def read(self, n: int) -> bytes:
        conn = self.conn
        if not conn._pending:
            action = conn._action
            if action == "eof":
                return b""
            if action == "hang":
                await asyncio.sleep(10)
                return b""
            conn._pending = conn.build_response(action)
        data, conn._pending = conn._pending[:n], conn._pending[n:]
        return data


def install_device(monkeypatch, *connections):
    """Make `asyncio.open_connection` hand out `connections` in order; an
    exception instance in the list is raised for that attempt instead."""
    queue = list(connections)
    attempts: list[object] = []

    async def fake_open_connection(host, port):
        item = queue.pop(0)
        attempts.append(item)
        if isinstance(item, BaseException):
            raise item
        return item.reader, item.writer

    monkeypatch.setattr(asyncio, "open_connection", fake_open_connection)
    return attempts


def make_client(**kwargs) -> ViegaModbusClient:
    return ViegaModbusClient("192.168.1.50", 502, timeout=kwargs.pop("timeout", 0.05), **kwargs)


def test_read_reconnects_and_retries_once_after_peer_closed_the_connection(monkeypatch, caplog):
    first = FakeConnection("ok", "eof")
    second = FakeConnection()
    attempts = install_device(monkeypatch, first, second)
    client = make_client()

    async def run():
        await client.connect()
        assert await client.read_holding_registers(0, 1) == [210]
        # The device restarted: the next read hits EOF on the old socket and
        # must transparently succeed on a new one.
        return await client.read_input_registers(5, 2)

    with caplog.at_level(logging.INFO):
        assert asyncio.run(run()) == [210, 211]

    assert attempts == [first, second]
    assert first.closed is True
    assert client.reconnect_count == 1
    assert client.last_reconnect_time is not None
    assert client.consecutive_failures == 0
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    infos = [r for r in caplog.records if "restored" in r.getMessage()]
    assert len(warnings) == 1 and "lost" in warnings[0].getMessage()
    assert len(infos) == 1


def test_socket_error_on_send_is_reported_as_modbus_client_error(monkeypatch):
    first = FakeConnection(ConnectionResetError("reset by peer"))
    second = FakeConnection()
    install_device(monkeypatch, first, second)
    client = make_client()

    async def run():
        await client.connect()
        return await client.read_holding_registers(0, 1)

    # Retried on a new connection, so the caller never sees the OSError.
    assert asyncio.run(run()) == [210]
    assert client.reconnect_count == 1


def test_read_is_retried_at_most_once(monkeypatch):
    install_device(monkeypatch, FakeConnection("eof"), FakeConnection("eof"))
    client = make_client()

    async def run():
        await client.connect()
        await client.read_holding_registers(0, 1)

    with pytest.raises(ModbusConnectionLost):
        asyncio.run(run())
    assert client.consecutive_failures == 1


def test_timeout_discards_the_connection_so_a_late_response_is_never_used(monkeypatch):
    first = FakeConnection("hang")
    second = FakeConnection()
    attempts = install_device(monkeypatch, first, second)
    client = make_client()

    async def run():
        await client.connect()
        with pytest.raises(ModbusClientError, match="timeout"):
            await client.read_holding_registers(0, 1)
        assert client._connected is False
        return await client.read_holding_registers(1, 1)

    assert asyncio.run(run()) == [210]
    assert attempts == [first, second]
    assert first.closed is True


def test_transaction_id_mismatch_discards_the_connection(monkeypatch):
    first = FakeConnection("bad_tid")
    second = FakeConnection()
    attempts = install_device(monkeypatch, first, second)
    client = make_client()

    async def run():
        await client.connect()
        with pytest.raises(ValueError, match="transaction ID mismatch"):
            await client.read_holding_registers(0, 1)
        return await client.read_holding_registers(0, 1)

    assert asyncio.run(run()) == [210]
    assert attempts == [first, second]


def test_modbus_exception_response_keeps_the_connection(monkeypatch):
    only = FakeConnection("exception")
    attempts = install_device(monkeypatch, only)
    client = make_client()

    async def run():
        await client.connect()
        with pytest.raises(ModbusClientError) as excinfo:
            await client.read_holding_registers(0, 1)
        assert excinfo.value.exception_code == 2
        return await client.read_holding_registers(0, 1)

    assert asyncio.run(run()) == [210]
    assert attempts == [only]
    assert only.closed is False
    assert client.reconnect_count == 0


def test_write_is_never_retried(monkeypatch):
    first = FakeConnection("eof")
    second = FakeConnection()
    attempts = install_device(monkeypatch, first, second)
    client = make_client()

    async def run():
        await client.connect()
        with pytest.raises(ModbusConnectionLost):
            await client.write_register(1, 215)
        # The failed write did not reconnect or resend anything ...
        assert attempts == [first]
        assert len(first.sent) == 1
        # ... but the next write uses a new connection.
        await client.write_register(1, 215)

    asyncio.run(run())
    assert attempts == [first, second]
    assert len(second.sent) == 1


def test_failed_reconnect_backs_off_and_fails_fast(monkeypatch):
    first = FakeConnection("eof")
    third = FakeConnection()
    attempts = install_device(
        monkeypatch, first, OSError("unreachable"), OSError("unreachable"), third
    )
    client = make_client(reconnect_backoff_max=12)

    async def run():
        await client.connect()
        # EOF on the old socket, then the immediate reconnect for the retry fails.
        with pytest.raises(ModbusClientError, match="failed"):
            await client.read_holding_registers(0, 1)
        assert len(attempts) == 2
        # Within the back-off window no new attempt is made at all.
        with pytest.raises(ModbusClientError, match="next reconnect attempt"):
            await client.read_holding_registers(0, 1)
        assert len(attempts) == 2
        assert client._reconnect_backoff == RECONNECT_BACKOFF_INITIAL * 2

        # Back-off elapsed: one more failing attempt doubles the delay up to the cap.
        client._next_reconnect_at = 0.0
        with pytest.raises(ModbusClientError):
            await client.read_holding_registers(0, 1)
        assert len(attempts) == 3
        assert client._reconnect_backoff == 12

        client._next_reconnect_at = 0.0
        return await client.read_holding_registers(0, 1)

    assert asyncio.run(run()) == [210]
    assert client._reconnect_backoff == RECONNECT_BACKOFF_INITIAL
    assert client.reconnect_count == 1


def test_connection_loss_is_logged_once_across_repeated_failures(monkeypatch, caplog):
    install_device(
        monkeypatch,
        FakeConnection("eof"),
        # one for the immediate retry, one for each of the two later polls
        OSError("unreachable"),
        OSError("unreachable"),
        OSError("unreachable"),
    )
    client = make_client()

    async def run():
        await client.connect()
        for _ in range(3):
            client._next_reconnect_at = 0.0
            with pytest.raises(ModbusClientError):
                await client.read_holding_registers(0, 1)

    with caplog.at_level(logging.DEBUG):
        asyncio.run(run())

    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(warnings) == 1


def test_no_reconnect_after_disconnect(monkeypatch):
    attempts = install_device(monkeypatch, FakeConnection())
    client = make_client()

    async def run():
        await client.connect()
        await client.disconnect()
        with pytest.raises(ModbusClientError, match="not connected"):
            await client.read_holding_registers(0, 1)

    asyncio.run(run())
    assert len(attempts) == 1


def test_cancelled_request_discards_the_connection(monkeypatch):
    first = FakeConnection("hang")
    second = FakeConnection()
    attempts = install_device(monkeypatch, first, second)
    client = make_client(timeout=5)

    async def run():
        await client.connect()
        task = asyncio.create_task(client.read_holding_registers(0, 1))
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert client._connected is False
        return await client.read_holding_registers(0, 1)

    assert asyncio.run(run()) == [210]
    assert attempts == [first, second]


def test_initial_connect_wraps_socket_errors(monkeypatch):
    install_device(monkeypatch, ConnectionRefusedError("refused"))
    client = make_client()

    with pytest.raises(ModbusClientError, match="refused"):
        asyncio.run(client.connect())
