"""MQTT → Postgres bridge for alarms and performance metrics.

Subscribes to:
  - <line>/+/Alarms                       station-side AlarmsMessage
  - <line>/Controller/Alarms              controller-side ControllerAlarmMessage
  - <line>/+/State/+                      per-actor StateMessage
  - <line>/+/JobResult/+                  per-actor JobResultMessage
  - <line>/Controller/OrderCompleted      per-order OrderCompletedMessage

Writes to the unified `alarms` table plus three metrics tables
(state_transitions, job_results, order_completions) consumed by the
Next.js dashboard.

Run as a long-lived process alongside the broker and the line controller:

    python Implementation2.0/PSQL_Consumer/psql_bridge.py
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import paho.mqtt.client as mqtt
import psycopg2

# Allow importing MessageStructure from the shared classes module.
# psql_bridge.py lives at Implementation2.0/PSQL_Consumer/, so its
# parent's parent IS Implementation2.0 — append that directly.
sys.path.append(str(Path(__file__).resolve().parent.parent))

from ClassesAndBuilderMethods.InformationModels import MessageStructure as MS  # noqa: E402


# ====== CONFIG ======
MQTT_BROKER = os.environ.get("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
LINE_ID = os.environ.get("LINE_ID", "ProductionLine1")
BASE_TOPIC = f"AAUSmartLab/{LINE_ID}"

# Station alarms: AAUSmartLab/<LINE_ID>/<resource_id>/Alarms
# Controller alarms: AAUSmartLab/<LINE_ID>/Controller/Alarms
# Both match the same wildcard; we route inside on_message.
ALARM_TOPIC_FILTER = f"{BASE_TOPIC}/+/Alarms"
CONTROLLER_ALARM_TOPIC = f"{BASE_TOPIC}/Controller/Alarms"

# Per-actor metrics streams (topic shape: <line>/<resource>/<channel>/<actor>).
STATE_TOPIC_FILTER = f"{BASE_TOPIC}/+/State/+"
JOBRESULT_TOPIC_FILTER = f"{BASE_TOPIC}/+/JobResult/+"

# Order-level completion events from the line controller.
ORDER_COMPLETED_TOPIC = f"{BASE_TOPIC}/Controller/OrderCompleted"

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://made:made@localhost:5432/made_app"
)

SCHEMA_FILE = Path(__file__).resolve().parent / "schema.sql"


# ====== DATABASE ======
def connect_db() -> psycopg2.extensions.connection:
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    return conn


def ensure_schema(conn) -> None:
    with conn.cursor() as cur, SCHEMA_FILE.open() as f:
        cur.execute(f.read())
    conn.commit()
    print(f"[DB] schema ensured ({SCHEMA_FILE.name})")


def to_utc(dt: datetime) -> datetime:
    """Coerce any datetime to aware UTC.

    Stations publish `datetime.now()` (naive local). Pydantic preserves it
    naive on the way through MQTT. Postgres `TIMESTAMPTZ` interprets a
    naive insert under the session tz (usually UTC in Docker), which
    silently shifts the stored timestamp away from the wall clock. We
    treat naive inputs as the local clock of the machine running the
    bridge — same machine as the stations in dev — and convert.
    """
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc)
    return dt.astimezone(timezone.utc)


def line_id_from_topic(topic: str) -> str | None:
    """Extract the line segment from an MQTT topic.

    Convention: AAUSmartLab/<line_id>/<resource>/...
    """
    parts = topic.split("/")
    return parts[1] if len(parts) >= 2 else None


def insert_alarm(
    conn,
    *,
    source: str,
    resource_id: str | None,
    category: str,
    severity: str,
    order_id: str | None,
    message: str | None,
    triggered_at: datetime,
) -> None:
    sql = """
        INSERT INTO alarms
            (source, resource_id, category, severity, order_id, message, triggered_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    with conn.cursor() as cur:
        cur.execute(
            sql,
            (source, resource_id, category, severity, order_id, message, triggered_at),
        )
    conn.commit()
    print(
        f"[DB] inserted {source} alarm "
        f"resource={resource_id} category={category} severity={severity}"
    )


# ====== MESSAGE HANDLERS ======
def handle_station_alarm(conn, payload: dict) -> None:
    msg = MS.AlarmsMessage(**payload)
    # AlarmsMessage carries a list of alarm_ids; one DB row per id so the
    # UI can acknowledge them individually.
    for alarm_id in msg.alarm_ids:
        insert_alarm(
            conn,
            source="station",
            resource_id=msg.resource_id,
            category=alarm_id,
            severity=MS.AlarmSeverity.WARNING.value,
            order_id=None,
            message=f"actor={msg.actor_id}",
            triggered_at=msg.timestamp,
        )


def clear_alarms(
    conn,
    *,
    category: str,
    resource_id: str | None,
    order_id: str | None,
    cleared_at: datetime,
) -> None:
    """Mark all matching *active* alarms (cleared_at IS NULL) as cleared.

    NULL match semantics: a NULL filter value matches any row value, so
    callers that don't care about, e.g., order_id can omit it.
    """
    sql = """
        UPDATE alarms
        SET cleared_at = %s
        WHERE category = %s
          AND cleared_at IS NULL
          AND (%s::text IS NULL OR resource_id = %s)
          AND (%s::text IS NULL OR order_id    = %s)
    """
    with conn.cursor() as cur:
        cur.execute(
            sql,
            (cleared_at, category, resource_id, resource_id, order_id, order_id),
        )
        affected = cur.rowcount
    conn.commit()
    print(
        f"[DB] cleared {affected} alarm(s) "
        f"category={category} resource={resource_id} order={order_id}"
    )


def handle_controller_alarm(conn, payload: dict) -> None:
    msg = MS.ControllerAlarmMessage(**payload)
    if msg.cleared:
        clear_alarms(
            conn,
            category=msg.category.value,
            resource_id=msg.resource_id,
            order_id=msg.order_id,
            cleared_at=msg.timestamp,
        )
        return
    insert_alarm(
        conn,
        source="controller",
        resource_id=msg.resource_id,
        category=msg.category.value,
        severity=msg.severity.value,
        order_id=msg.order_id,
        message=msg.message,
        triggered_at=msg.timestamp,
    )


# ====== METRICS HANDLERS ======
def handle_state(conn, topic: str, payload: dict) -> None:
    """Topic shape: AAUSmartLab/<line>/<resource>/State/<actor>."""
    msg = MS.StateMessage(**payload)
    line_id = line_id_from_topic(topic)
    actor_name = topic.rsplit("/", 1)[-1]
    sql = """
        INSERT INTO state_transitions
            (line_id, resource_id, actor_name, state, ts)
        VALUES (%s, %s, %s, %s, %s)
    """
    with conn.cursor() as cur:
        cur.execute(
            sql,
            (line_id, msg.resource_id, actor_name, msg.state.value,
             to_utc(msg.timestamp)),
        )
    conn.commit()
    print(
        f"[DB] state: {line_id}/{msg.resource_id}/{actor_name} -> {msg.state.value}"
    )


def handle_job_result(conn, topic: str, payload: dict) -> None:
    """Topic shape: AAUSmartLab/<line>/<resource>/JobResult/<actor>."""
    msg = MS.JobResultMessage(**payload)
    line_id = line_id_from_topic(topic)
    actor_name = topic.rsplit("/", 1)[-1]
    skill = None
    sql = """
        INSERT INTO job_results
            (line_id, order_id, job_id, resource_id, actor_name, skill,
             ideal_cycle_time_ms, actual_cycle_time_ms,
             result, quality, completed_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    with conn.cursor() as cur:
        cur.execute(
            sql,
            (
                line_id,
                msg.order_id,
                msg.job_id,
                msg.resource_id,
                actor_name,
                skill,
                msg.ideal_cycle_time_ms,
                msg.actual_cycle_time_ms,
                msg.result.value if msg.result else None,
                msg.quality.value if msg.quality else None,
                to_utc(msg.timestamp),
            ),
        )
    conn.commit()
    print(
        f"[DB] job_result: {line_id}/{msg.resource_id}/{actor_name} "
        f"job={msg.job_id} result={msg.result} quality={msg.quality}"
    )


def handle_order_completed(conn, topic: str, payload: dict) -> None:
    msg = MS.OrderCompletedMessage(**payload)
    line_id = line_id_from_topic(topic)
    sql = """
        INSERT INTO order_completions
            (line_id, order_id, product_ref, started_at, completed_at,
             status, attempt_count)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    with conn.cursor() as cur:
        cur.execute(
            sql,
            (
                line_id,
                msg.order_id,
                msg.product_ref,
                to_utc(msg.started_at),
                to_utc(msg.completed_at),
                msg.status.value,
                msg.attempt_count,
            ),
        )
    conn.commit()
    print(
        f"[DB] order: {line_id}/{msg.order_id} status={msg.status.value} "
        f"attempts={msg.attempt_count}"
    )


# ====== MQTT CALLBACKS ======
def on_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code != 0:
        print(f"[MQTT] connect failed: rc={reason_code}")
        return
    print(f"[MQTT] connected to {MQTT_BROKER}:{MQTT_PORT}")
    for f in (
        ALARM_TOPIC_FILTER,
        STATE_TOPIC_FILTER,
        JOBRESULT_TOPIC_FILTER,
        ORDER_COMPLETED_TOPIC,
    ):
        client.subscribe(f)
        print(f"[MQTT] subscribed to {f}")


def _classify_topic(topic: str) -> str:
    """Return one of: 'controller_alarm', 'station_alarm', 'state',
    'job_result', 'order_completed', or 'unknown'."""
    if topic == ORDER_COMPLETED_TOPIC:
        return "order_completed"
    if topic == CONTROLLER_ALARM_TOPIC:
        return "controller_alarm"
    parts = topic.split("/")
    if parts[-1] == "Alarms":
        return "station_alarm"
    # Per-actor channels have shape: ...<resource>/<channel>/<actor>
    if len(parts) >= 2:
        channel = parts[-2]
        if channel == "State":
            return "state"
        if channel == "JobResult":
            return "job_result"
    return "unknown"


def on_message(client, userdata, msg):
    conn: psycopg2.extensions.connection = userdata["conn"]
    try:
        payload = json.loads(msg.payload.decode())
        kind = _classify_topic(msg.topic)
        if kind == "controller_alarm":
            handle_controller_alarm(conn, payload)
        elif kind == "station_alarm":
            handle_station_alarm(conn, payload)
        elif kind == "state":
            handle_state(conn, msg.topic, payload)
        elif kind == "job_result":
            handle_job_result(conn, msg.topic, payload)
        elif kind == "order_completed":
            handle_order_completed(conn, msg.topic, payload)
        else:
            print(f"[WARN] unhandled topic shape: {msg.topic}")
    except Exception as exc:
        # Don't crash the loop on a malformed payload — log and continue.
        print(f"[ERROR] {type(exc).__name__} on {msg.topic}: {exc}")
        try:
            conn.rollback()
        except Exception:
            pass


# ====== MAIN ======
def main() -> None:
    conn = connect_db()
    ensure_schema(conn)

    client = mqtt.Client(
        client_id="MES_AlarmBridge",
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        userdata={"conn": conn},
    )
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)

    print("[bridge] running — Ctrl+C to stop")
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("\n[bridge] stopping")
    finally:
        client.disconnect()
        conn.close()


if __name__ == "__main__":
    main()
