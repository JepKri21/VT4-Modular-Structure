"""
Inventory Database Manager

Reads all generated component instance JSON files and syncs them to a SQL
database, grouped by Model_Number so stock levels are immediately visible.

Schema
------
inventory_items   – one row per physical instance (the actual unit)
inventory_stock   – one row per model number (aggregated stock count)

Usage
-----
  python inventory_db.py --sync          # scan JSON files and sync to DB
  python inventory_db.py --status        # print current stock table
  python inventory_db.py --db mydb.db   # use a specific DB file (default: inventory.db)

The database is SQLite by default. To switch to PostgreSQL or MySQL, replace
the `_get_connection()` method — no other changes are needed.
"""

import json
import re
import sqlite3
import argparse
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# =============================================================================
# Configuration
# =============================================================================

# Directories that contain instance submodel files, relative to this script
INSTANCE_SUBMODEL_DIRS = [
    "JSON_Submodels/Product_Submodels_JSON/Instances/Component_Instance_Submodels",
    "JSON_Submodels/Product_Submodels_JSON/Instances/Sub_Assembly_Instance_Submodels",
    "JSON_Submodels/Product_Submodels_JSON/Instances/Final_Product_Instance_Submodels",
]

# Maps instance_registry.json product_type keys → (type_doc_dir, type_doc_file_prefix)
# Used to derive model numbers from registry configurations when no instance files exist.
REGISTRY_KEY_TO_TYPE_DOC: Dict[str, tuple] = {
    "Bottom_Cover": (
        "JSON_Submodels/Product_Submodels_JSON/Types/Component_Type_Submodels",
        "Product-Component-AAU-Bottom_Cover",
    ),
    "Top_Cover": (
        "JSON_Submodels/Product_Submodels_JSON/Types/Component_Type_Submodels",
        "Product-Component-AAU-Top_Cover",
    ),
    "PCB": (
        "JSON_Submodels/Product_Submodels_JSON/Types/Component_Type_Submodels",
        "Product-Component-AAU-PCB",
    ),
    "Fuse": (
        "JSON_Submodels/Product_Submodels_JSON/Types/Component_Type_Submodels",
        "Product-Component-AAU-Fuse",
    ),
    "PCB_With_Fuse": (
        "JSON_Submodels/Product_Submodels_JSON/Types/Sub_Assembly_Type_Submodels",
        "Product-Sub_Assembly-AAU-PCB_With_Fuse",
    ),
    "Housing_With_PCB": (
        "JSON_Submodels/Product_Submodels_JSON/Types/Sub_Assembly_Type_Submodels",
        "Product-Sub_Assembly-AAU-Housing_With_PCB",
    ),
    "Telefon_Pro_Max": (
        "JSON_Submodels/Product_Submodels_JSON/Types/Final_Product_Type_Submodels",
        "Product-Final_Product-Telefon-Telefon_Pro_Max",
    ),
}

DEFAULT_DB_FILE = "inventory.db"


# =============================================================================
# Database setup
# =============================================================================

