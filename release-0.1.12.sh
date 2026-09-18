#!/usr/bin/env bash
# One-off helper for committing and tagging release 0.1.12.
# Review before running, then execute on your Fedora machine from the repo root:
#   bash release-0.1.12.sh
# This file is not meant to be committed itself - delete it once you're done,
# or leave it untracked (it is not added to git by this script).

set -euo pipefail

git add \
  README.md \
  custom_components/viega_fonterra_modbus/__init__.py \
  custom_components/viega_fonterra_modbus/climate.py \
  custom_components/viega_fonterra_modbus/const.py \
  custom_components/viega_fonterra_modbus/diagnostic.py \
  custom_components/viega_fonterra_modbus/manifest.json \
  custom_components/viega_fonterra_modbus/modbus_handler.py \
  custom_components/viega_fonterra_modbus/registers.py \
  custom_components/viega_fonterra_modbus/room_mapping.py \
  custom_components/viega_fonterra_modbus/sensor.py \
  info.md \
  spec.md \
  tests/test_entity_fixes.py \
  tests/test_init.py \
  tests/test_modbus_handler.py \
  tests/test_registers.py \
  tests/test_room_mapping.py \
  tests/test_sensor_entities.py \
  tests/test_specification.py

git commit -m "$(cat <<'EOF'
fix: correct off-by-one register addressing, add real room auto-discovery

- Fixed the PDU address formula in registers.py: it was off by exactly one
  register from the real device on every read/write (holding: manual - 40000,
  input: manual - 30000, not -40001/-30001), verified byte-for-byte against
  the Viega manual's own request/response wire examples. This was the root
  cause of wrong/unavailable data across every entity.
- Implemented real room/actor auto-discovery (room_mapping.py) from the
  device's actuator "Raum ID" and room-name registers instead of relying only
  on manually typed config - the previous discovery hook was dead code
  (ViegaModbusClient never implemented any of the probed methods).
- Fixed diagnostic entities to read each room's own error register instead of
  always showing the shared base-unit error code.
- Reverted the PLATFORMS regression: "diagnostic" is not a real Home
  Assistant platform domain.
- Removed placeholder sensor entities (temperature_flow/return/room, system
  pressure, pump state) that pointed at addresses with no real register.
- Completed the base-unit/room error code table from the manual's
  "Fehlercodes" table.
- Simplified Modbus debug logging to a single logger-based switch and added
  decision-level logging of the resolved room/register topology.
- Changed default host/port to 192.168.0.188:502.
- Release 0.1.12.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"

git tag -a v0.1.12 -m "Release 0.1.12"

echo "Commit and tag v0.1.12 created locally."
echo "To publish: git push origin main && git push origin v0.1.12"
