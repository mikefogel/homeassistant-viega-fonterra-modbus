"""Tests for the Viega Fonterra Modbus client."""

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
