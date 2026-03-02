"""
Inventory Management System for Telefon Configurator v3

Manages component inventory in a SQLite database. Tracks quantities of each
component variant and prevents orders that exceed available stock.
"""

import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass


@dataclass
class ComponentInventory:
    """Represents a single component type in inventory."""
    component_id: str
    component_name: str
    variant_spec: str  # e.g., "Material: PLA-31212, Color: Red, Finish: Glossy"
    quantity: int
    last_updated: str
    notes: str = ""


class InventoryDatabase:
    """SQLite-based inventory management for Telefon components."""

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize the inventory database.

        Args:
            db_path: Path to SQLite database file. If None, uses 'inventory.db'
                     in the current directory.
        """
        if db_path is None:
            db_path = str(Path.cwd() / "inventory.db")
        
        self.db_path = db_path
        self.conn = None
        self._init_database()

    def _init_database(self):
        """Initialize the database connection and create tables if needed."""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row  # Access columns by name
        cursor = self.conn.cursor()

        # Create main inventory table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS component_inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                component_id TEXT NOT NULL,
                component_name TEXT NOT NULL,
                variant_spec TEXT NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 0,
                last_updated TEXT NOT NULL,
                notes TEXT DEFAULT '',
                UNIQUE(component_id, variant_spec)
            )
        """)

        # Create inventory transaction log (for audit trail)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS inventory_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                component_id TEXT NOT NULL,
                component_name TEXT NOT NULL,
                variant_spec TEXT NOT NULL,
                quantity_change INTEGER NOT NULL,
                previous_quantity INTEGER NOT NULL,
                new_quantity INTEGER NOT NULL,
                transaction_type TEXT NOT NULL,
                notes TEXT DEFAULT ''
            )
        """)

        # Create component options table (for validation)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS component_options (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                component_type TEXT NOT NULL,
                option_type TEXT NOT NULL,
                option_value TEXT NOT NULL,
                UNIQUE(component_type, option_type, option_value)
            )
        """)

        self.conn.commit()

    def add_component_inventory(
        self,
        component_id: str,
        component_name: str,
        variant_spec: str,
        quantity: int,
        notes: str = ""
    ) -> bool:
        """
        Add a new component variant to inventory.

        Args:
            component_id: Unique component identifier (e.g., 'Bottom_Cover')
            component_name: Human-readable component name
            variant_spec: Specification string (e.g., 'Material: PLA-31212, Color: Red')
            quantity: Initial quantity in stock
            notes: Optional notes about this inventory item

        Returns:
            True if successful, False if already exists
        """
        cursor = self.conn.cursor()
        timestamp = datetime.now().isoformat()

        try:
            cursor.execute("""
                INSERT INTO component_inventory 
                (component_id, component_name, variant_spec, quantity, last_updated, notes)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (component_id, component_name, variant_spec, quantity, timestamp, notes))
            
            self.conn.commit()
            
            # Log this transaction
            self._log_transaction(
                component_id, component_name, variant_spec, quantity,
                0, quantity, "INITIAL_STOCK", notes
            )
            return True
        except sqlite3.IntegrityError:
            print(f"Component variant already exists: {component_id} - {variant_spec}")
            return False

    def update_inventory(
        self,
        component_id: str,
        variant_spec: str,
        quantity_change: int,
        notes: str = ""
    ) -> Tuple[bool, int]:
        """
        Update inventory by adding/removing quantities.

        Args:
            component_id: Component identifier
            variant_spec: Variant specification string
            quantity_change: Positive or negative quantity change
            notes: Optional notes about the transaction

        Returns:
            Tuple of (success: bool, new_quantity: int)
        """
        cursor = self.conn.cursor()

        # Get current quantity
        cursor.execute("""
            SELECT quantity FROM component_inventory
            WHERE component_id = ? AND variant_spec = ?
        """, (component_id, variant_spec))
        
        row = cursor.fetchone()
        if not row:
            return False, 0

        previous_quantity = row[0]
        new_quantity = previous_quantity + quantity_change

        if new_quantity < 0:
            print(f"Error: Cannot reduce {component_id} quantity below 0 "
                  f"(current: {previous_quantity}, change: {quantity_change})")
            return False, previous_quantity

        timestamp = datetime.now().isoformat()

        cursor.execute("""
            UPDATE component_inventory
            SET quantity = ?, last_updated = ?
            WHERE component_id = ? AND variant_spec = ?
        """, (new_quantity, timestamp, component_id, variant_spec))

        self.conn.commit()

        # Log this transaction
        transaction_type = "CONSUMPTION" if quantity_change < 0 else "RESTOCK"
        self._log_transaction(
            component_id, "", variant_spec, quantity_change,
            previous_quantity, new_quantity, transaction_type, notes
        )

        return True, new_quantity

    def get_inventory(self, component_id: str, variant_spec: str) -> Optional[ComponentInventory]:
        """
        Get current inventory for a specific component variant.

        Args:
            component_id: Component identifier
            variant_spec: Variant specification string

        Returns:
            ComponentInventory object or None if not found
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT component_id, component_name, variant_spec, quantity, last_updated, notes
            FROM component_inventory
            WHERE component_id = ? AND variant_spec = ?
        """, (component_id, variant_spec))
        
        row = cursor.fetchone()
        if not row:
            return None

        return ComponentInventory(
            component_id=row[0],
            component_name=row[1],
            variant_spec=row[2],
            quantity=row[3],
            last_updated=row[4],
            notes=row[5]
        )

    def get_all_inventory_by_component(self, component_id: str) -> List[ComponentInventory]:
        """
        Get all inventory items for a specific component type.

        Returns:
            List of ComponentInventory objects for this component type
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT component_id, component_name, variant_spec, quantity, last_updated, notes
            FROM component_inventory
            WHERE component_id = ?
            ORDER BY variant_spec
        """, (component_id,))
        
        return [ComponentInventory(
            component_id=row[0],
            component_name=row[1],
            variant_spec=row[2],
            quantity=row[3],
            last_updated=row[4],
            notes=row[5]
        ) for row in cursor.fetchall()]

    def get_all_inventory(self) -> List[ComponentInventory]:
        """Get all inventory items across all components."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT component_id, component_name, variant_spec, quantity, last_updated, notes
            FROM component_inventory
            ORDER BY component_id, variant_spec
        """)
        
        return [ComponentInventory(
            component_id=row[0],
            component_name=row[1],
            variant_spec=row[2],
            quantity=row[3],
            last_updated=row[4],
            notes=row[5]
        ) for row in cursor.fetchall()]

    def check_availability(
        self,
        component_id: str,
        variant_spec: str,
        required_quantity: int = 1
    ) -> Tuple[bool, int]:
        """
        Check if required quantity is available in inventory.

        Args:
            component_id: Component identifier
            variant_spec: Variant specification
            required_quantity: How many units needed

        Returns:
            Tuple of (available: bool, current_quantity: int)
        """
        inventory = self.get_inventory(component_id, variant_spec)
        if not inventory:
            return False, 0
        
        return inventory.quantity >= required_quantity, inventory.quantity

    def get_low_stock_items(self, threshold: int = 5) -> List[ComponentInventory]:
        """
        Get all items with quantity below threshold.

        Args:
            threshold: Minimum quantity level

        Returns:
            List of low-stock ComponentInventory items
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT component_id, component_name, variant_spec, quantity, last_updated, notes
            FROM component_inventory
            WHERE quantity < ?
            ORDER BY quantity ASC, component_id
        """, (threshold,))
        
        return [ComponentInventory(
            component_id=row[0],
            component_name=row[1],
            variant_spec=row[2],
            quantity=row[3],
            last_updated=row[4],
            notes=row[5]
        ) for row in cursor.fetchall()]

    def add_component_option(
        self,
        component_type: str,
        option_type: str,
        option_value: str
    ) -> bool:
        """
        Register a valid component option for validation purposes.

        Args:
            component_type: Component type (e.g., 'Bottom_Cover')
            option_type: Type of option (e.g., 'Material', 'Color', 'Finish')
            option_value: Specific value (e.g., 'PLA-31212', 'Red')

        Returns:
            True if added, False if already exists
        """
        cursor = self.conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO component_options (component_type, option_type, option_value)
                VALUES (?, ?, ?)
            """, (component_type, option_type, option_value))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def get_available_options(
        self,
        component_type: str,
        option_type: str
    ) -> List[str]:
        """
        Get available options for a component type and option type.

        Args:
            component_type: Component type
            option_type: Option type (Material, Color, Finish, etc.)

        Returns:
            List of available option values
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT DISTINCT option_value FROM component_options
            WHERE component_type = ? AND option_type = ?
            ORDER BY option_value
        """, (component_type, option_type))
        
        return [row[0] for row in cursor.fetchall()]

    def _log_transaction(
        self,
        component_id: str,
        component_name: str,
        variant_spec: str,
        quantity_change: int,
        previous_quantity: int,
        new_quantity: int,
        transaction_type: str,
        notes: str = ""
    ):
        """
        Log inventory transaction for audit trail.

        Args:
            component_id: Component identifier
            component_name: Component name
            variant_spec: Variant specification
            quantity_change: Amount changed
            previous_quantity: Quantity before change
            new_quantity: Quantity after change
            transaction_type: Type of transaction (INITIAL_STOCK, CONSUMPTION, RESTOCK, etc.)
            notes: Optional transaction notes
        """
        cursor = self.conn.cursor()
        timestamp = datetime.now().isoformat()

        cursor.execute("""
            INSERT INTO inventory_log
            (timestamp, component_id, component_name, variant_spec, quantity_change,
             previous_quantity, new_quantity, transaction_type, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (timestamp, component_id, component_name, variant_spec, quantity_change,
              previous_quantity, new_quantity, transaction_type, notes))
        
        self.conn.commit()

    def get_transaction_history(
        self,
        component_id: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict]:
        """
        Get transaction history from the audit log.

        Args:
            component_id: Filter by component (None for all)
            limit: Maximum number of records to return

        Returns:
            List of transaction records
        """
        cursor = self.conn.cursor()
        
        if component_id:
            cursor.execute("""
                SELECT * FROM inventory_log
                WHERE component_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (component_id, limit))
        else:
            cursor.execute("""
                SELECT * FROM inventory_log
                ORDER BY timestamp DESC
                LIMIT ?
            """, (limit,))
        
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def print_inventory_summary(self):
        """Print a formatted summary of current inventory."""
        inventory = self.get_all_inventory()
        
        if not inventory:
            print("\n📦 Inventory Summary: Empty\n")
            return

        print("\n" + "="*80)
        print("📦 INVENTORY SUMMARY")
        print("="*80)

        current_component = None
        for item in inventory:
            if item.component_id != current_component:
                current_component = item.component_id
                print(f"\n{current_component}:")
            
            status = "✓" if item.quantity > 0 else "⚠"
            print(f"  {status} {item.variant_spec:<50} | Qty: {item.quantity:>4}")
        
        print("\n" + "="*80 + "\n")

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()

    def __del__(self):
        """Ensure database is closed on garbage collection."""
        self.close()


