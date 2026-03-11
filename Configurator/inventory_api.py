from flask import Flask, jsonify, request
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from configurator_v3 import TelefonConfiguratorV3
from inventory_db import _rebuild_stock, _get_connection, _create_tables

app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False

BASE_PATH = Path(__file__).parent
DB_PATH = BASE_PATH / "inventory.db"

# Initialize configurator
configurator = TelefonConfiguratorV3(str(BASE_PATH))


def get_inventory():
    conn = _get_connection(str(DB_PATH))
    _create_tables(conn)
    # Always recount from inventory_items so qty reflects the latest reservations.
    _rebuild_stock(conn)

    rows = conn.execute(
        """
        SELECT 
            model_number, 
            component_type, 
            material, 
            color, 
            finish,
            nr_fuses,
            qty_available,
            qty_reserved,
            qty_total
        FROM inventory_stock 
        WHERE qty_total > 0
        ORDER BY component_type, model_number
        """
    ).fetchall()

    conn.close()
    return [dict(row) for row in rows]


@app.route("/api/inventory", methods=["GET"])
def inventory():
    try:
        data = get_inventory()
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/configurator/options", methods=["GET"])
def configurator_options():
    try:
        options = configurator._get_available_options()

        # Convert tuple combo keys to objects
        options["bottom_cover_combos"] = [
            {
                "material": m,
                "color": c,
                "finish": f,
                "qty": q
            }
            for (m, c, f), q in options["bottom_cover_combos"].items()
        ]

        options["top_cover_combos"] = [
            {
                "material": m,
                "color": c,
                "finish": f,
                "qty": q
            }
            for (m, c, f), q in options["top_cover_combos"].items()
        ]

        return jsonify(options), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/configurator/order", methods=["POST"])
def create_order():
    """Create a new configuration order and reserve inventory."""
    try:
        config = request.get_json(force=True)
        if not config:
            return jsonify({"error": "No configuration provided"}), 400

        order_id, details = configurator.create_configuration_order(config)

        # Recount stock immediately so subsequent inventory requests are current.
        conn = _get_connection(str(DB_PATH))
        _rebuild_stock(conn)
        conn.close()

        return jsonify({
            "order_id": order_id,
            "product_type": details["product_type"],
            "configuration": details["configuration"],
            "model_numbers_needed": details["model_numbers_needed"],
            "inventory_status": details["inventory_status"],
            "created_date": details["created_date"],
            "status": "pending",
        }), 201

    except ValueError as e:
        return jsonify({"error": str(e)}), 422
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/configurator/orders", methods=["GET"])
def list_orders():
    """Return all configuration orders."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT order_id, product_type, configuration,
                   model_numbers_needed, status, created_date
            FROM configuration_orders
            ORDER BY created_date DESC
            """
        ).fetchall()
        conn.close()

        orders = []
        for row in rows:
            d = dict(row)
            # Parse JSON-encoded columns
            for col in ("configuration", "model_numbers_needed"):
                try:
                    d[col] = json.loads(d[col])
                except (TypeError, ValueError):
                    pass
            orders.append(d)

        return jsonify(orders), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/configurator/order/<order_id>/release", methods=["POST"])
def release_order(order_id):
    """
    Release (ship) a fully assembled Telefon.

    Marks the Telefon inventory_items row as 'consumed' (shipped) and
    transitions the order status from 'assembled' → 'released'.
    Rebuilds stock so the phone disappears from the available count.
    """
    try:
        conn = _get_connection(str(DB_PATH))
        _create_tables(conn)

        order = conn.execute(
            "SELECT * FROM configuration_orders WHERE order_id = ?", (order_id,)
        ).fetchone()
        if not order:
            conn.close()
            return jsonify({"error": f"Order not found: {order_id}"}), 404
        if order["status"] != "assembled":
            conn.close()
            return jsonify({
                "error": f"Order {order_id} cannot be released (current status: {order['status']})"
            }), 422

        progress = json.loads(order["assembly_progress"] or "{}")
        telefon_instance_id = progress.get("telefon_instance_id")

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if telefon_instance_id:
            conn.execute(
                "UPDATE inventory_items SET status = 'consumed', last_updated = ? "
                "WHERE instance_id = ? AND status != 'consumed'",
                (now, telefon_instance_id),
            )

        conn.execute(
            "UPDATE configuration_orders SET status = 'released', assembled_date = ? "
            "WHERE order_id = ?",
            (now, order_id),
        )
        conn.commit()
        _rebuild_stock(conn)
        conn.close()

        return jsonify({
            "order_id": order_id,
            "status": "released",
            "released_date": now,
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(port=2001)