"""
order_store.py — In-memory + JSON file order registry.

Tracks each order: order_id, line_id, status, timestamps.
Status is updated by mqtt_client when WorkOrderStatusMessages arrive.
"""

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

STORE_FILE = Path(__file__).parent / "orders.json"

_lock = threading.Lock()
_orders: dict[str, dict] = {}


def _load_from_disk() -> None:
    global _orders
    if STORE_FILE.exists():
        try:
            with open(STORE_FILE, encoding="utf-8") as f:
                _orders = json.load(f)
        except (json.JSONDecodeError, OSError):
            _orders = {}


def _save_to_disk() -> None:
    try:
        with open(STORE_FILE, "w", encoding="utf-8") as f:
            json.dump(_orders, f, indent=2, ensure_ascii=False)
    except OSError:
        pass


_load_from_disk()


def add_order(order_id: str, line_id: Optional[str] = None, webshop_id: Optional[str] = None) -> None:
    with _lock:
        _orders[order_id] = {
            "order_id": order_id,
            "webshop_id": webshop_id,
            "line_id": line_id,
            "status": "PENDING",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        _save_to_disk()


def update_status(order_id: str, status: str, line_id: Optional[str] = None, error: Optional[str] = None) -> None:
    with _lock:
        if order_id not in _orders:
            _orders[order_id] = {"order_id": order_id}
        _orders[order_id]["status"] = status
        _orders[order_id]["updated_at"] = datetime.now().isoformat()
        if line_id:
            _orders[order_id]["line_id"] = line_id
        if error:
            _orders[order_id]["error"] = error
        _save_to_disk()


def update_shell_iris(order_id: str, shell_iris: dict[str, str]) -> None:
    with _lock:
        if order_id in _orders:
            _orders[order_id]["shell_iris"] = shell_iris
            _orders[order_id]["updated_at"] = datetime.now().isoformat()
            _save_to_disk()


def get_all() -> list[dict]:
    with _lock:
        return list(_orders.values())


def get_order(order_id: str) -> Optional[dict]:
    with _lock:
        return _orders.get(order_id)


def get_order_by_webshop_id(webshop_id: str) -> Optional[dict]:
    with _lock:
        for order in _orders.values():
            if order.get("webshop_id") == webshop_id:
                return order
        return None
