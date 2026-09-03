"""Modbus TCP client for the Viega Fonterra Smart Control integration."""

from __future__ import annotations

import asyncio
import logging
import struct
from typing import Any


_LOGGER = logging.getLogger("custom_components.viega_fonterra_modbus.modbus")


class ModbusClientError(RuntimeError):
    """Raised when a Modbus request cannot be processed."""


class ViegaModbusClient:
    """Minimal Modbus TCP helper for the Fonterra system."""

    UNIT_ID = 1
    PROTOCOL_ID = 0
    ERROR_SENTINEL = -99
    _transaction_counter = 0

    def __init__(
        self, host: str, port: int = 1502, timeout: float = 5, debug: bool = False
    ) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.debug = debug
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._connected = False
        self._lock = asyncio.Lock()

    def set_debug(self, enabled: bool) -> None:
        """Enable or disable frame-level debug logging."""
        self.debug = enabled

    def _log_frame(self, direction: str, frame: bytes) -> None:
        """Log a Modbus frame with decoded header fields at DEBUG level."""
        if not self.debug:
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
        """Build a Modbus TCP request for function code 0x06."""
        cls._transaction_counter += 1
        transaction_id = cls._transaction_counter & 0xFFFF
        return struct.pack(
            ">HHHBBHH",
            transaction_id,
            cls.PROTOCOL_ID,
            6,
            unit_id,
            0x06,
            address,
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

    async def connect(self) -> None:
        """Open a TCP socket to the configured Modbus endpoint."""
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), timeout=self.timeout
            )
        except asyncio.TimeoutError:
            raise ModbusClientError(f"Connection timeout after {self.timeout}s")
        self._connected = True

    async def disconnect(self) -> None:
        """Close the current TCP connection."""
        if self._writer is not None:
            self._writer.close()
            await self._writer.wait_closed()
        self._reader = None
        self._writer = None
        self._connected = False

    async def read_holding_registers(self, address: int, count: int = 1) -> list[int]:
        """Read one or more holding registers from the Modbus device."""
        if not self._connected or self._reader is None or self._writer is None:
            raise ModbusClientError("Modbus client is not connected")

        request = self.build_read_request(address, count, unit_id=self.UNIT_ID)
        expected_transaction_id = int.from_bytes(request[0:2], byteorder="big")
        async with self._lock:
            self._log_frame("TX", request)
            self._writer.write(request)
            await self._writer.drain()

            try:
                response = await asyncio.wait_for(self._reader.read(256), timeout=self.timeout)
            except asyncio.TimeoutError:
                raise ModbusClientError(f"Modbus read timeout after {self.timeout}s")
            self._log_frame("RX", response)
            self.validate_transaction_id(response, expected_transaction_id)
            return self.decode_register_response(response)

    async def read_input_registers(self, address: int, count: int = 1) -> list[int]:
        """Read signed Int16 input registers using function code 0x04."""
        if not self._connected or self._reader is None or self._writer is None:
            raise ModbusClientError("Modbus client is not connected")

        request = self.build_read_request(address, count, unit_id=self.UNIT_ID)
        request = request[:7] + b"\x04" + request[8:]
        expected_transaction_id = int.from_bytes(request[0:2], byteorder="big")
        async with self._lock:
            self._log_frame("TX", request)
            self._writer.write(request)
            await self._writer.drain()
            try:
                response = await asyncio.wait_for(
                    self._reader.read(256), timeout=self.timeout
                )
            except asyncio.TimeoutError:
                raise ModbusClientError(f"Modbus input read timeout after {self.timeout}s")
            self._log_frame("RX", response)
            self.validate_transaction_id(response, expected_transaction_id)
            return self.decode_int16_response(response)

    async def write_register(self, address: int, value: int) -> None:
        """Write a single register via Modbus function code 0x06."""
        if not self._connected or self._reader is None or self._writer is None:
            raise ModbusClientError("Modbus client is not connected")

        request = self.build_write_request(address, value, unit_id=self.UNIT_ID)
        expected_transaction_id = int.from_bytes(request[0:2], byteorder="big")
        async with self._lock:
            self._log_frame("TX", request)
            self._writer.write(request)
            await self._writer.drain()

            try:
                response = await asyncio.wait_for(
                    self._reader.read(256), timeout=self.timeout
                )
            except asyncio.TimeoutError:
                raise ModbusClientError(f"Modbus write timeout after {self.timeout}s")
            self._log_frame("RX", response)
            self.validate_transaction_id(response, expected_transaction_id)

