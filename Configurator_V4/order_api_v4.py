"""
Order API V4 — Flask REST API for the V4 configurator/assembly system.

Endpoints
---------
GET  /api/v4/inventory                                   – current stock levels
GET  /api/v4/options                                     – available config options
POST /api/v4/orders                                      – place a new order (Phase 1)
GET  /api/v4/orders                                      – list all orders
GET  /api/v4/orders/<order_id>                           – get single order detail
POST /api/v4/orders/<order_id>/step1                     – assembly step 1 (Housing)
POST /api/v4/orders/<order_id>/step2                     – assembly step 2 (PCB+Fuse)
POST /api/v4/orders/<order_id>/step3                     – assembly step 3 (Final)
POST /api/v4/orders/<order_id>/assemble                  – run all 3 steps in sequence
POST /api/v4/orders/<order_id>/release                   – ship the assembled Telefon
POST /api/v4/orders/<order_id>/cancel                    – cancel a pending order

Run
---
  cd Configurator_V4
  python order_api_v4.py          # default port 2002
  python order_api_v4.py --port 5000

Step 1 request body (all fields optional — omit to auto-select):
  {
    "bottom_cover_instance_id": "urn:aas:...",
    "pcb_instance_id":          "urn:aas:..."
  }

Step 2 request body (optional):
  {
    "fuse_instance_ids": ["urn:aas:...", "urn:aas:..."]
  }

Step 3 request body (optional):
  {
    "top_cover_instance_id": "urn:aas:..."
  }

Assemble request body (all optional — combines step 1+2+3 bodies):
  {
    "bottom_cover_instance_id": "urn:aas:...",
    "pcb_instance_id":          "urn:aas:...",
    "fuse_instance_ids":        ["urn:aas:..."],
    "top_cover_instance_id":    "urn:aas:..."
  }
"""

import argparse
import json
import sqlite3
from pathlib import Path

from flask import Flask, jsonify, request

from configurator_v4 import TelefonConfiguratorV4
from assembly_manager_v4 import AssemblyManagerV4
from inventory_db import (
    _create_tables, _get_connection, _rebuild_stock, reset_db, CONFIGURATOR_BASE, DEFAULT_DB_FILE,
)
from asset_registry import ASSET_REGISTRY

# =============================================================================
# App setup
# =============================================================================

app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False

configurator = TelefonConfiguratorV4()
assembly_mgr = AssemblyManagerV4()

DB_PATH = DEFAULT_DB_FILE


# =============================================================================
# Helpers
# =============================================================================

def _get_inventory_rows():
    conn = _get_connection(DB_PATH)
    _create_tables(conn)
    _rebuild_stock(conn)
    # Only show raw components — exclude sub-assemblies and final products
    non_component_types = [
        k for k, cfg in ASSET_REGISTRY.items() if not cfg.get("is_component", False)
    ]
    placeholders = ",".join("?" * len(non_component_types))
    rows = conn.execute(f"""
        SELECT model_number, component_type, material, color, finish, nr_fuses,
               qty_available, qty_reserved, qty_consumed, qty_total
        FROM inventory_stock
        WHERE (qty_available > 0 OR qty_reserved > 0)
          AND component_type NOT IN ({placeholders})
        ORDER BY component_type, model_number
    """, non_component_types).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _get_order_row(order_id: str) -> dict:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM configuration_orders WHERE order_id = ?", (order_id,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    for col in ("configuration", "model_numbers_needed", "shell_instances", "assembly_progress"):
        try:
            d[col] = json.loads(d[col]) if d[col] else None
        except (TypeError, ValueError):
            pass
    return d


# =============================================================================
# Routes
# =============================================================================

@app.route("/api/v4/inventory", methods=["GET"])
def inventory():
    try:
        return jsonify(_get_inventory_rows()), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/v4/options", methods=["GET"])
def options():
    """Return available configuration options (combos with stock > 0)."""
    try:
        opts = configurator._get_available_options()
        # Combos are already list-of-dicts from _get_available_options; pass through directly.
        return jsonify(opts), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/v4/orders", methods=["POST"])
def place_order():
    """
    Phase 1 — place a new production order.

    Request body:
      {
        "bottom_cover_material": "PLA-31212",
        "bottom_cover_color":    "Red",
        "bottom_cover_finish":   "Glossy",
        "top_cover_material":    "PLA-31212",
        "top_cover_color":       "Red",
        "top_cover_finish":      "Glossy",
        "number_of_fuses":       1
      }

    Response (201):
      {
        "order_id":           "ORD-001",
        "product_type":       "Telefon_Pro_Max",
        "configuration":      { ... },
        "shell_instances":    {"Housing_With_PCB": "001", "PCB_With_Fuse": "001", "Telefon": "001"},
        "reservation_slots":  {"Bottom_Cover": "BC-...", "Fuse_1": "FUSE-AAU"},
        "inventory_status":   { ... },
        "created_date":       "...",
        "status":             "pending"
      }
    """
    try:
        config = request.get_json(force=True)
        if not config:
            return jsonify({"error": "No configuration provided"}), 400

        order_id, details = configurator.create_order(config)

        conn = _get_connection(DB_PATH)
        _rebuild_stock(conn)
        conn.close()

        return jsonify({
            "order_id":             details["order_id"],
            "product_type":         details["product_type"],
            "configuration":        details["configuration"],
            "model_numbers_needed": details["model_numbers_needed"],
            "shell_instances":      details["shell_instances"],
            "reservation_slots":    details["reservation_slots"],
            "inventory_status":     details["inventory_status"],
            "created_date":         details["created_date"],
            "status":               "pending",
        }), 201

    except ValueError as e:
        return jsonify({"error": str(e)}), 422
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/v4/orders", methods=["GET"])
def list_orders():
    """Return all orders, newest first."""
    try:
        orders = assembly_mgr.list_orders()
        for o in orders:
            for col in ("configuration", "model_numbers_needed", "shell_instances", "assembly_progress"):
                try:
                    o[col] = json.loads(o[col]) if o[col] else None
                except (TypeError, ValueError):
                    pass
        return jsonify(orders), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/v4/orders/<order_id>", methods=["GET"])
