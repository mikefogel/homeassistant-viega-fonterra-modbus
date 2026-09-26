"""Modbus TCP client for the Viega Fonterra Smart Control integration."""

from __future__ import annotations

import asyncio
import logging
import struct
import time
from datetime import datetime, timezone


_LOGGER = logging.getLogger("custom_components.viega_fonterra_modbus.modbus")


class ModbusClientError(RuntimeError):
    """Raised when a Modbus request cannot be processed.

    `exception_code` carries the device's own Modbus exception code (see
    `validate_function_code`) when this error was raised for that reason,
    so callers tracking connection health (spec.md 16b) can record it
    without re-parsing the error message.
    """

    def __init__(self, message: str, exception_code: int | None = None) -> None:
        super().__init__(message)
        self.exception_code = exception_code


class ViegaModbusClient:
    """Minimal Modbus TCP helper for the Fonterra system."""

    UNIT_ID = 1
    PROTOCOL_ID = 0
    ERROR_SENTINEL = -99
    _transaction_counter = 0

    def __init__(
        self, host: str, port: int = 502, timeout: float = 5
    ) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._connected = False
        self._lock = asyncio.Lock()
        self._recv_buffer = b""

        # Connection health metrics (spec.md 16b), derived entirely from
        # this client's own request/response bookkeeping - reading them
        # never issues an additional Modbus request of its own.
        self.last_success_time: datetime | None = None
        self.last_failure_time: datetime | None = None
        self.consecutive_failures: int = 0
        self.invalid_value_count: int = 0
        self.last_exception_code: int | None = None
        self.last_success_duration: float | None = None

    def _record_success(self, duration: float, invalid_values: int = 0) -> None:
        self.last_success_time = datetime.now(timezone.utc)
        self.last_success_duration = duration
        self.consecutive_failures = 0
        self.invalid_value_count += invalid_values

    def _record_failure(self, error: Exception) -> None:
        self.last_failure_time = datetime.now(timezone.utc)
        self.consecutive_failures += 1
        exception_code = getattr(error, "exception_code", None)
        if exception_code is not None:
            self.last_exception_code = exception_code

    def _log_frame(self, direction: str, frame: bytes) -> None:
        """Log a Modbus frame with decoded header fields at DEBUG level.

        Gated purely on the standard Home Assistant logger mechanism (see
        README "Modbus debug logging") rather than a separate config-entry
        toggle, so there is exactly one switch to enable frame logging and it
        can never end up silently out of sync with the logger level.
        """
        if not _LOGGER.isEnabledFor(logging.DEBUG):
            return
        transaction_id = (
            int.from_bytes(frame[0:2], byteorder="big") if len(frame) >= 2 else None
        )
        unit_id = frame[6] if len(frame) >= 7 else None
        function_code = frame[7] if len(frame) >= 8 else None
        _LOGGER.debug(
            "Modbus %s frame host=%s port=%s transaction_id=%s unit_id=%s "
            "function=0x%02x length=%d hex=%s",
            direction,
            self.host,
            self.port,
            transaction_id,
            unit_id,
            function_code or 0,
            len(frame),
            frame.hex(" "),
        )

    @staticmethod
    def validate_transaction_id(response: bytes, expected: int) -> None:
        """Reject mismatched Modbus TCP transaction IDs."""
        if len(response) < 6:
            raise ValueError("response too short for transaction validation")
        transaction_id = int.from_bytes(response[0:2], byteorder="big", signed=False)
        if transaction_id != expected:
            raise ValueError(
                f"transaction ID mismatch: expected {expected}, got {transaction_id}"
            )

    @staticmethod
    def validate_function_code(response: bytes, expected: int) -> None:
        """Reject a response whose function code does not echo the request.

        A real Modbus/TCP device signals a rejected request (bad address,
        bad quantity, ...) by echoing the request's function code with its
        high bit set (e.g. `0x03` -> `0x83`) followed by a one-byte
        exception code, not by an empty or garbled payload. Without this
        check, that exception response would fall through to
        `decode_int16_response`, which has no way to tell it apart from a
        short/garbled data payload and would raise a generic "too short" or
        "invalid length" error that hides the device's actual exception
        code. A function code that echoes neither the request nor its
        exception variant indicates a misrouted or corrupted frame and must
        be rejected the same way a transaction ID mismatch is (spec.md 11).
        """
        if len(response) < 8:
            raise ValueError("response too short for function code validation")
        function_code = response[7]
        if function_code == expected | 0x80:
            exception_code = response[8] if len(response) > 8 else None
            raise ModbusClientError(
                f"Modbus exception response for function 0x{expected:02x}: "
                f"exception code {exception_code}",
                exception_code=exception_code,
            )
        if function_code != expected:
            raise ValueError(
                f"function code mismatch: expected 0x{expected:02x}, "
                f"got 0x{function_code:02x}"
            )

    @classmethod
    def build_read_request(cls, address: int, count: int = 1, unit_id: int = 1) -> bytes:
        """Build a Modbus TCP request for function code 0x03."""
        if not 1 <= count <= 125:
            raise ValueError("count must be between 1 and 125")
        cls._transaction_counter += 1
        transaction_id = cls._transaction_counter & 0xFFFF
        return struct.pack(
            ">HHHBBHH",
            transaction_id,
            cls.PROTOCOL_ID,
            6,
            unit_id,
            0x03,
            address,
            count,
        )

    @classmethod
    def build_write_request(cls, address: int, value: int, unit_id: int = 1) -> bytes:
        """Build a Modbus TCP request for function code 0x10 (Write Multiple
        Registers), writing a single register.

        The manual's own worked wire example ("Beispiel 2 - Soll-Temperatur
        für Raum 2 setzen", `Fonterra Smart Control-de-DE.pdf`, page 95)
        writes this way - function 16, quantity 1, byte count 2 - not
        function 0x06 (Write Single Register), which this method used
        previously and which was never checked against that example (spec.md
        5b): the same class of mistake as the earlier PDU-address-offset
        bugs - internally self-consistent code and tests that were never
        checked against the vendor's own documented frame bytes.
        """
        cls._transaction_counter += 1
        transaction_id = cls._transaction_counter & 0xFFFF
        return struct.pack(
            ">HHHBBHHBH",
            transaction_id,
            cls.PROTOCOL_ID,
            9,
            unit_id,
            0x10,
            address,
            1,  # quantity of registers
            2,  # byte count
            value,
        )

    @staticmethod
    def decode_register_response(response: bytes) -> list[int]:
        """Decode a function code 0x03 (holding register) response.

        Values are decoded as signed 16-bit integers, matching
        `decode_int16_response`. This is required so the `-99` error
        sentinel (spec.md 10) can actually be detected on holding-register
        reads: decoding as unsigned would turn -99 into 65437 and the
        sentinel comparison would never match. Regular holding-register
        values (temperatures, power levels, modes) are always well below
        32768 and are unaffected by this interpretation.
        """
        return ViegaModbusClient.decode_int16_response(response)

    @staticmethod
    def decode_int16_response(response: bytes) -> list[int]:
        """Decode signed Int16 values from an input-register response."""
        if len(response) < 9:
            raise ModbusClientError("Modbus response is too short")
        byte_count = response[8]
        if len(response) != 9 + byte_count or byte_count % 2:
            raise ModbusClientError("Modbus response length is invalid")
        data = response[9:]
        return [
            int.from_bytes(data[index : index + 2], byteorder="big", signed=True)
            for index in range(0, len(data), 2)
        ]

    @staticmethod
    def _validate_register_count(values: list[int], expected_count: int) -> None:
        """Reject a response that decoded to a different number of registers
        than was requested.

        `decode_int16_response` only checks that its own `byte_count` field
        is internally consistent with the payload it carries (§10) - it has
        no way to know how many registers the *request* actually asked for.
        A device that echoes a different quantity (a truncated read after a
        partial TCP write, or a firmware quirk that answers a 2-register
        request with 1) would otherwise be decoded silently, handing the
        caller a value list that is the wrong length for the registers it
        asked for - e.g. shifting which list index holds which register.
        """
        if len(values) != expected_count:
            raise ModbusClientError(
                f"Modbus response returned {len(values)} register(s), "
                f"expected {expected_count}"
            )

    async def connect(self) -> None:
        """Open a TCP socket to the configured Modbus endpoint."""
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), timeout=self.timeout
            )
        except asyncio.TimeoutError:
            raise ModbusClientError(f"Connection timeout after {self.timeout}s")
        self._connected = True
        self._recv_buffer = b""

    async def _read_exact(self, size: int) -> bytes:
        """Accumulate exactly `size` bytes from the stream.

        Loops across multiple `StreamReader.read()` calls if needed - see
        `_read_frame` for why a single call cannot be trusted to return a
        whole frame. Any bytes read beyond what the current frame needs are
        kept in `self._recv_buffer` for the next call instead of discarded.
        """
        while len(self._recv_buffer) < size:
            chunk = await self._reader.read(size - len(self._recv_buffer))
            if not chunk:
                raise ModbusClientError(
                    "Modbus connection closed while reading a response"
                )
            self._recv_buffer += chunk
        data, self._recv_buffer = self._recv_buffer[:size], self._recv_buffer[size:]
        return data

    async def _read_frame(self) -> bytes:
        """Read one complete Modbus TCP response frame.

        TCP is a byte stream, not message-framed: `StreamReader.read(n)` can
        legitimately return fewer than `n` bytes even without EOF, if a
        response arrives split across more than one TCP segment. A single
        unconditional `read(256)` (the previous implementation) then handed
        a truncated frame straight to the decoders, which could only fail
        with a generic/misleading "too short" error instead of actually
        waiting for the rest. The MBAP header's length field (bytes 4-5)
        states exactly how many bytes follow the header, so read the header
        first and then keep reading until that many more bytes have
        arrived.
        """
        header = await self._read_exact(6)
        length = int.from_bytes(header[4:6], byteorder="big")
        if length <= 0:
            raise ModbusClientError("Modbus response length field is invalid")
        remainder = await self._read_exact(length)
        return header + remainder

    async def disconnect(self) -> None:
        """Close the current TCP connection.

        `StreamWriter.wait_closed()` has no built-in timeout: if the peer
        never completes the TCP close handshake (e.g. the device just went
        offline or is unreachable), it can block forever. Bounding it by the
        configured Modbus timeout ensures a stuck socket can never hang the
        config entry's removal (spec.md 6a/13: removal must succeed even
        when the device is offline or its connection is already broken).
        The state reset below must always run, even when the close itself
        fails or times out, so the client is never left thinking it is
        still connected.
        """
        if self._writer is not None:
            self._writer.close()
            try:
                await asyncio.wait_for(self._writer.wait_closed(), timeout=self.timeout)
            except (asyncio.TimeoutError, OSError):
                _LOGGER.debug(
                    "Modbus disconnect from %s:%s did not complete cleanly; "
                    "closing anyway",
                    self.host, self.port, exc_info=True,
                )
        self._reader = None
        self._writer = None
        self._connected = False
        self._recv_buffer = b""

    async def read_holding_registers(self, address: int, count: int = 1) -> list[int]:
        """Read one or more holding registers from the Modbus device."""
        if not self._connected or self._reader is None or self._writer is None:
            raise ModbusClientError("Modbus client is not connected")

        request = self.build_read_request(address, count, unit_id=self.UNIT_ID)
        expected_transaction_id = int.from_bytes(request[0:2], byteorder="big")
        start = time.monotonic()
        async with self._lock:
            try:
                self._log_frame("TX", request)
                self._writer.write(request)
                await self._writer.drain()

                try:
                    response = await asyncio.wait_for(self._read_frame(), timeout=self.timeout)
                except asyncio.TimeoutError:
                    raise ModbusClientError(f"Modbus read timeout after {self.timeout}s")
                self._log_frame("RX", response)
                self.validate_transaction_id(response, expected_transaction_id)
                self.validate_function_code(response, 0x03)
                values = self.decode_register_response(response)
                self._validate_register_count(values, count)
            except Exception as err:
                self._record_failure(err)
                raise
            self._record_success(
                time.monotonic() - start,
                sum(1 for value in values if value == self.ERROR_SENTINEL),
            )
            return values

    async def read_input_registers(self, address: int, count: int = 1) -> list[int]:
        """Read signed Int16 input registers using function code 0x04."""
        if not self._connected or self._reader is None or self._writer is None:
            raise ModbusClientError("Modbus client is not connected")

        request = self.build_read_request(address, count, unit_id=self.UNIT_ID)
        request = request[:7] + b"\x04" + request[8:]
        expected_transaction_id = int.from_bytes(request[0:2], byteorder="big")
        start = time.monotonic()
        async with self._lock:
            try:
                self._log_frame("TX", request)
                self._writer.write(request)
                await self._writer.drain()
                try:
                    response = await asyncio.wait_for(self._read_frame(), timeout=self.timeout)
                except asyncio.TimeoutError:
                    raise ModbusClientError(f"Modbus input read timeout after {self.timeout}s")
                self._log_frame("RX", response)
                self.validate_transaction_id(response, expected_transaction_id)
                self.validate_function_code(response, 0x04)
                values = self.decode_int16_response(response)
                self._validate_register_count(values, count)
            except Exception as err:
                self._record_failure(err)
                raise
            self._record_success(
                time.monotonic() - start,
                sum(1 for value in values if value == self.ERROR_SENTINEL),
            )
            return values

    async def write_register(self, address: int, value: int) -> None:
        """Write a single register via Modbus function code 0x10 (Write
        Multiple Registers, quantity 1) - see `build_write_request`."""
        if not self._connected or self._reader is None or self._writer is None:
            raise ModbusClientError("Modbus client is not connected")

        request = self.build_write_request(address, value, unit_id=self.UNIT_ID)
        expected_transaction_id = int.from_bytes(request[0:2], byteorder="big")
        start = time.monotonic()
        async with self._lock:
            try:
                self._log_frame("TX", request)
                self._writer.write(request)
                await self._writer.drain()

                try:
                    response = await asyncio.wait_for(self._read_frame(), timeout=self.timeout)
                except asyncio.TimeoutError:
                    raise ModbusClientError(f"Modbus write timeout after {self.timeout}s")
                self._log_frame("RX", response)
                self.validate_transaction_id(response, expected_transaction_id)
                self.validate_function_code(response, 0x10)
            except Exception as err:
                self._record_failure(err)
                raise
            self._record_success(time.monotonic() - start)

