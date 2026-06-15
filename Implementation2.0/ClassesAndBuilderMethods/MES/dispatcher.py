"""MES dispatcher — releases queued WorkOrders to the broker when the
line has spare capacity.

Capacity model: at most `max_concurrent` orders may be RELEASED but not yet
COMPLETED at any time. `max_concurrent` is driven by the Line Controller, which
publishes its live Transport-actor count (retained) on Controller/Capacity — the
true ceiling on simultaneous orders, since a shuttle is held from a part's first
Retrieve to its final Store. `MES_MAX_CONCURRENT` is only the fallback until that
message arrives. The dispatcher reacts to:

  - boot:            try to fill capacity with whatever is PENDING
  - OrderCompleted:  mark that order COMPLETED, then try to fill capacity
  - Capacity:        adopt the controller's value, then try to fill capacity

A safety-net periodic tick covers the unlikely case where an
OrderCompleted is lost (the bridge would also miss it, but the next
release attempt at boot or on the next completion will catch up).

Run as a long-lived process alongside `mes_api.py`:

    python -m Implementation2.0.ClassesAndBuilderMethods.MES.dispatcher

or directly:

    python Implementation2.0/ClassesAndBuilderMethods/MES/dispatcher.py
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from pathlib import Path

import paho.mqtt.client as mqtt

# Local imports — the module dir is on sys.path when run as a script.
THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

import queue_manager  # noqa: E402
import order_store    # noqa: E402
import webshop_notify  # noqa: E402

# Pull in the shared MessageStructure so we can parse OrderCompleted
# messages without re-declaring the schema.
_INFO_MODELS_DIR = THIS_DIR.parent / "InformationModels"
if str(_INFO_MODELS_DIR) not in sys.path:
    sys.path.insert(0, str(_INFO_MODELS_DIR))

import MessageStructure as MS  # noqa: E402


log = logging.getLogger("mes.dispatcher")
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)

MQTT_HOST = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
LINE_ID_DEFAULT = os.environ.get("LINE_ID", "ProductionLine1")
# Fallback capacity until the controller publishes the live transport-actor
# count on Controller/Capacity (see `_max_concurrent` below). The published
# value is authoritative once seen.
MAX_CONCURRENT_FALLBACK = int(os.environ.get("MES_MAX_CONCURRENT", "2"))
SAFETY_TICK_S = int(os.environ.get("MES_DISPATCH_TICK_S", "30"))

# Live capacity, driven by the controller's retained Controller/Capacity
# message. `_capacity_from_controller` flips True on the first such message, at
# which point the published value (not the env fallback) governs releases.
# Guarded by a lock because on_message and the safety thread both read it.
_capacity_lock = threading.Lock()
_max_concurrent = MAX_CONCURRENT_FALLBACK
_capacity_from_controller = False


def current_max_concurrent() -> int:
    with _capacity_lock:
        return _max_concurrent


def set_max_concurrent(value: int) -> bool:
    """Record a controller-published capacity. Returns True if it changed."""
    global _max_concurrent, _capacity_from_controller
    with _capacity_lock:
        changed = (not _capacity_from_controller) or value != _max_concurrent
        _max_concurrent = value
        _capacity_from_controller = True
    return changed
# Dispatcher-level retry: when the controller fully aborts an order
# (after exhausting its own OrderRecovery attempts), requeue it for
# another go after a backoff. Total worst case is MAX_ATTEMPTS × the
# controller's own 3-attempt cap.
MAX_ATTEMPTS = int(os.environ.get("MES_MAX_ATTEMPTS", "2"))
RETRY_BACKOFF_S = int(os.environ.get("MES_RETRY_BACKOFF_S", "60"))

# Topics. Order completion is what the controller publishes on every
# run_order exit (added in Step 3 of the metrics work).
ORDER_COMPLETED_TOPIC = f"AAUSmartLab/{LINE_ID_DEFAULT}/Controller/OrderCompleted"
# Retained capacity broadcast: the controller publishes the line's transport-
# actor count here on boot and on every line-config reload.
CAPACITY_TOPIC = f"AAUSmartLab/{LINE_ID_DEFAULT}/Controller/Capacity"


def workorder_topic(line_id: str) -> str:
    return f"AAUSmartLab/{line_id}/MES/WorkOrder"


# ── Release loop ──────────────────────────────────────────────────────


def try_release(client: mqtt.Client) -> int:
    """Publish PENDING orders until either the queue is empty or capacity
    is exhausted. Returns the number released this round.
    """
    released = 0
    while True:
        max_concurrent = current_max_concurrent()
        in_flight = queue_manager.in_flight_count()
        if in_flight >= max_concurrent:
            log.debug("[dispatch] at capacity (%s/%s)", in_flight, max_concurrent)
            return released

        candidate = queue_manager.peek_next()
        if candidate is None:
            return released

        order_id = candidate["order_id"]
        line_id = candidate["line_id"] or LINE_ID_DEFAULT
        payload = candidate["payload"]

        if not queue_manager.mark_released(order_id, line_id=line_id):
            # Another tick released this one between the peek and the
            # update. Move on.
            log.debug("[dispatch] race on %s; retrying", order_id)
            continue

        # retain=False because we rely on the controller's persistent
        # session (clean_session=False, subscribe qos=1) to receive
        # WorkOrders queued while it's offline. Retained would only
        # keep the LAST message per topic, which silently drops every
        # earlier one when multiple orders release back-to-back.
        client.publish(
            workorder_topic(line_id),
            json.dumps(payload, default=str),
            qos=1,
            retain=False,
        )
        log.info(
            "[dispatch] released %s to line %s (%d/%d in flight)",
            order_id, line_id, in_flight + 1, max_concurrent,
        )
        released += 1


# ── MQTT callbacks ────────────────────────────────────────────────────


def on_connect(client: mqtt.Client, userdata, flags, rc):
    if rc != 0:
        log.error("[mqtt] connect failed rc=%s", rc)
        return
    log.info("[mqtt] connected to %s:%s", MQTT_HOST, MQTT_PORT)
    client.subscribe(ORDER_COMPLETED_TOPIC, qos=1)
    log.info("[mqtt] subscribed to %s", ORDER_COMPLETED_TOPIC)
    # Retained capacity — delivered immediately on subscribe if the controller
    # has already published it, so we adopt the live value before releasing.
    client.subscribe(CAPACITY_TOPIC, qos=1)
    log.info("[mqtt] subscribed to %s", CAPACITY_TOPIC)
    # Boot-time release: catch up if anything was queued before we started.
    try_release(client)


def _resolve_batch_if_terminal(order_id: str, unit_terminal: str) -> None:
    """Resolve the whole webshop order once EVERY unit of its batch is terminal.

    A multi-product order fans out into several MES units sharing one webshop_id.
    Each unit finishes independently; we only resolve the customer order when no
    sibling is still PENDING/RELEASED, so one unit's outcome never disturbs the
    others while they're producing. Three terminal shapes:

      - every unit COMPLETED            -> fulfil the webshop order
      - mixed (some done, some failed)  -> close it; the produced units stay
                                           consumed, the reservation for the
                                           unproduced units is released
      - every unit failed               -> close it; full reservation released

    Call this only for a unit that is genuinely terminal — NOT one about to be
    requeued for another dispatcher attempt — so a retrying unit keeps the order
    open. Idempotent: webshop_notify ignores a repeat fulfil/cancel, so it's safe
    if two units reach terminal back-to-back. order_store re-reads from disk on
    miss, so this works even when the order was added after the dispatcher booted.
    """
    if queue_manager.batch_has_active_siblings(order_id):
        log.info(
            "[dispatch] %s terminal but batch still has active siblings — "
            "keeping webshop order open",
            order_id,
        )
        return
    order = order_store.get_order(order_id)
    if not order:
        log.debug("[dispatch] no order_store entry for %s — cannot resolve webshop", order_id)
        return
    webshop_id = order.get("webshop_id")
    if not webshop_id:
        log.debug("[dispatch] order %s has no webshop_id — skipping webshop resolve", order_id)
        return

    all_done, batch_id = queue_manager.batch_all_completed(order_id)
    if batch_id is None:
        # Not part of a multi-unit batch (lone order / legacy null batch_id):
        # resolve by this unit's own outcome rather than the batch query, which
        # reports False for a missing batch_id and would wrongly close a success.
        all_done = unit_terminal == "COMPLETED"
    if all_done:
        log.info(
            "[dispatch] batch %s fully complete — fulfilling webshop order %s",
            batch_id, webshop_id,
        )
        webshop_notify.complete_order(webshop_id)
    else:
        log.info(
            "[dispatch] batch %s terminal with failures — closing webshop order %s "
            "(releasing reservation for unproduced units)",
            batch_id, webshop_id,
        )
        webshop_notify.cancel_order(
            webshop_id,
            reason="Order closed: one or more units could not be produced",
        )


def on_message(client: mqtt.Client, userdata, msg):
    if msg.topic == CAPACITY_TOPIC:
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            capacity = MS.LineCapacityMessage(**payload)
        except Exception as exc:
            log.warning("[mqtt] bad Capacity payload: %s", exc)
            return
        if set_max_concurrent(capacity.max_concurrent):
            log.info(
                "[dispatch] capacity from controller: max_concurrent=%s",
                capacity.max_concurrent,
            )
            # Newly-granted capacity should be used immediately.
            try_release(client)
        return

    if msg.topic != ORDER_COMPLETED_TOPIC:
        return
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
        completed = MS.OrderCompletedMessage(**payload)
    except Exception as exc:
        log.warning("[mqtt] bad OrderCompleted payload: %s", exc)
        return

    terminal = (
        "COMPLETED"
        if completed.status == MS.OrderStatus.COMPLETED
        else "ABORTED"
    )
    queue_manager.mark_completed(completed.order_id, status=terminal)
    log.info(
        "[dispatch] order %s -> %s (attempts=%s)",
        completed.order_id, terminal, completed.attempt_count,
    )

    if terminal == "COMPLETED":
        # A completed unit may be the last of its batch to finish — resolve the
        # whole order (fulfil if all done, close if a sibling failed).
        _resolve_batch_if_terminal(completed.order_id, "COMPLETED")

    # Dispatcher-level retry on ABORTED. Look up the current
    # attempt_count via the queue (the controller's attempt_count in
    # the message is its own retry counter, separate from ours).
    if terminal == "ABORTED":
        row = queue_manager.get_order(completed.order_id) or {}
        cur_attempt = int(row.get("attempt_count") or 1)
        if cur_attempt < MAX_ATTEMPTS:
            ok, new_attempt = queue_manager.requeue_aborted(
                completed.order_id, backoff_seconds=RETRY_BACKOFF_S,
            )
            if ok:
                log.info(
                    "[dispatch] requeued %s for attempt %s (backoff %ss)",
                    completed.order_id, new_attempt, RETRY_BACKOFF_S,
                )
        else:
            log.info(
                "[dispatch] %s exhausted %s/%s dispatcher attempts — final ABORT",
                completed.order_id, cur_attempt, MAX_ATTEMPTS,
            )
            # This unit is now genuinely terminal. Resolve the batch: if it was
            # the last unit, close (or fulfil) the webshop order. Parts already
            # assembled into completed sub-assemblies stay consumed (their shells
            # remain referenced in product BOMs); only the unproduced units'
            # reservation is released. Best-effort; never raises.
            _resolve_batch_if_terminal(completed.order_id, "ABORTED")

    try_release(client)


# ── Safety-net periodic tick ──────────────────────────────────────────


def _safety_loop(client: mqtt.Client, stop: threading.Event) -> None:
    while not stop.wait(SAFETY_TICK_S):
        try:
            try_release(client)
        except Exception:
            log.exception("[safety] release failed")


# ── Entrypoint ────────────────────────────────────────────────────────


def main() -> None:
    queue_manager.init()
    log.info(
        "[dispatch] max_concurrent fallback=%s (awaiting %s) topic=%s",
        MAX_CONCURRENT_FALLBACK, CAPACITY_TOPIC, ORDER_COMPLETED_TOPIC,
    )

    client = mqtt.Client(client_id="MES_Dispatcher", clean_session=True)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)

    stop = threading.Event()
    safety = threading.Thread(
        target=_safety_loop, args=(client, stop), daemon=True
    )
    safety.start()

    try:
        client.loop_forever()
    except KeyboardInterrupt:
        log.info("[dispatch] stopping")
    finally:
        stop.set()
        client.disconnect()


if __name__ == "__main__":
    main()