def _get_connection(db_path: str) -> sqlite3.Connection:
    """
    Return a database connection.
    Swap this function to connect to PostgreSQL / MySQL instead of SQLite.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row       # allows column access by name
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _create_tables(conn: sqlite3.Connection) -> None:
    """Create the inventory tables if they do not already exist."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS inventory_items (
            -- One row per physical component instance
            instance_id         TEXT PRIMARY KEY,   -- AAS id from the shell
            instance_number     TEXT NOT NULL,       -- e.g. "001"
            model_number        TEXT NOT NULL,       -- e.g. "BC-PLA-31212-Red"
            component_type      TEXT NOT NULL,       -- e.g. "Bottom_Cover"
            product_name        TEXT,
            material            TEXT,
            color               TEXT,
            finish              TEXT,
            created_date        TEXT,
            status              TEXT NOT NULL DEFAULT 'available',
            -- 'available'  : in stock, not reserved
            -- 'reserved'   : allocated to a production order
            -- 'consumed'   : used in a finished product
            last_updated        TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS inventory_stock (
            -- One row per model number — aggregated view of stock
            model_number        TEXT PRIMARY KEY,
            component_type      TEXT NOT NULL,
            product_name        TEXT,
            material            TEXT,
            color               TEXT,
            finish              TEXT,
            qty_available       INTEGER NOT NULL DEFAULT 0,
            qty_reserved        INTEGER NOT NULL DEFAULT 0,
            qty_consumed        INTEGER NOT NULL DEFAULT 0,
            qty_total           INTEGER NOT NULL DEFAULT 0,
            last_updated        TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS model_catalog (
            -- Permanent record of every model number ever seen.
            -- Never cleared — survives instance and registry resets.
            model_number        TEXT PRIMARY KEY,
            component_type      TEXT NOT NULL,
            product_name        TEXT,
            first_seen          TEXT NOT NULL,
            last_seen           TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS configuration_orders (
            -- Tracks product configurations before assembly
            order_id            TEXT PRIMARY KEY,
            product_type        TEXT NOT NULL,
            configuration       TEXT NOT NULL,           -- JSON: {material, color, finish, fuse_count}
            model_numbers_needed TEXT NOT NULL,          -- JSON: {component_type: model_number}
            reserved_instances  TEXT,                    -- JSON: {component_type: {instance_id, instance_number, model_number}} — set during config, used during assembly
            status              TEXT NOT NULL DEFAULT 'pending',  -- pending|step1_done|step2_done|assembled|cancelled
            assembly_progress   TEXT,                    -- JSON: intermediate sub-assembly IDs/numbers per step
            created_date        TEXT NOT NULL,
            assembled_date      TEXT,
            notes               TEXT
        );

        CREATE TABLE IF NOT EXISTS assembly_log (
            -- Tracks which instances were assembled into which products
            assembly_id         TEXT PRIMARY KEY,
            product_instance_id TEXT NOT NULL,
            component_type      TEXT NOT NULL,
            component_instance_id TEXT NOT NULL,
            model_number        TEXT NOT NULL,
            assembly_date       TEXT NOT NULL
        );
    """)
    # Migration: add assembly_progress column to existing databases that pre-date this column
    try:
        conn.execute("ALTER TABLE configuration_orders ADD COLUMN assembly_progress TEXT")
    except sqlite3.OperationalError:
        pass  # column already exists
    conn.commit()


# =============================================================================
# JSON parsing helpers
# =============================================================================

def _get_prop(elements: List[Dict], id_short: str) -> Optional[str]:
    """Return the value of a flat submodelElement by idShort."""
    for elem in elements:
        if elem.get("idShort") == id_short:
            return elem.get("value")
    return None


def _get_list_prop(elements: List[Dict], list_id_short: str, prop_id_short: str) -> Optional[str]:
    """
    Return a property value from inside a SubmodelElementList.
    Used to read Material / Color / Finish from List_Of_Properties.
    """
    for elem in elements:
        if elem.get("idShort") == list_id_short:
            for item in elem.get("value", []):
                if item.get("idShort") == prop_id_short:
                    return item.get("value")
    return None


def _update_catalog(conn: sqlite3.Connection, records: List[Dict[str, Any]]) -> None:
    """
    Upsert every model number from records into the permanent model_catalog.
    First-seen date is preserved; last-seen is updated on every sync.
    """
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


def _parse_component_type(filename: str):
    """
    Infer the component type from a Documentation filename.
    e.g. "Product-Component-AAU-Bottom_Cover-001-Documentation.json"  -> "Bottom_Cover"
         "Product-Sub_Assembly-AAU-PCB_With_Fuse-001-Documentation.json" -> "PCB_With_Fuse"
         "Product-Final_Product-Telefon-Telefon_Pro_Max-001-Documentation.json" -> "Telefon_Pro_Max"
    """
    name = filename
    for prefix in (
        "Product-Component-AAU-",
        "Product-Sub_Assembly-AAU-",
        "Product-Final_Product-Telefon-",
    ):
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    # Remove "-NNN-Documentation.json"
    parts = name.rsplit("-", 2)
    return parts[0] if len(parts) >= 3 else "Unknown"


def _parse_instance_number(filename: str) -> str:
    """
    Extract instance number from filename.
    e.g. "Product-Component-AAU-Bottom_Cover-001-Documentation.json" -> "001"
    """
    parts = filename.rsplit("-", 2)
    return parts[1] if len(parts) >= 3 else "000"


def _build_instance_id(doc_submodel: Dict) -> str:
    """Derive an instance ID from the Documentation submodel's own 'id' field."""
    return doc_submodel.get("id", "")


# =============================================================================
# Core sync logic
# =============================================================================

def _collect_instances(base_path: Path) -> List[Dict[str, Any]]:
    """
    Scan all instance submodel directories for Documentation files and
    return a list of instance records ready to be inserted/updated in the DB.
    """
    records = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for rel_dir in INSTANCE_SUBMODEL_DIRS:
        submodel_dir = base_path / rel_dir
        if not submodel_dir.exists():
            print(f"  ⚠  Directory not found, skipping: {submodel_dir}")
            continue

        for doc_file in sorted(submodel_dir.glob("*-Documentation.json")):
            filename = doc_file.name

            # Load Documentation submodel
            with open(doc_file, encoding="utf-8") as f:
                doc = json.load(f)

            elements = doc.get("submodelElements", [])
            model_number  = _get_prop(elements, "Model_Number")
            instance_num  = _get_prop(elements, "Instance_Number")
            product_name  = _get_prop(elements, "Product_Name")
            created_date  = _get_prop(elements, "Created_Date")
            instance_id   = _build_instance_id(doc)
            component_type = _parse_component_type(filename)

            if not model_number:
                print(f"  ⚠  No Model_Number in {filename}, skipping.")
                continue

            # Load matching Properties submodel for Material / Color / Finish
            props_file = doc_file.with_name(
                filename.replace("-Documentation.json", "-Properties.json")
            )
            material = color = finish = None
            if props_file.exists():
                with open(props_file, encoding="utf-8") as f:
                    props = json.load(f)
                prop_elems = props.get("submodelElements", [])
                material = _get_list_prop(prop_elems, "List_Of_Properties", "Material")
                color    = _get_list_prop(prop_elems, "List_Of_Properties", "Color")
                finish   = _get_list_prop(prop_elems, "List_Of_Properties", "Finish")

            records.append({
                "instance_id":    instance_id,
                "instance_number": instance_num or _parse_instance_number(filename),
                "model_number":   model_number,
                "component_type": component_type,
                "product_name":   product_name,
                "material":       material,
                "color":          color,
                "finish":         finish,
                "created_date":   created_date,
                "status":         "available",
                "last_updated":   now,
            })

    return records


def _upsert_items(conn: sqlite3.Connection, records: List[Dict[str, Any]]) -> Tuple[int, int]:
    """
    Insert new inventory_items rows or update existing ones.
    Preserves the 'status' field for rows that already exist.
    Also keeps the permanent model_catalog up to date.
    Returns (inserted, updated) counts.
    """
    inserted = updated = 0
    if records:
        _update_catalog(conn, records)

    for r in records:
        existing = conn.execute(
            "SELECT status FROM inventory_items WHERE instance_id = ?",
            (r["instance_id"],),
        ).fetchone()

        if existing:
            # Keep the current status (don't reset reserved/consumed to available)
            conn.execute("""
                UPDATE inventory_items SET
                    instance_number = ?,
                    model_number    = ?,
                    component_type  = ?,
                    product_name    = ?,
                    material        = ?,
                    color           = ?,
                    finish          = ?,
                    created_date    = ?,
                    last_updated    = ?
                WHERE instance_id = ?
            """, (
                r["instance_number"], r["model_number"], r["component_type"],
                r["product_name"], r["material"], r["color"], r["finish"],
                r["created_date"], r["last_updated"], r["instance_id"],
            ))
            updated += 1
        else:
            conn.execute("""
                INSERT INTO inventory_items (
                    instance_id, instance_number, model_number, component_type,
                    product_name, material, color, finish,
                    created_date, status, last_updated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                r["instance_id"], r["instance_number"], r["model_number"],
                r["component_type"], r["product_name"], r["material"],
                r["color"], r["finish"], r["created_date"],
                r["status"], r["last_updated"],
            ))
            inserted += 1

    conn.commit()
    return inserted, updated


def _rebuild_stock(conn: sqlite3.Connection) -> None:
    """
    Rebuild the inventory_stock table from inventory_items.
    Called after every sync so stock counts are always up to date.

    Uses zero-out + UPSERT instead of DELETE + INSERT so that model numbers
    that have been seen before (but have no current instance files) remain in
    the table with qty=0 rather than disappearing entirely.
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Step 1: Zero out all quantities for existing rows (keep the rows)
    conn.execute(f"""
        UPDATE inventory_stock
        SET qty_available = 0,
            qty_reserved  = 0,
            qty_consumed  = 0,
            qty_total     = 0,
            last_updated  = '{now}'
    """)

    # Step 2: Upsert actual counts from inventory_items
    conn.execute(f"""
        INSERT INTO inventory_stock (
            model_number, component_type, product_name,
            material, color, finish,
            qty_available, qty_reserved, qty_consumed, qty_total,
            last_updated
        )
        SELECT
            model_number,
            component_type,
            MAX(product_name)   AS product_name,
            MAX(material)       AS material,
            MAX(color)          AS color,
            MAX(finish)         AS finish,
            SUM(CASE WHEN status = 'available' THEN 1 ELSE 0 END)  AS qty_available,
            SUM(CASE WHEN status = 'reserved'  THEN 1 ELSE 0 END)  AS qty_reserved,
            SUM(CASE WHEN status = 'consumed'  THEN 1 ELSE 0 END)  AS qty_consumed,
            COUNT(*)                                                 AS qty_total,
            '{now}'
        FROM inventory_items
        GROUP BY model_number, component_type
        ON CONFLICT(model_number) DO UPDATE SET
            component_type = excluded.component_type,
            product_name   = excluded.product_name,
            material       = excluded.material,
            color          = excluded.color,
            finish         = excluded.finish,
            qty_available  = excluded.qty_available,
            qty_reserved   = excluded.qty_reserved,
            qty_consumed   = excluded.qty_consumed,
            qty_total      = excluded.qty_total,
            last_updated   = excluded.last_updated
    """)
    conn.commit()


def _get_model_number_template(type_doc_dir: str, type_doc_prefix: str, base_path: Path) -> Optional[str]:
    """
    Load a Type-Documentation JSON and return the Model_Number template string,
    or None if the file or template is not found.
    """
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


def _seed_stock_from_catalog(conn: sqlite3.Connection) -> int:
    """
    Ensure every model number recorded in the permanent model_catalog has a
    row in inventory_stock.  Rows are inserted with qty=0 if they do not
    already exist — this survives instance resets and registry clears because
    the catalog lives only in the database and is never wiped.

    Returns the number of new rows seeded.
    """
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


# =============================================================================
# Public API
# =============================================================================

def sync(db_path: str, base_path: Path) -> None:
    """Scan JSON files and sync to the database."""
    print(f"\n=== Syncing inventory to {db_path} ===\n")

    conn = _get_connection(db_path)
    _create_tables(conn)

    records = _collect_instances(base_path)
    print(f"  Found {len(records)} instance(s) across all component types.\n")

    inserted, updated = _upsert_items(conn, records)

    # Seed stock from the permanent catalog so model numbers that were seen
    # in previous syncs remain visible (qty=0) even after instance/registry resets.
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
    """Print a formatted stock status table to the console."""
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


def update_status(db_path: str, instance_id: str, new_status: str) -> None:
    """
    Update the status of a single inventory item and rebuild stock counts.
    Valid statuses: 'available', 'reserved', 'consumed'
    """
    valid = {"available", "reserved", "consumed"}
    if new_status not in valid:
        raise ValueError(f"Invalid status '{new_status}'. Must be one of: {valid}")

    conn = _get_connection(db_path)
    _create_tables(conn)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn.execute(
        "UPDATE inventory_items SET status = ?, last_updated = ? WHERE instance_id = ?",
        (new_status, now, instance_id),
    )
    conn.commit()
    _rebuild_stock(conn)
    conn.close()
    print(f"  ✓ Updated {instance_id} → {new_status}")


# =============================================================================
# CLI entry point
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Inventory Database Manager")
    parser.add_argument("--sync",   action="store_true", help="Scan JSON files and sync to DB")
    parser.add_argument("--status", action="store_true", help="Print current stock levels")
    parser.add_argument("--db",     default=DEFAULT_DB_FILE, help=f"SQLite DB file (default: {DEFAULT_DB_FILE})")
    args = parser.parse_args()

    base_path = Path(__file__).parent

    if args.sync:
        sync(args.db, base_path)
    elif args.status:
        print_status(args.db)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
