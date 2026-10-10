"""Fill 24 h of plausible climate history into the render instance's recorder
database (night setback, morning heat-up, cycling actuators), so the history
graphs in the README screenshots are not empty. Run while Home Assistant is
stopped, after it has created the database and the entities once."""
import json
import os
import random
import sqlite3
import sys
import time

ROOMS = {  # entity: (target, room number, friendly name, actuators)
    "climate.fonterra_bad": (23.0, 1, "Fonterra Bad", ["1"]),
    "climate.fonterra_schlafzimmer": (19.0, 2, "Fonterra Schlafzimmer", ["2", "3"]),
    "climate.fonterra_arbeitszimmer": (20.5, 3, "Fonterra Arbeitszimmer", ["4"]),
    "climate.fonterra_kinderzimmer": (20.0, 4, "Fonterra Kinderzimmer", ["5"]),
}


def main(database: str) -> None:
    db = sqlite3.connect(database)
    random.seed(7)
    for entity_id, (target, room, name, actuators) in ROOMS.items():
        meta = db.execute("select metadata_id from states_meta where entity_id=?", (entity_id,)).fetchone()[0]
        first = db.execute("select min(last_updated_ts) from states where metadata_id=?", (meta,)).fetchone()[0]
        t, current, heating, next_switch = first - 24 * 3600, target - 1.2, False, first - 24 * 3600
        while t < first - 60:
            local = time.localtime(t)
            hour = local.tm_hour + local.tm_min / 60
            setpoint = target - 2.0 if (hour >= 22 or hour < 5) else target
            if t >= next_switch:  # actuators cycle every 15-30 minutes
                heating = (current < setpoint + 0.2 and not heating) if current > setpoint - 0.4 else current < setpoint + 0.2
                next_switch = t + random.choice([900, 1200, 1500, 1800])
            current += (0.06 if heating else -0.035) + random.uniform(-0.01, 0.01)
            current = max(setpoint - 2.5, min(setpoint + 0.8, current))
            attrs = {
                "current_temperature": round(current, 1), "temperature": setpoint,
                "hvac_action": "heating" if heating else "idle", "preset_mode": "manual",
                "room_id": room, "power_level": 4, "flow_temperature": 34.5,
                "return_temperature": 28.0, "actuator_position": int(heating),
                "actuator_positions": {a: int(heating) for a in actuators},
                "base_unit_error_code": 0, "last_active_hvac_mode": "heat", "friendly_name": name,
            }
            shared = json.dumps(attrs, separators=(",", ":"))
            attributes_id = db.execute(
                "insert into state_attributes(hash, shared_attrs) values(?, ?)",
                (hash(shared) & 0xFFFFFFFF, shared)).lastrowid
            db.execute(
                "insert into states(state, last_changed_ts, last_reported_ts, last_updated_ts,"
                " attributes_id, origin_idx, context_id_bin, metadata_id)"
                " values('heat', ?, ?, ?, ?, 0, ?, ?)",
                (t, t, t, attributes_id, os.urandom(16), meta))
            t += 300
    db.commit()


if __name__ == "__main__":
    main(sys.argv[1])
