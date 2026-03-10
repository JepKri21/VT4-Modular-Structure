from flask import Flask, jsonify
import sqlite3
from pathlib import Path
from configurator_v3 import TelefonConfiguratorV3

app = Flask(__name__)

BASE_PATH = Path(__file__).parent
DB_PATH = BASE_PATH / "inventory.db"

# Initialize configurator
configurator = TelefonConfiguratorV3(str(BASE_PATH))


def get_inventory():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        """
        SELECT 
            model_number, 
            component_type, 
            material, 
            color, 
            qty_available 
        FROM inventory_stock 
        WHERE qty_available > 0
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


if __name__ == "__main__":
    app.run(port=2001)