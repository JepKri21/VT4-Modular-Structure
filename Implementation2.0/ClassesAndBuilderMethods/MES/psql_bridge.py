"""MQTT → Postgres bridge for alarms and performance metrics.

At startup the bridge walks the AAS server (`AAS_BASE` env var, default
http://localhost:8081) for every shell under `RESOURCE_IRI_PREFIX`. For
each shell it reads the Communication submodel and pulls:

  - `MQTT.ProductionLinePrefix`         e.g. "AAUSmartLab/ProductionLine1"
  - `MQTT.Suffixes.{StateSuffix,        e.g. "PackMLState", "JobResult",
                    JobResultSuffix,         "Alarms", "InventoryLevel"
                    AlarmSuffix,
                    InventoryLevelSuffix}`

Concrete subscription filters are built from those, e.g.
`AAUSmartLab/ProductionLine1/Drilling_<uuid>/PackMLState/+`. There are no
hardcoded suffix strings — change Communication.yaml and re-run, the
bridge picks it up.

Controller-side topics are still hardcoded (they don't live on any
resource's Communication submodel):

  - <line>/Controller/Alarms              controller-side ControllerAlarmMessage
  - <line>/Controller/OrderCompleted      per-order OrderCompletedMessage

Writes to the unified `alarms` table plus three metrics tables
(state_transitions, job_results, order_completions) consumed by the
Next.js dashboard.

Run as a long-lived process alongside the broker and the line controller:

    python Implementation2.0/ClassesAndBuilderMethods/MES/psql_bridge.py
"""

import base64
import json
import os
import re
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

import paho.mqtt.client as mqtt
import psycopg2
import requests

# Allow importing MessageStructure from the shared classes module.
# psql_bridge.py lives at Implementation2.0/ClassesAndBuilderMethods/MES/,
# so parent.parent.parent IS Implementation2.0.
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from ClassesAndBuilderMethods.InformationModels import MessageStructure as MS  # noqa: E402


# ====== CONFIG ======
MQTT_BROKER = os.environ.get("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
LINE_ID = os.environ.get("LINE_ID", "ProductionLine1")
BASE_TOPIC = f"AAUSmartLab/{LINE_ID}"

AAS_BASE = os.environ.get("AAS_BASE", "http://localhost:8081")
RESOURCE_IRI_PREFIX = os.environ.get(
    "RESOURCE_IRI_PREFIX", "https://aausmartlab.org/Shells/Resources/"
)

# Controller-side topics: hardcoded because they don't live on any
# resource's Communication submodel.
CONTROLLER_ALARM_TOPIC = f"{BASE_TOPIC}/Controller/Alarms"
ORDER_COMPLETED_TOPIC = f"{BASE_TOPIC}/Controller/OrderCompleted"

# Suffix idShort -> classification key. Used when walking each resource's
# Communication.MQTT.Suffixes collection. If a suffix isn't in this map the
# bridge skips it (e.g. CommandSuffix is controller→station, not consumed
# here). Keys here MUST match the idShort fields defined in the
# communication submodel template.
SUFFIX_KIND_MAP: dict[str, str] = {
    "StateSuffix": "state",
    "JobResultSuffix": "job_result",
    "AlarmSuffix": "station_alarm",
    "InventoryLevelSuffix": "inventory",
}

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://made:made@localhost:5432/made_app"
)

# How often to re-walk the AAS for newly-uploaded or removed resources.
# Each refresh is one HTTP list call + one HTTP submodel call per resource
# — cheap enough to do every 30s at typical lab scale. Drop to 0 to
# disable and require a bridge restart for changes (not recommended).
DISCOVERY_INTERVAL_S = int(os.environ.get("DISCOVERY_INTERVAL_S", "30"))

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


