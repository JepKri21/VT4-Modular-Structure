"""
Inventory Database Manager — V4 Edition

Extended copy of Configurator/inventory_db.py with:
  - model_type_reservations table  (V4: reserve by model-type quantity, not specific instance)
  - shell_instances column on configuration_orders  (V4: tracks which shells were created at order time)
  - _rebuild_stock accounts for pending model-type reservations
  - Helpers: _reserve_model_types, _fulfill_reservation, _cancel_order_reservations

Both v3 and v4 share the same inventory.db file.  V4 tables are additive and do not
break v3 operations.

Usage (CLI — scans the shared v3 JSON instance directories):
  python inventory_db.py --sync
  python inventory_db.py --status
"""

import json
import re
import sqlite3
import argparse
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from asset_registry import ASSET_REGISTRY

# =============================================================================
# Configuration
# =============================================================================

# Python scripts live here; the DB stays in this directory.
CONFIGURATOR_BASE = Path(__file__).parent

# All JSON type/instance files live under AAS_files/ at the repo root.
AAS_FILES_BASE = Path(__file__).parent.parent / "AAS_files"

INSTANCE_SUBMODEL_DIRS = [
    "JSON_Submodels/Product_Submodels_JSON/Instances/Component_Instance_Submodels",
    "JSON_Submodels/Product_Submodels_JSON/Instances/Sub_Assembly_Instance_Submodels",
    "JSON_Submodels/Product_Submodels_JSON/Instances/Final_Product_Instance_Submodels",
]

# Maps registry_key → (type_submodels_dir, type_submodel_prefix).
# Built dynamically from ASSET_REGISTRY so adding a new component only requires
# editing asset_registry.py.
REGISTRY_KEY_TO_TYPE_DOC: Dict[str, tuple] = {
    cfg["registry_key"]: (cfg["type_submodels_dir"], cfg["type_submodel_prefix"])
    for cfg in ASSET_REGISTRY.values()
    if "registry_key" in cfg
}

DEFAULT_DB_FILE = str(CONFIGURATOR_BASE / "inventory.db")


# =============================================================================
# Database setup
# =============================================================================

def _get_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _create_tables(conn: sqlite3.Connection) -> None:
    """Create all inventory tables (v3 schema + v4 extensions) if they do not exist."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS inventory_items (
            instance_id         TEXT PRIMARY KEY,
            instance_number     TEXT NOT NULL,
            model_number        TEXT NOT NULL,
            component_type      TEXT NOT NULL,
            product_name        TEXT,
            material            TEXT,
            color               TEXT,
            finish              TEXT,
            nr_fuses            INTEGER,
            created_date        TEXT,
            status              TEXT NOT NULL DEFAULT 'available',
            last_updated        TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS inventory_stock (
            model_number        TEXT PRIMARY KEY,
            component_type      TEXT NOT NULL,
            product_name        TEXT,
            material            TEXT,
            color               TEXT,
            finish              TEXT,
            nr_fuses            INTEGER,
            qty_available       INTEGER NOT NULL DEFAULT 0,
            qty_reserved        INTEGER NOT NULL DEFAULT 0,
            qty_consumed        INTEGER NOT NULL DEFAULT 0,
            qty_total           INTEGER NOT NULL DEFAULT 0,
            last_updated        TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS model_catalog (
            model_number        TEXT PRIMARY KEY,
            component_type      TEXT NOT NULL,
            product_name        TEXT,
            first_seen          TEXT NOT NULL,
            last_seen           TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS configuration_orders (
            order_id            TEXT PRIMARY KEY,
            product_type        TEXT NOT NULL,
            configuration       TEXT NOT NULL,
            model_numbers_needed TEXT NOT NULL,
            reserved_instances  TEXT,
            status              TEXT NOT NULL DEFAULT 'pending',
            assembly_progress   TEXT,
            created_date        TEXT NOT NULL,
            assembled_date      TEXT,
            notes               TEXT
        );

        CREATE TABLE IF NOT EXISTS assembly_log (
            assembly_id         TEXT PRIMARY KEY,
            product_instance_id TEXT NOT NULL,
            component_type      TEXT NOT NULL,
            component_instance_id TEXT NOT NULL,
            model_number        TEXT NOT NULL,
            assembly_date       TEXT NOT NULL
        );

        -- V4: model-type (quantity) reservations — no specific instance locked.
        CREATE TABLE IF NOT EXISTS model_type_reservations (
            reservation_id  TEXT PRIMARY KEY,   -- "{order_id}:{slot_key}"
            order_id        TEXT NOT NULL,
            slot_key        TEXT NOT NULL,       -- e.g. "Bottom_Cover", "Fuse_1"
            model_number    TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'pending',
            -- 'pending'   : reserved but not yet consumed
            -- 'fulfilled' : the physical instance was consumed during assembly
            -- 'cancelled' : order cancelled before assembly
            created_date    TEXT NOT NULL
        );
    """)

    # Migrations — safe to run on existing DBs
    for migration in [
        # v3 migrations
        "ALTER TABLE configuration_orders ADD COLUMN assembly_progress TEXT",
        # v4 migrations
        "ALTER TABLE configuration_orders ADD COLUMN shell_instances TEXT",
        "ALTER TABLE inventory_items ADD COLUMN nr_fuses INTEGER",
        "ALTER TABLE inventory_stock ADD COLUMN nr_fuses INTEGER",
    ]:
        try:
            conn.execute(migration)
        except sqlite3.OperationalError:
            pass  # column/table already exists

    conn.commit()