# ============================================================================
# CLI utility functions
# ============================================================================

def initialize_sample_inventory(db: InventoryDatabase):
    """Initialize database with sample component inventory."""
    print("\n🔧 Initializing sample inventory...\n")

    # Sample inventory data based on configurator_v2.py components
    samples = [
        # Bottom Cover variants
        ("Bottom_Cover", "Bottom Cover", "Material: PLA-31212, Color: Red, Finish: Glossy", 50, "Initial stock"),
        ("Bottom_Cover", "Bottom Cover", "Material: PLA-31212, Color: Blue, Finish: Glossy", 35, "Initial stock"),
        ("Bottom_Cover", "Bottom Cover", "Material: ABS-5500, Color: Black, Finish: Matte", 25, "Initial stock"),
        ("Bottom_Cover", "Bottom Cover", "Material: PETG-7700, Color: White, Finish: Textured", 15, "Initial stock"),
        
        # Top Cover variants
        ("Top_Cover", "Top Cover", "Material: PLA-31212, Color: Red, Finish: Glossy", 50, "Initial stock"),
        ("Top_Cover", "Top Cover", "Material: PLA-31212, Color: Blue, Finish: Glossy", 40, "Initial stock"),
        ("Top_Cover", "Top Cover", "Material: ABS-5500, Color: Black, Finish: Matte", 30, "Initial stock"),
        
        # PCB
        ("PCB", "PCB Standard", "Standard Configuration", 100, "Initial stock"),
        
        # Fuses
        ("Fuse", "Fuse 1A", "1A Rating", 200, "Initial stock"),
        ("Fuse", "Fuse 2A", "2A Rating", 150, "Initial stock"),
        ("Fuse", "Fuse 3A", "3A Rating", 100, "Initial stock"),
    ]

    for component_id, component_name, variant_spec, qty, notes in samples:
        success = db.add_component_inventory(component_id, component_name, variant_spec, qty, notes)
        status = "✓" if success else "→"
        print(f"  {status} {component_id}: {variant_spec}")

    # Register available options
    options = [
        ("Bottom_Cover", "Material", "PLA-31212"),
        ("Bottom_Cover", "Material", "ABS-5500"),
        ("Bottom_Cover", "Material", "PETG-7700"),
        ("Bottom_Cover", "Color", "Red"),
        ("Bottom_Cover", "Color", "Blue"),
        ("Bottom_Cover", "Color", "Black"),
        ("Bottom_Cover", "Color", "White"),
        ("Bottom_Cover", "Color", "Green"),
        ("Bottom_Cover", "Finish", "Glossy"),
        ("Bottom_Cover", "Finish", "Matte"),
        ("Bottom_Cover", "Finish", "Textured"),
        
        ("Top_Cover", "Material", "PLA-31212"),
        ("Top_Cover", "Material", "ABS-5500"),
        ("Top_Cover", "Material", "PETG-7700"),
        ("Top_Cover", "Color", "Red"),
        ("Top_Cover", "Color", "Blue"),
        ("Top_Cover", "Color", "Black"),
        ("Top_Cover", "Color", "White"),
        ("Top_Cover", "Color", "Green"),
        ("Top_Cover", "Finish", "Glossy"),
        ("Top_Cover", "Finish", "Matte"),
        ("Top_Cover", "Finish", "Textured"),
    ]

    for component_type, option_type, option_value in options:
        db.add_component_option(component_type, option_type, option_value)

    print("\n✓ Sample inventory initialized\n")


def print_inventory(db: InventoryDatabase):
    """Print current inventory to console."""
    db.print_inventory_summary()


def check_stock(db: InventoryDatabase, component_id: str):
    """Check stock for a specific component type."""
    items = db.get_all_inventory_by_component(component_id)
    if not items:
        print(f"\n❌ No inventory found for component: {component_id}\n")
        return
    
    print(f"\n📦 Stock for {component_id}:")
    for item in items:
        status = "✓" if item.quantity > 0 else "⚠"
        print(f"  {status} {item.variant_spec}: {item.quantity} units")
    print()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Inventory Management System")
    parser.add_argument("--init-sample", action="store_true", help="Initialize with sample data")
    parser.add_argument("--print", action="store_true", help="Print inventory summary")
    parser.add_argument("--check", type=str, help="Check stock for component")
    parser.add_argument("--db", type=str, default="inventory.db", help="Database file path")
    
    args = parser.parse_args()

    db = InventoryDatabase(args.db)

    if args.init_sample:
        initialize_sample_inventory(db)
    elif args.print:
        print_inventory(db)
    elif args.check:
        check_stock(db, args.check)
    else:
        parser.print_help()

    db.close()