# Matches the standard `Name<sep><UUID>` suffix used to distinguish a
# specific instance from its type IRI. Both `-` (Fuse16ASB-<uuid>) and
# `_` (AAUMobilePhoneV1_<uuid>) are valid separators in the project.
_UUID_TAIL = re.compile(
    r"[-_][0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def classify_material_kind(type_iri: str) -> str:
    """Map an IRI shape to its MRP kind:
      /Shells/Component/...  -> RAW           (we buy / source these)
      /Shells/Assembly/...   -> INTERMEDIATE  (we produce on the line)
      /Shells/Product/...    -> FINISHED      (output of MPS, not material)
    """
    if "/Shells/Product/" in type_iri:
        return "FINISHED"
    if "/Shells/Assembly/" in type_iri:
        return "INTERMEDIATE"
    return "RAW"


def component_type_iri(component_id: str) -> str:
    """Strip the `-<UUID>` instance tail from a component IRI to get the
    type-level IRI used as the MRP material key.

    Example:
      https://.../Fuse/Fuse16ASB-b40d1f62-735d-4c4e-a91a-18ae08043cff
      -> https://.../Fuse/Fuse16ASB
    """
    if not component_id:
        return component_id
    return _UUID_TAIL.sub("", component_id)


def _name_and_category_from_iri(type_iri: str) -> tuple[str, str | None]:
    """Pull a human name and category out of the AAS shell IRI shape
    `https://.../<Category>/<Name>` so seeded materials are readable.
    """
    parts = [p for p in type_iri.split("/") if p]
    if len(parts) >= 2:
        return parts[-1], parts[-2]
    return type_iri, None


def insert_alarm(
    conn,
    *,
    source: str,
    resource_id: str | None,
    actor_name: str | None,
    category: str,
    severity: str,
    order_id: str | None,
    message: str | None,
    triggered_at: datetime,
) -> None:
    sql = """
        INSERT INTO alarms
            (source, resource_id, actor_name, category, severity, order_id,
             message, triggered_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    with conn.cursor() as cur:
        cur.execute(
            sql,
            (
                source, resource_id, actor_name, category, severity,
                order_id, message, triggered_at,
            ),
        )
    conn.commit()
    print(
        f"[DB] inserted {source} alarm "
        f"resource={resource_id} actor={actor_name} category={category}"
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
            actor_name=msg.actor_id,
            category=alarm_id,
            severity=MS.AlarmSeverity.WARNING.value,
            order_id=None,
            message=None,
            triggered_at=msg.timestamp,
        )


def clear_alarms(
    conn,
    *,
    category: str,
    resource_id: str | None,
    actor_name: str | None,
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
          AND (%s::text IS NULL OR actor_name  = %s)
          AND (%s::text IS NULL OR order_id    = %s)
    """
    with conn.cursor() as cur:
        cur.execute(
            sql,
            (
                cleared_at, category,
                resource_id, resource_id,
                actor_name, actor_name,
                order_id, order_id,
            ),
        )
        affected = cur.rowcount
    conn.commit()
    print(
        f"[DB] cleared {affected} alarm(s) category={category} "
        f"resource={resource_id} actor={actor_name} order={order_id}"
    )


def handle_controller_alarm(conn, payload: dict) -> None:
    msg = MS.ControllerAlarmMessage(**payload)
    if msg.cleared:
        clear_alarms(
            conn,
            category=msg.category.value,
            resource_id=msg.resource_id,
            actor_name=msg.actor_name,
            order_id=msg.order_id,
            cleared_at=msg.timestamp,
        )
        return
    insert_alarm(
        conn,
        source="controller",
        resource_id=msg.resource_id,
        actor_name=msg.actor_name,
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


def handle_inventory(conn, topic: str, payload: dict) -> None:
    """Aggregate a station's InventoryLevel snapshot into mrp_inventory.

    The bridge wipes the rows for this resource_id and re-inserts the
    fresh per-type counts — the message is authoritative.

    Side effect: auto-seeds mrp_materials with sensible defaults for any
    type we haven't seen before, so the materials catalog grows on its
    own as the line discovers new components.

    Topic shape: AAUSmartLab/<line>/<resource_id>/InventoryLevel
    Expected payload shape (see InventoryLevelMessage / InventoryData):
      {
        "resource_id": "...",
        "inventory": {
          "Inventory_1": {
            "storage": {
              "position1": {"component_id": null},
              "position3": {"component_id": "https://.../Fuse16ASB-<UUID>"}
            },
            ...
          },
          ...
        },
        "timestamp": "..."
      }
    """
    resource_id = payload.get("resource_id")
    if not resource_id:
        print(f"[WARN] InventoryLevel on {topic} missing resource_id")
        return

    # Count by type IRI across all of this station's inventories.
    counts: dict[str, int] = {}
    for inv in (payload.get("inventory") or {}).values():
        storage = (inv or {}).get("storage") or {}
        for slot in storage.values():
            component_id = (slot or {}).get("component_id")
            if not component_id:
                continue
            type_iri = component_type_iri(component_id)
            counts[type_iri] = counts.get(type_iri, 0) + 1

    with conn.cursor() as cur:
        # Wipe + insert is the simplest authoritative-snapshot pattern.
        cur.execute(
            "DELETE FROM mrp_inventory WHERE resource_id = %s",
            (resource_id,),
        )
        if counts:
            cur.executemany(
                """
                INSERT INTO mrp_inventory
                    (resource_id, component_type_iri, on_hand, updated_at)
                VALUES (%s, %s, %s, NOW())
                """,
                [(resource_id, type_iri, n) for type_iri, n in counts.items()],
            )
            # Seed material rows for any new type — no-op if already there.
            cur.executemany(
                """
                INSERT INTO mrp_materials
                    (component_type_iri, name, category, kind)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (component_type_iri) DO NOTHING
                """,
                [
                    (
                        type_iri,
                        *_name_and_category_from_iri(type_iri),
                        classify_material_kind(type_iri),
                    )
                    for type_iri in counts.keys()
                ],
            )
    conn.commit()
    print(
        f"[DB] inventory: {resource_id} -> {len(counts)} type(s), "
        f"{sum(counts.values())} unit(s)"
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
# ====== AAS-DRIVEN RESOURCE DISCOVERY ======

# Populated by discover_resources() at startup. Maps each subscription
# filter (which may include `+` actor wildcards) to the bridge's internal
# kind. _classify_topic walks this dict on every incoming message so we
# never hardcode suffix strings like "PackMLState" or "JobResult".
_topic_routes: dict[str, str] = {}


def _b64url(value: str) -> str:
    """BaSyx encodes shell/submodel IDs with URL-safe base64, no padding."""
    return base64.urlsafe_b64encode(value.encode("utf-8")).decode().rstrip("=")


def _walk_for_idshort(value, idshort):
    """Depth-first scan for the first SubmodelElement whose idShort matches."""
    if isinstance(value, dict):
        if value.get("idShort") == idshort:
            return value
        for child in value.values():
            found = _walk_for_idshort(child, idshort)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _walk_for_idshort(child, idshort)
            if found is not None:
                return found
    return None


def _read_property_value(elements, idshort: str) -> str | None:
    el = _walk_for_idshort(elements, idshort)
    if not el:
        return None
    val = el.get("value")
    return val if isinstance(val, str) and val else None


def _fetch_resource_shells() -> list[str]:
    """Every shell IRI on the AAS server starting with RESOURCE_IRI_PREFIX.

    Follows the paging cursor — BaSyx caps page size at 1000, so a single
    request would silently drop shells past the first page.
    """
    shells: list = []
    cursor: str | None = None
    try:
        while True:
            url = f"{AAS_BASE}/shells?limit=1000"
            if cursor:
                url += f"&cursor={requests.utils.quote(cursor, safe='')}"
            resp = requests.get(url, timeout=5)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list):
                shells.extend(data)
                break
            shells.extend(data.get("result", []))
            cursor = (data.get("paging_metadata") or {}).get("cursor")
            if not cursor:
                break
    except Exception as exc:
        print(f"[discover] failed to list shells from {AAS_BASE}: {exc}")
        return []
    return [
        s["id"] for s in shells
        if isinstance(s, dict)
        and isinstance(s.get("id"), str)
        and s["id"].startswith(RESOURCE_IRI_PREFIX)
    ]


def discover_resources() -> dict[str, str]:
    """Read each Resource's Communication submodel and build the
    topic-filter -> kind map. Populates and returns `_topic_routes`.
    """
    _topic_routes.clear()
    for iri in _fetch_resource_shells():
        sm_iri = f"{iri}/Communication"
        try:
            resp = requests.get(
                f"{AAS_BASE}/submodels/{_b64url(sm_iri)}", timeout=5
            )
            if resp.status_code != 200:
                print(
                    f"[discover] {iri}: no Communication submodel "
                    f"(HTTP {resp.status_code})"
                )
                continue
            sm = resp.json()
        except Exception as exc:
            print(f"[discover] {iri}: failed to fetch Communication: {exc}")
            continue

        elements = sm.get("submodelElements", []) or []
        prefix = _read_property_value(elements, "ProductionLinePrefix")
        suffixes_el = _walk_for_idshort(elements, "Suffixes")
        if not prefix or not suffixes_el:
            print(
                f"[discover] {iri}: missing ProductionLinePrefix or "
                f"Suffixes — skipping"
            )
            continue

        resource_id_short = iri.rstrip("/").rsplit("/", 1)[-1]
        for child in suffixes_el.get("value", []) or []:
            suffix_idshort = child.get("idShort")
            suffix_value = child.get("value")
            kind = SUFFIX_KIND_MAP.get(suffix_idshort)
            if not kind or not isinstance(suffix_value, str) or not suffix_value:
                continue
            # State + JobResult are per-actor, so the filter ends with /+.
            # Alarms + InventoryLevel are resource-level, no actor segment.
            base = f"{prefix}/{resource_id_short}/{suffix_value}"
            if kind in ("state", "job_result"):
                _topic_routes[f"{base}/+"] = kind
            else:
                _topic_routes[base] = kind

    print(f"[discover] {len(_topic_routes)} topic filter(s) registered:")
    for filt, kind in _topic_routes.items():
        print(f"  {filt}  -> {kind}")
    return _topic_routes


# Track currently-subscribed per-resource filters so we can diff on each
# re-discovery and add/remove only the deltas.
_subscribed: set[str] = set()
_subscribe_lock = threading.Lock()


def resync_subscriptions(client: mqtt.Client) -> None:
    """Re-run AAS discovery and diff against current subscriptions.

    Subscribes to any new filters and unsubscribes from any that
    disappeared (resource deleted from the AAS or removed from the line).
    Safe to call repeatedly; paho is fine with concurrent (un)subscribe
    from any thread.
    """
    with _subscribe_lock:
        before = set(_subscribed)
        discover_resources()
        after = set(_topic_routes.keys())

        added = after - before
        removed = before - after

        for filt in added:
            client.subscribe(filt)
            _subscribed.add(filt)
            print(f"[discover] +sub {filt}")
        for filt in removed:
            client.unsubscribe(filt)
            _subscribed.discard(filt)
            print(f"[discover] -sub {filt}")
        if not added and not removed:
            # Quiet path: nothing changed since last sweep.
            pass


def _discovery_loop(client: mqtt.Client, stop_event: threading.Event) -> None:
    """Background re-discovery tick. Picks up resources added/removed on
    the AAS server while the bridge is running."""
    while not stop_event.wait(DISCOVERY_INTERVAL_S):
        try:
            resync_subscriptions(client)
        except Exception as exc:
            print(f"[discover] resync failed: {exc}")


def on_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code != 0:
        print(f"[MQTT] connect failed: rc={reason_code}")
        return
    print(f"[MQTT] connected to {MQTT_BROKER}:{MQTT_PORT}")
    for filt in _topic_routes:
        client.subscribe(filt)
        _subscribed.add(filt)
        print(f"[MQTT] subscribed to {filt}")
    for filt in (CONTROLLER_ALARM_TOPIC, ORDER_COMPLETED_TOPIC):
        client.subscribe(filt)
        print(f"[MQTT] subscribed to {filt}")


def _classify_topic(topic: str) -> str:
    """Return one of: 'controller_alarm', 'station_alarm', 'state',
    'job_result', 'order_completed', 'inventory', or 'unknown'.

    Per-resource classification is driven by `_topic_routes`, populated at
    startup from each Communication submodel. No suffix strings are
    hardcoded — change the Communication YAML and a re-run picks it up.
    """
    if topic == ORDER_COMPLETED_TOPIC:
        return "order_completed"
    if topic == CONTROLLER_ALARM_TOPIC:
        return "controller_alarm"
    for filt, kind in _topic_routes.items():
        if mqtt.topic_matches_sub(filt, topic):
            return kind
    return "unknown"


def _get_live_conn(userdata) -> psycopg2.extensions.connection:
    """Return a usable connection. Reconnects if the cached one is dead.

    Postgres restarts (or long-idle connections being kicked) mark the
    cached connection as `.closed != 0`; psycopg2 then raises
    `InterfaceError: connection already closed` on the next operation.
    Re-establishing transparently keeps the bridge running across DB
    blips without restart.
    """
    conn = userdata.get("conn")
    if conn is None or getattr(conn, "closed", 1):
        print("[DB] (re)connecting…")
        conn = connect_db()
        userdata["conn"] = conn
    return conn


def on_message(client, userdata, msg):
    try:
        conn = _get_live_conn(userdata)
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
        elif kind == "inventory":
            handle_inventory(conn, msg.topic, payload)
        else:
            print(f"[WARN] unhandled topic shape: {msg.topic}")
    except (psycopg2.InterfaceError, psycopg2.OperationalError) as exc:
        # Connection-level failure — drop the cached conn so the NEXT
        # message rebuilds it. This message is lost but the bridge stays
        # alive.
        print(f"[DB] {type(exc).__name__} on {msg.topic}: {exc} — will reconnect on next message")
        userdata["conn"] = None
    except Exception as exc:
        # Anything else (malformed payload, schema mismatch, …) is a
        # per-message bug; log + roll back the transaction.
        print(f"[ERROR] {type(exc).__name__} on {msg.topic}: {exc}")
        try:
            userdata.get("conn") and userdata["conn"].rollback()
        except Exception:
            pass


# ====== MAIN ======
def main() -> None:
    conn = connect_db()
    ensure_schema(conn)

    # Initial discovery before MQTT connect so on_connect has something to
    # subscribe to.
    discover_resources()

    client = mqtt.Client(
        client_id="MES_AlarmBridge",
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        userdata={"conn": conn},
    )
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)

    # Background re-discovery: picks up resources added or removed on the
    # AAS while the bridge is running. Each tick walks the AAS once and
    # subscribes/unsubscribes deltas — no full resubscribe.
    stop_event = threading.Event()
    discovery_thread: threading.Thread | None = None
    if DISCOVERY_INTERVAL_S > 0:
        discovery_thread = threading.Thread(
            target=_discovery_loop,
            args=(client, stop_event),
            name="aas-discovery",
            daemon=True,
        )
        discovery_thread.start()
        print(f"[discover] re-sync every {DISCOVERY_INTERVAL_S}s")

    print("[bridge] running — Ctrl+C to stop")
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("\n[bridge] stopping")
    finally:
        stop_event.set()
        if discovery_thread is not None:
            discovery_thread.join(timeout=2)
        client.disconnect()
        conn.close()


if __name__ == "__main__":
    main()