# =============================================================================
# JSON parsing helpers (unchanged from v3)
# =============================================================================

def _get_prop(elements: List[Dict], id_short: str) -> Optional[str]:
    for elem in elements:
        if elem.get("idShort") == id_short:
            return elem.get("value")
    return None


def _get_list_prop(elements: List[Dict], list_id_short: str, prop_id_short: str) -> Optional[str]:
    for elem in elements:
        if elem.get("idShort") == list_id_short:
            for item in elem.get("value", []):
                if item.get("idShort") == prop_id_short:
                    return item.get("value")
    return None


def _parse_model_number_properties(model_number: str, component_type: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    if component_type == "PCB_With_Fuse":
        fuse_match = re.search(r'-F(\d+)$', model_number)
        if fuse_match:
            result["nr_fuses"] = int(fuse_match.group(1))
    if component_type == "Housing_With_PCB":
        hwp_match = re.match(r'^HWP-([^-]+)-[^-]+-([^-]+)-F\d+$', model_number)
        if hwp_match:
            result["material"] = hwp_match.group(1)
            result["color"]    = hwp_match.group(2)
    return result


def _parse_component_type(filename: str):
    name = filename
    for prefix in (
        "Product-Component-AAU-",
        "Product-Sub_Assembly-AAU-",
        "Product-Final_Product-Telefon-",
    ):
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    parts = name.rsplit("-", 2)
    return parts[0] if len(parts) >= 3 else "Unknown"


def _parse_instance_number(filename: str) -> str:
    parts = filename.rsplit("-", 2)
    return parts[1] if len(parts) >= 3 else "000"


# =============================================================================
# V4 Reservation helpers
# =============================================================================

def _reserve_model_types(
    conn: sqlite3.Connection,
    order_id: str,
    slots: Dict[str, str],           # {slot_key: model_number}
) -> None:
    """
    Insert a pending model-type reservation row for each required slot.
    Does NOT lock any specific inventory_items row — reservation is at
    the model/quantity level only.
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for slot_key, model_number in slots.items():
        conn.execute("""
            INSERT INTO model_type_reservations
                (reservation_id, order_id, slot_key, model_number, status, created_date)
            VALUES (?, ?, ?, ?, 'pending', ?)
            ON CONFLICT(reservation_id) DO NOTHING
        """, (f"{order_id}:{slot_key}", order_id, slot_key, model_number, now))


def _fulfill_reservation(
    conn: sqlite3.Connection,
    order_id: str,
    slot_key: str,
) -> None:
    """Mark a model-type reservation as fulfilled (physical instance consumed)."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("""
        UPDATE model_type_reservations
        SET status = 'fulfilled'
        WHERE reservation_id = ? AND status = 'pending'
    """, (f"{order_id}:{slot_key}",))


def _cancel_order_reservations(conn: sqlite3.Connection, order_id: str) -> int:
    """Cancel all pending model-type reservations for an order. Returns rows affected."""
    cur = conn.execute("""
        UPDATE model_type_reservations
        SET status = 'cancelled'
        WHERE order_id = ? AND status = 'pending'
    """, (order_id,))
    return cur.rowcount


# =============================================================================
# Core sync logic (unchanged from v3)
# =============================================================================

def _update_catalog(conn: sqlite3.Connection, records: List[Dict[str, Any]]) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for r in records:
        conn.execute("""
            INSERT INTO model_catalog (model_number, component_type, product_name, first_seen, last_seen)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(model_number) DO UPDATE SET
                last_seen    = excluded.last_seen,
                product_name = excluded.product_name
        """, (r["model_number"], r["component_type"], r["product_name"], now, now))
    conn.commit()


def _collect_instances(base_path: Path) -> List[Dict[str, Any]]:
    records = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for rel_dir in INSTANCE_SUBMODEL_DIRS:
        submodel_dir = base_path / rel_dir
        if not submodel_dir.exists():
            print(f"  ⚠  Directory not found, skipping: {submodel_dir}")
            continue

        for doc_file in sorted(submodel_dir.glob("*-Documentation.json")):
            filename = doc_file.name
            with open(doc_file, encoding="utf-8") as f:
                doc = json.load(f)

            elements = doc.get("submodelElements", [])
            model_number   = _get_prop(elements, "Model_Number")
            instance_num   = _get_prop(elements, "Instance_Number")
            product_name   = _get_prop(elements, "Product_Name")
            created_date   = _get_prop(elements, "Created_Date")
            instance_id    = doc.get("id", "")
            component_type = _parse_component_type(filename)

            if not model_number:
                print(f"  ⚠  No Model_Number in {filename}, skipping.")
                continue

            props_file = doc_file.with_name(filename.replace("-Documentation.json", "-Properties.json"))
            material = color = finish = None
            if props_file.exists():
                with open(props_file, encoding="utf-8") as f:
                    props = json.load(f)
                prop_elems = props.get("submodelElements", [])
                material = _get_list_prop(prop_elems, "List_Of_Properties", "Material")
                color    = _get_list_prop(prop_elems, "List_Of_Properties", "Color")
                finish   = _get_list_prop(prop_elems, "List_Of_Properties", "Finish")

            parsed = _parse_model_number_properties(model_number, component_type)
            if material is None: material = parsed.get("material")
            if color    is None: color    = parsed.get("color")
            nr_fuses = parsed.get("nr_fuses")

            records.append({
                "instance_id":     instance_id,
                "instance_number": instance_num or _parse_instance_number(filename),
                "model_number":    model_number,
                "component_type":  component_type,
                "product_name":    product_name,
                "material":        material,
                "color":           color,
                "finish":          finish,
                "nr_fuses":        nr_fuses,
                "created_date":    created_date,
                "status":          "available",
                "last_updated":    now,
            })

    return records


def _upsert_items(conn: sqlite3.Connection, records: List[Dict[str, Any]]) -> Tuple[int, int]:
    inserted = updated = 0
    if records:
        _update_catalog(conn, records)

    # Remove items from the DB that no longer exist on disk so stale 'reserved'
    # or 'consumed' rows don't inflate stock counts after files are deleted.
    scanned_ids = {r["instance_id"] for r in records}
    if scanned_ids:
        placeholders = ",".join("?" * len(scanned_ids))
        deleted = conn.execute(
            f"DELETE FROM inventory_items WHERE instance_id NOT IN ({placeholders})",
            list(scanned_ids),
        ).rowcount
    else:
        deleted = conn.execute("DELETE FROM inventory_items").rowcount
    if deleted:
        print(f"  ↳ Removed {deleted} stale item(s) no longer on disk.")

    for r in records:
        existing = conn.execute(
            "SELECT status FROM inventory_items WHERE instance_id = ?",
            (r["instance_id"],),
        ).fetchone()

        if existing:
            conn.execute("""
                UPDATE inventory_items SET
                    instance_number = ?, model_number = ?, component_type = ?,
                    product_name = ?, material = ?, color = ?, finish = ?,
                    nr_fuses = ?, created_date = ?, last_updated = ?
                WHERE instance_id = ?
            """, (
                r["instance_number"], r["model_number"], r["component_type"],
                r["product_name"], r["material"], r["color"], r["finish"],
                r.get("nr_fuses"), r["created_date"], r["last_updated"], r["instance_id"],
            ))
            updated += 1
        else:
            conn.execute("""
                INSERT INTO inventory_items (
                    instance_id, instance_number, model_number, component_type,
                    product_name, material, color, finish, nr_fuses,
                    created_date, status, last_updated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                r["instance_id"], r["instance_number"], r["model_number"],
                r["component_type"], r["product_name"], r["material"],
                r["color"], r["finish"], r.get("nr_fuses"), r["created_date"],
                r["status"], r["last_updated"],
            ))
            inserted += 1

    conn.commit()
    return inserted, updated


