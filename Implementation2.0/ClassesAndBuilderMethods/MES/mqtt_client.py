"""
mqtt_client.py — paho-mqtt wrapper for MES WorkOrder publishing and status receipt.

Publishes WorkOrderMessage (retained) to AAUSmartLab/<line_id>/MES/WorkOrder.
Subscribes to AAUSmartLab/+/LC/WorkOrderStatus and updates order_store on receipt.
"""

import json
import logging
import threading
from datetime import datetime
from typing import Optional

import paho.mqtt.client as mqtt

import order_store
from sys import path as _path
from pathlib import Path as _Path
_path.insert(0, str(_Path(__file__).parent.parent / "InformationModels"))
from MessageStructure import WorkOrderMessage, WorkOrderStatusMessage

log = logging.getLogger(__name__)

MQTT_HOST = "localhost"
MQTT_PORT = 1883

_client: Optional[mqtt.Client] = None
_client_lock = threading.Lock()


def _get_client() -> mqtt.Client:
    global _client
    with _client_lock:
        if _client is None:
            c = mqtt.Client(client_id="MES", clean_session=False)
            c.on_connect = _on_connect
            c.on_message = _on_message
            c.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
            c.loop_start()
            _client = c
        return _client


def _on_connect(client, userdata, flags, rc):
    if rc == 0:
        client.subscribe("AAUSmartLab/+/LC/WorkOrderStatus")
        log.info("MQTT connected, subscribed to WorkOrderStatus")
    else:
        log.error("MQTT connect failed rc=%s", rc)


def _on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
        status_msg = WorkOrderStatusMessage(**payload)
        order_store.update_status(
            status_msg.order_id,
            status_msg.status.value,
            status_msg.line_id,
        )
        log.info("WorkOrderStatus %s → %s", status_msg.order_id, status_msg.status)
    except Exception as exc:
        log.warning("Failed to parse WorkOrderStatus: %s", exc)


def _workorder_to_pascal_dict(wo: WorkOrderMessage) -> dict:
    raw = wo.model_dump(mode="json")
    result = {
        "Timestamp": raw["timestamp"],
        "OrderId": raw["order_id"],
        "Priority": raw["priority"],
        "IssueDate": raw["issue_date"],
        "ProductReference": raw["product_reference"],
        "Ingredients": raw["ingredients"],
        "Properties": raw["properties"],
        "Assemblies": raw["assemblies"],
        "ProcessSteps": raw["process_steps"],
    }
    if raw.get("seq_no") is not None:
        result["SeqNo"] = raw["seq_no"]
    return result


def publish_workorder(line_id: str, workorder: WorkOrderMessage) -> None:
    """Publish WorkOrderMessage (retained) to AAUSmartLab/<line_id>/MES/WorkOrder."""
    client = _get_client()
    topic = f"AAUSmartLab/{line_id}/MES/WorkOrder"
    payload = json.dumps(_workorder_to_pascal_dict(workorder), default=str)
    client.publish(topic, payload, qos=1, retain=True)
    log.info("Published WorkOrder %s to %s", workorder.order_id, topic)


def ensure_connected() -> None:
    _get_client()
