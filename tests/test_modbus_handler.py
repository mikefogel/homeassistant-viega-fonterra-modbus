"""Tests for the Viega Fonterra Modbus client."""

import logging
from types import SimpleNamespace

from custom_components.viega_fonterra_modbus.const import DOMAIN
from custom_components.viega_fonterra_modbus.modbus_handler import ViegaModbusClient
from custom_components.viega_fonterra_modbus.sensor import ViegaRegisterSensor


def test_client_initialization():
    """The client must carry the configured host and port."""
    client = ViegaModbusClient("192.168.1.50", 502)

    assert client.host == "192.168.1.50"
    assert client.port == 502
    assert hasattr(client, "read_holding_registers")


def test_read_request_is_built_with_modbus_tcp_frame():
    """The read request must be encoded as a valid Modbus/TCP frame."""
    request = ViegaModbusClient.build_read_request(1000, count=2)

    assert len(request) == 12
    assert request[0:2] == b"\x00\x01"
    assert request[2:4] == b"\x00\x00"
    assert request[4:6] == b"\x00\x06"
    assert request[6] == 0x01
    assert request[7] == 0x03


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
    client = ViegaModbusClient("192.168.8.20", 1502, debug=True)
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


def test_frame_debug_logging_is_disabled_by_default(caplog):
    """No frame log should be emitted unless debug logging is enabled."""
    client = ViegaModbusClient("192.168.8.20", 1502)

    with caplog.at_level(
        logging.DEBUG,
        logger="custom_components.viega_fonterra_modbus.modbus",
    ):
        client._log_frame("TX", b"\x00\x01")

    assert not caplog.records