def _backfill_consumed_subassemblies(conn: sqlite3.Connection) -> int:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    updated = 0

    orders = conn.execute(
        "SELECT order_id, status, assembly_progress FROM configuration_orders "
        "WHERE status IN ('step2_done', 'assembled') AND assembly_progress IS NOT NULL"
    ).fetchall()

    for order in orders:
        try:
            progress = json.loads(order["assembly_progress"])
        except (TypeError, json.JSONDecodeError):
            continue

        hwp_id = progress.get("housing_with_pcb_id")
        if hwp_id:
            cur = conn.execute(
                "UPDATE inventory_items SET status = 'consumed', last_updated = ? "
                "WHERE instance_id = ? AND status != 'consumed'",
                (now, hwp_id),
            )
            updated += cur.rowcount

        if order["status"] == "assembled":
            pwf_id = progress.get("pcb_with_fuse_id")
            if pwf_id:
                cur = conn.execute(
                    "UPDATE inventory_items SET status = 'consumed', last_updated = ? "
                    "WHERE instance_id = ? AND status != 'consumed'",
                    (now, pwf_id),
                )
                updated += cur.rowcount

    if updated:
        conn.commit()

    return updated


def _rebuild_stock(conn: sqlite3.Connection) -> None:
    """
    Rebuild inventory_stock from inventory_items, then apply V4 model-type reservations.

    V4 extension: after the standard upsert, adjust qty_available and qty_reserved
    to reflect pending model_type_reservations (no specific instances are marked
    'reserved' in inventory_items under the V4 flow).
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    _backfill_consumed_subassemblies(conn)

    # Step 1: Zero existing rows
    conn.execute(f"""
        UPDATE inventory_stock
        SET qty_available = 0, qty_reserved = 0, qty_consumed = 0,
            qty_total = 0, last_updated = '{now}'
    """)

    # Step 2: Upsert from inventory_items
    conn.execute(f"""
        INSERT INTO inventory_stock (
            model_number, component_type, product_name,
            material, color, finish, nr_fuses,
            qty_available, qty_reserved, qty_consumed, qty_total,
            last_updated
        )
        SELECT
            model_number, component_type, MAX(product_name),
            MAX(material), MAX(color), MAX(finish), MAX(nr_fuses),
            SUM(CASE WHEN status = 'available' THEN 1 ELSE 0 END),
            SUM(CASE WHEN status = 'reserved'  THEN 1 ELSE 0 END),
            SUM(CASE WHEN status = 'consumed'  THEN 1 ELSE 0 END),
            COUNT(*),
            '{now}'
        FROM inventory_items
        GROUP BY model_number, component_type
        ON CONFLICT(model_number) DO UPDATE SET
            component_type = excluded.component_type,
            product_name   = excluded.product_name,
            material       = excluded.material,
            color          = excluded.color,
            finish         = excluded.finish,
            nr_fuses       = excluded.nr_fuses,
            qty_available  = excluded.qty_available,
            qty_reserved   = excluded.qty_reserved,
            qty_consumed   = excluded.qty_consumed,
            qty_total      = excluded.qty_total,
            last_updated   = excluded.last_updated
    """)

    # Step 3 (V4): Subtract pending model-type reservations from qty_available.
    # These reservations are NOT reflected in inventory_items, so we adjust here.
    try:
        pending = conn.execute("""
            SELECT model_number, COUNT(*) AS cnt
            FROM model_type_reservations
            WHERE status = 'pending'
            GROUP BY model_number
        """).fetchall()

        for row in pending:
            conn.execute("""
                UPDATE inventory_stock
                SET qty_reserved  = qty_reserved  + ?,
                    qty_available = MAX(0, qty_available - ?),
                    last_updated  = ?
                WHERE model_number = ?
            """, (row["cnt"], row["cnt"], now, row["model_number"]))
    except sqlite3.OperationalError:
        pass  # model_type_reservations table not yet created (first call before migration)

    conn.commit()


def _seed_stock_from_catalog(conn: sqlite3.Connection) -> int:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    catalog_rows = conn.execute(
        "SELECT model_number, component_type, product_name FROM model_catalog"
    ).fetchall()

    seeded = 0
    for row in catalog_rows:
        existing = conn.execute(
            "SELECT 1 FROM inventory_stock WHERE model_number = ?",
            (row["model_number"],),
        ).fetchone()
        if not existing:
            conn.execute("""
                INSERT INTO inventory_stock (
                    model_number, component_type, product_name,
                    material, color, finish,
                    qty_available, qty_reserved, qty_consumed, qty_total,
                    last_updated
                ) VALUES (?, ?, ?, NULL, NULL, NULL, 0, 0, 0, 0, ?)
            """, (row["model_number"], row["component_type"], row["product_name"], now))
            seeded += 1

    conn.commit()
    return seeded


def _get_model_number_template(type_doc_dir: str, type_doc_prefix: str, base_path: Path) -> Optional[str]:
    doc_file = base_path / type_doc_dir / f"{type_doc_prefix}-Type-Documentation.json"
    if not doc_file.exists():
        return None
    with open(doc_file, encoding="utf-8") as f:
        doc = json.load(f)
    for elem in doc.get("submodelElements", []):
        if elem.get("idShort") == "Model_Number_Configuration":
            for child in elem.get("value", []):
                if child.get("idShort") == "Template":
                    return child.get("value")
    return None


# =============================================================================
# Public API
# =============================================================================

def sync(db_path: str, base_path: Path) -> None:
    print(f"\n=== Syncing inventory to {db_path} ===\n")
    conn = _get_connection(db_path)
    _create_tables(conn)
    records = _collect_instances(base_path)
    print(f"  Found {len(records)} instance(s) across all component types.\n")
    inserted, updated = _upsert_items(conn, records)
    seeded = _seed_stock_from_catalog(conn)
    _rebuild_stock(conn)
    print(f"  ✓ Items inserted : {inserted}")
    print(f"  ✓ Items updated  : {updated}")
    if seeded:
        print(f"  ✓ New model numbers seeded from catalog: {seeded}")
    print(f"  ✓ Stock table rebuilt.\n")
    conn.close()
    print_status(db_path)


def print_status(db_path: str) -> None:
    conn = _get_connection(db_path)
    _create_tables(conn)
    rows = conn.execute("""
        SELECT model_number, component_type, material, color, finish,
               qty_available, qty_reserved, qty_consumed, qty_total
        FROM inventory_stock
        ORDER BY component_type, model_number
    """).fetchall()
    conn.close()

    if not rows:
        print("No inventory records found. Run --sync first.")
        return

    print("\n" + "=" * 100)
    print(f"  INVENTORY STOCK LEVELS — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 100)
    print(f"  {'Model Number':<35} {'Type':<16} {'Material':<12} {'Color':<10} {'Avail':>6} {'Res':>5} {'Used':>5} {'Total':>6}")
    print("-" * 100)
    current_type = None
    for row in rows:
        if row["component_type"] != current_type:
            current_type = row["component_type"]
            print(f"\n  [{current_type}]")
        print(
            f"  {row['model_number']:<35}"
            f" {row['component_type']:<16}"
            f" {(row['material'] or ''):<12}"
            f" {(row['color'] or ''):<10}"
            f" {row['qty_available']:>6}"
            f" {row['qty_reserved']:>5}"
            f" {row['qty_consumed']:>5}"
            f" {row['qty_total']:>6}"
        )
    print("\n" + "=" * 100)


def reset_db(db_path: str, base_path: Path) -> None:
    """Wipe all orders, reservations, and inventory data, then re-sync from JSON files.

    Intended for development resets when instance JSON files have been deleted.
    """
    print(f"\n=== Resetting database at {db_path} ===\n")
    conn = _get_connection(db_path)
    _create_tables(conn)
    conn.executescript("""
        DELETE FROM model_type_reservations;
        DELETE FROM configuration_orders;
        DELETE FROM inventory_items;
        DELETE FROM inventory_stock;
    """)
    conn.commit()
    conn.close()
    print("  ✓ Orders cleared.")
    print("  ✓ Reservations cleared.")
    print("  ✓ Inventory items cleared.")
    print("  ✓ Stock cleared.\n")
    sync(db_path, base_path)


def main():
    parser = argparse.ArgumentParser(description="Inventory Database Manager (V4)")
    parser.add_argument("--sync",   action="store_true", help="Scan JSON files and sync to DB")
    parser.add_argument("--status", action="store_true", help="Print current stock levels")
    parser.add_argument("--reset",  action="store_true", help="Wipe all orders/reservations/inventory and re-sync (dev use)")
    parser.add_argument("--db",     default=DEFAULT_DB_FILE, help=f"SQLite DB file (default: {DEFAULT_DB_FILE})")
    args = parser.parse_args()

    if args.reset:
        reset_db(args.db, AAS_FILES_BASE)
    elif args.sync:
        sync(args.db, AAS_FILES_BASE)
    elif args.status:
        print_status(args.db)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
