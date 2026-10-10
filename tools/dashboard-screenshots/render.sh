#!/usr/bin/env bash
# Re-render the README dashboard screenshots (docs/dashboard-*.png) from
# docs/dashboards/*.yaml with a real Home Assistant, this integration, and a
# simulated, anonymous Fonterra module. Needs podman, google-chrome, python3,
# and gh. Nothing here touches a real installation; everything runs on
# 127.0.0.1. The standard and tiles examples are shot on an English
# instance, the button-card example (German labels and entity IDs) on a
# German one.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
WORK="${WORK:-$(mktemp -d)}"
IMAGE="ghcr.io/home-assistant/home-assistant:stable"
echo "work dir: $WORK"

python3 -m venv "$WORK/venv"
"$WORK/venv/bin/pip" install -q aiohttp pillow
mkdir -p "$WORK/shots" "$WORK/www"
gh release download -R custom-cards/button-card --pattern button-card.js -D "$WORK/www" --clobber
podman pull -q "$IMAGE" >/dev/null

python3 "$HERE/fake_fonterra.py" 5020 & FAKE=$!
trap 'kill $FAKE 2>/dev/null; podman rm -f viega-render-en viega-render-de >/dev/null 2>&1 || true' EXIT

# render_instance <language> <port> <shots JSON>
render_instance() {
  local lang="$1" port="$2" shots="$3" config="$WORK/config-$1" name="viega-render-$1"
  mkdir -p "$config/.storage" "$config/custom_components" "$config/www" "$config/dashboards"
  sed -e "s/language: en/language: $lang/" -e "s/server_port: 18123/server_port: $port/" \
    "$HERE/config/configuration.yaml" > "$config/configuration.yaml"
  cp "$REPO"/docs/dashboards/*.yaml "$config/dashboards/"
  cp "$WORK/www/button-card.js" "$config/www/"
  cp -r "$REPO/custom_components/viega_fonterra_modbus" "$config/custom_components/"
  echo '{"version": 4, "minor_version": 1, "key": "onboarding", "data": {"done": ["user", "core_config", "analytics", "integration"]}}' \
    > "$config/.storage/onboarding"
  cat > "$config/.storage/core.config_entries" <<'JSON'
{"version": 1, "minor_version": 1, "key": "core.config_entries", "data": {"entries": [
  {"entry_id": "01DEMOVIEGAFONTERRA0000001", "version": 1, "domain": "viega_fonterra_modbus",
   "title": "Fonterra", "data": {"host": "127.0.0.1", "port": 5020, "device_name": "Fonterra",
   "polling_interval": 10, "modbus_timeout": 3}, "options": {},
   "pref_disable_new_entities": false, "pref_disable_polling": false, "source": "user",
   "unique_id": "127.0.0.1:5020", "disabled_by": null}]}}
JSON
  podman run --rm -v "$config:/config:Z" "$IMAGE" \
    python -m homeassistant --script auth -c /config add demo demo-render-only >/dev/null

  wait_up() { for _ in $(seq 1 60); do curl -sf -o /dev/null "http://127.0.0.1:$port/" && return; sleep 3; done; exit 1; }
  podman run -d --name "$name" --network host -e TZ=Europe/Berlin -v "$config:/config:Z" "$IMAGE" >/dev/null
  wait_up; sleep 40                                 # let entities and history appear
  podman stop "$name" >/dev/null
  python3 "$HERE/backfill_history.py" "$config/home-assistant_v2.db"
  podman start "$name" >/dev/null; wait_up; sleep 20
  HA_URL="http://127.0.0.1:$port" UI_LANGUAGE="$lang" \
    "$WORK/venv/bin/python" "$HERE/shoot.py" "$WORK/chrome-$lang" "$shots"
  podman rm -f "$name" >/dev/null
}

render_instance en 18123 "[
  [\"/viega-standard/heating-overview\", \"$WORK/shots/standard.png\", 1600, 1500],
  [\"/viega-tiles/fonterra\", \"$WORK/shots/tiles.png\", 1600, 960]]"
render_instance de 18124 "[
  [\"/viega-button-card/fonterra\", \"$WORK/shots/button_card.png\", 1600, 1000]]"

"$WORK/venv/bin/python" "$HERE/crop.py" \
  "$WORK/shots/standard.png" "$REPO/docs/dashboard-standard.png" \
  "$WORK/shots/tiles.png" "$REPO/docs/dashboard-tiles.png" \
  "$WORK/shots/button_card.png" "$REPO/docs/dashboard-button-card.png"
echo "updated docs/dashboard-*.png"
