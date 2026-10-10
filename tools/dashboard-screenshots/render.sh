#!/usr/bin/env bash
# Re-render the README dashboard screenshots (docs/dashboard-*.png) from
# docs/dashboards/*.yaml with a real Home Assistant, this integration, and a
# simulated, anonymous Fonterra module. Needs podman, google-chrome, python3.
# Nothing here touches a real installation; everything runs on 127.0.0.1.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
WORK="${WORK:-$(mktemp -d)}"
IMAGE="ghcr.io/home-assistant/home-assistant:stable"
CONFIG="$WORK/config"
echo "work dir: $WORK"

python3 -m venv "$WORK/venv"
"$WORK/venv/bin/pip" install -q aiohttp pillow

mkdir -p "$CONFIG/.storage" "$CONFIG/custom_components" "$CONFIG/www" "$CONFIG/dashboards" "$WORK/shots"
cp "$HERE/config/configuration.yaml" "$CONFIG/"
cp "$REPO"/docs/dashboards/*.yaml "$CONFIG/dashboards/"
cp -r "$REPO/custom_components/viega_fonterra_modbus" "$CONFIG/custom_components/"
gh release download -R custom-cards/button-card --pattern button-card.js -D "$CONFIG/www" --clobber
echo '{"version": 4, "minor_version": 1, "key": "onboarding", "data": {"done": ["user", "core_config", "analytics", "integration"]}}' \
  > "$CONFIG/.storage/onboarding"
cat > "$CONFIG/.storage/core.config_entries" <<'JSON'
{"version": 1, "minor_version": 1, "key": "core.config_entries", "data": {"entries": [
  {"entry_id": "01DEMOVIEGAFONTERRA0000001", "version": 1, "domain": "viega_fonterra_modbus",
   "title": "Fonterra", "data": {"host": "127.0.0.1", "port": 5020, "device_name": "Fonterra",
   "polling_interval": 10, "modbus_timeout": 3}, "options": {},
   "pref_disable_new_entities": false, "pref_disable_polling": false, "source": "user",
   "unique_id": "127.0.0.1:5020", "disabled_by": null}]}}
JSON

podman pull -q "$IMAGE" >/dev/null
podman run --rm -v "$CONFIG:/config:Z" "$IMAGE" \
  python -m homeassistant --script auth -c /config add demo demo-render-only >/dev/null

python3 "$HERE/fake_fonterra.py" 5020 & FAKE=$!
trap 'kill $FAKE 2>/dev/null; podman rm -f viega-render >/dev/null 2>&1 || true' EXIT

wait_up() { for _ in $(seq 1 60); do curl -sf -o /dev/null http://127.0.0.1:18123/ && return; sleep 3; done; exit 1; }
podman run -d --name viega-render --network host -e TZ=Europe/Berlin -v "$CONFIG:/config:Z" "$IMAGE" >/dev/null
wait_up; sleep 40                                   # let entities and history appear
podman stop viega-render >/dev/null
python3 "$HERE/backfill_history.py" "$CONFIG/home-assistant_v2.db"
podman start viega-render >/dev/null; wait_up; sleep 20

"$WORK/venv/bin/python" "$HERE/shoot.py" "$WORK/chrome" "[
  [\"/viega-standard/heating-overview\", \"$WORK/shots/standard.png\", 1600, 1500],
  [\"/viega-tiles/fonterra\", \"$WORK/shots/tiles.png\", 1600, 960],
  [\"/viega-button-card/fonterra\", \"$WORK/shots/button_card.png\", 1600, 870]]"
"$WORK/venv/bin/python" "$HERE/crop.py" \
  "$WORK/shots/standard.png" "$REPO/docs/dashboard-standard.png" \
  "$WORK/shots/tiles.png" "$REPO/docs/dashboard-tiles.png" \
  "$WORK/shots/button_card.png" "$REPO/docs/dashboard-button-card.png"
echo "updated docs/dashboard-*.png"