def get_order(order_id: str):
    """Return a single order with all details."""
    try:
        d = _get_order_row(order_id)
        if not d:
            return jsonify({"error": f"Order not found: {order_id}"}), 404
        return jsonify(d), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/v4/orders/<order_id>/step1", methods=["POST"])
def assembly_step1(order_id: str):
    """
    Assembly Step 1 — Station 1: Bottom_Cover + PCB → Housing_With_PCB.

    Optional body:
      { "bottom_cover_instance_id": "urn:...", "pcb_instance_id": "urn:..." }
    If omitted, the first available instance of each model type is used.
    """
    try:
        body = request.get_json(force=True) or {}
        result = assembly_mgr.assemble_step1_housing(
            order_id,
            bottom_cover_instance_id=body.get("bottom_cover_instance_id"),
            pcb_instance_id=body.get("pcb_instance_id"),
        )
        return jsonify({"order_id": order_id, "status": "step1_done", **result}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 422


@app.route("/api/v4/orders/<order_id>/step2", methods=["POST"])
def assembly_step2(order_id: str):
    """
    Assembly Step 2 — Station 2: Fuse(s) → PCB_With_Fuse.

    Optional body:
      { "fuse_instance_ids": ["urn:...", "urn:..."] }
    List length must match the order's number_of_fuses if provided.
    """
    try:
        body = request.get_json(force=True) or {}
        result = assembly_mgr.assemble_step2_pcb_fuse(
            order_id,
            fuse_instance_ids=body.get("fuse_instance_ids"),
        )
        return jsonify({"order_id": order_id, "status": "step2_done", **result}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 422


@app.route("/api/v4/orders/<order_id>/step3", methods=["POST"])
def assembly_step3(order_id: str):
    """
    Assembly Step 3 — Station 3: Top_Cover + sub-assemblies → Final Telefon.

    Optional body:
      { "top_cover_instance_id": "urn:..." }
    """
    try:
        body = request.get_json(force=True) or {}
        result = assembly_mgr.assemble_step3_final(
            order_id,
            top_cover_instance_id=body.get("top_cover_instance_id"),
        )
        return jsonify({"order_id": order_id, "status": "assembled", **result}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 422


@app.route("/api/v4/orders/<order_id>/assemble", methods=["POST"])
def assemble_all(order_id: str):
    """
    Run all 3 assembly steps in sequence.

    Optional body (same as combining step1/2/3 bodies):
      {
        "bottom_cover_instance_id": "urn:...",
        "pcb_instance_id":          "urn:...",
        "fuse_instance_ids":        ["urn:..."],
        "top_cover_instance_id":    "urn:..."
      }
    """
    try:
        body = request.get_json(force=True) or {}
        result = assembly_mgr.assemble_all(
            order_id,
            bottom_cover_instance_id=body.get("bottom_cover_instance_id"),
            pcb_instance_id=body.get("pcb_instance_id"),
            fuse_instance_ids=body.get("fuse_instance_ids"),
            top_cover_instance_id=body.get("top_cover_instance_id"),
        )
        return jsonify({"order_id": order_id, "status": "assembled", **result}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 422


@app.route("/api/v4/orders/<order_id>/release", methods=["POST"])
def release_order(order_id: str):
    """
    Release (ship) a fully assembled Telefon.
    Transitions the order status from 'assembled' to 'released' and marks
    the Telefon inventory item as 'consumed' (shipped).
    """
    try:
        assembly_mgr.release_order(order_id)
        return jsonify({"order_id": order_id, "status": "released"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 422


@app.route("/api/v4/admin/reset", methods=["POST"])
def admin_reset():
    """
    Development reset: wipe all orders, reservations, and inventory, then re-sync
    from the JSON instance files on disk.
    """
    try:
        reset_db(DB_PATH, CONFIGURATOR_BASE)
        return jsonify({"status": "ok", "message": "Database reset and re-synced."}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/v4/orders/<order_id>/cancel", methods=["POST"])
def cancel_order(order_id: str):
    """
    Cancel a pending or in-progress order.
    Releases all pending model-type reservations so stock is freed.
    Already-consumed components from partial assembly are NOT restored.
    """
    try:
        assembly_mgr.cancel_order(order_id)
        return jsonify({"order_id": order_id, "status": "cancelled"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 422


# =============================================================================
# Entry point
# =============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Order API V4")
    parser.add_argument("--port", type=int, default=2002, help="Port to run on (default: 2002)")
    parser.add_argument("--debug", action="store_true", help="Run Flask in debug mode")
    args = parser.parse_args()

    print(f"\n=== Order API V4 ===")
    print(f"  Inventory DB : {DB_PATH}")
    print(f"  JSON base    : {CONFIGURATOR_BASE}")
    print(f"  Listening on : http://127.0.0.1:{args.port}\n")

    app.run(port=args.port, debug=args.debug)
