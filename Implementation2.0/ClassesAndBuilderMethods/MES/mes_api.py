"""
mes_api.py — FastAPI MES server.

POST /api/v1/orders  Receive mesPayload from Next.js webshop.
                     Returns 202 Accepted immediately; runs pipeline in background.

GET  /api/v1/orders  Returns internal order registry with status.

Start with:
    uvicorn mes_api:app --host 0.0.0.0 --port 8000 --reload
"""

import asyncio
import logging
import sys
from pathlib import Path

from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Resolve imports relative to this file
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "InformationModels"))
sys.path.insert(0, str(Path(__file__).parent.parent / "BaSyx_AAS_Generator"))

import order_store
import order_processor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
)
log = logging.getLogger("mes_api")

app = FastAPI(title="MES API", version="1.0.0")

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


@app.get("/health")
async def health():
    return {"status": "ok"}
