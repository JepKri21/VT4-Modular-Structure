"""
mes_api.py — FastAPI MES server.

POST /api/v1/orders  Receive mesPayload from Next.js webshop.
                     Returns 202 Accepted immediately; runs pipeline in background.

GET  /api/v1/orders  Returns internal order registry with status.

Start with:
    python -m uvicorn mes_api:app --host 0.0.0.0 --port 8000 --reload

The dispatcher and PSQL bridge start automatically as daemon threads alongside
the API server — no need to run them separately.
"""

import logging
import sys
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Resolve imports relative to this file
_MES_DIR = Path(__file__).resolve().parent

sys.path.insert(0, str(_MES_DIR))
sys.path.insert(0, str(_MES_DIR.parent / "InformationModels"))
sys.path.insert(0, str(_MES_DIR.parent / "BaSyx_AAS_Generator"))

import order_store
import order_processor
import queue_manager
import shell_uploader
import dispatcher
import psql_bridge

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
)
log = logging.getLogger("mes_api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure the schema exists *before* either background thread starts.
    # psql_bridge.main() also calls ensure_schema(), but it does so inside
    # its own thread — racing the dispatcher thread's on_connect, which
    # queries mes_orders as soon as MQTT connects. On a fresh database that
    # race can lose, crashing the dispatcher thread with UndefinedTable.
    schema_conn = psql_bridge.connect_and_init()
    if schema_conn is not None:
        schema_conn.close()

    t_dispatcher = threading.Thread(
        target=dispatcher.main, name="dispatcher", daemon=True
    )
    t_bridge = threading.Thread(
        target=psql_bridge.main, name="psql_bridge", daemon=True
    )
    t_dispatcher.start()
    t_bridge.start()
    log.info("Dispatcher and PSQL bridge started as background threads")
    yield
    log.info("API shutting down — daemon threads will stop with the process")


app = FastAPI(title="MES API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class MesPayload(BaseModel):
    class Config:
        extra = "allow"


@app.post("/api/v1/orders", status_code=202)
async def receive_order(payload: dict, background_tasks: BackgroundTasks):
    """
    Accept a mesPayload from the Next.js virtual store.
    Returns 202 immediately; the full pipeline runs in the background.
    """
    order_number = payload.get("orderNumber", "ORD-UNKNOWN")
    log.info("Received order %s", order_number)
    background_tasks.add_task(order_processor.process_order, payload)
    return {"accepted": True, "orderNumber": order_number}


@app.get("/api/v1/orders")
async def list_orders():
    """Return all orders with their current status."""
    return order_store.get_all()


@app.get("/api/v1/orders/{order_id}")
async def get_order(order_id: str):
    """Return a single order by ID."""
    order = order_store.get_order(order_id)
    if order is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@app.delete("/api/v1/orders/{webshop_id}/shells", status_code=200)
async def delete_order_shells(webshop_id: str, background_tasks: BackgroundTasks):
    """
    Delete all BaSyx shells that were uploaded for a given webshop order UUID.
    Called by the Next.js app when an order is cancelled by the user.
    """
    orders = order_store.get_orders_by_webshop_id(webshop_id)
    if not orders:
        log.warning("delete_order_shells: no MES record for webshop_id=%s", webshop_id)
        return {"ok": True, "deleted": 0}

    # A multi-product webshop order fans out into one MES order per product,
    # each with its own shells — schedule cleanup for every one of them.
    total = 0
    for order in orders:
        iris = order.get("shell_iris", {})
        if not iris:
            continue
        order_id = order.get("order_id", webshop_id)
        log.info("Scheduling shell cleanup for order %s (%d shells)", order_id, len(iris))
        background_tasks.add_task(shell_uploader.delete_all, iris)
        total += len(iris)

    if total == 0:
        log.info("delete_order_shells: no shells recorded for webshop_id=%s", webshop_id)
    return {"ok": True, "deleted": total}


@app.post("/api/v1/orders/{batch_id}/priority")
async def set_order_priority(batch_id: str, payload: dict):
    """Bump a batch to the front of the dispatch queue.

    `batch_id` is the MES batch id ("ORD-<8hex>"). Only orders still PENDING in
    the queue can be reordered; once released to the line, priority is ignored.
    Lower priority number = dispatched sooner (default 100).
    """
    try:
        priority = int(payload.get("priority", 0))
    except (TypeError, ValueError):
        priority = 0
    updated = queue_manager.set_priority_by_batch(batch_id, priority)
    return {"ok": True, "batch_id": batch_id, "priority": priority, "updated": updated}


@app.get("/health")
async def health():
    return {"status": "ok"}
