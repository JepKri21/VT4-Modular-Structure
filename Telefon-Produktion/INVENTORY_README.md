# Telefon Configurator v3 - Inventory Management System

## Overview

Configurator v3 extends v2 with **SQL-based inventory tracking** for all component variants. The system:

- ✅ Tracks stock quantities for each component variant
- ✅ Validates configuration availability before creating instances
- ✅ Automatically deducts from inventory on successful creation
- ✅ Provides visibility into available options based on current stock
- ✅ Maintains audit trail of all inventory transactions
- ✅ Prevents orders that exceed available inventory

## Architecture

### Components

#### 1. **inventory_db.py** - Inventory Management Module

SQLite-based database manager with the following features:

```
Database Tables:
├── component_inventory      # Current stock levels
├── inventory_log           # Audit trail of all transactions
└── component_options       # Valid option values for validation
```

**Key Classes:**

- `InventoryDatabase` - Main database interface
  - `add_component_inventory()` - Register a component variant with initial stock
  - `update_inventory()` - Add/remove quantities (with audit logging)
  - `check_availability()` - Verify sufficient stock exists
  - `get_inventory()` - Retrieve current stock level
  - `get_all_inventory()` - List all inventory items
  - `get_low_stock_items()` - Find items below threshold
  - `get_transaction_history()` - Audit trail queries
  - `add_component_option()` - Register valid options
  - `get_available_options()` - Query valid options by type

**Data Classes:**

- `ComponentInventory` - Represents a single inventory item

#### 2. **configurator_v3.py** - Extended Configurator

Extends v2 functionality with inventory integration:

**New Methods:**

- `validate_configuration_availability()` - Check all components have stock
- `get_available_configurations()` - List options based on current inventory
- `print_available_options()` - Display available variants to user
- `_build_variant_spec()` - Create variant specification strings

**Modified Methods:**

- `_create_asset_instance()` - Now deducts from inventory on successful creation
- `generate_random_configuration()` - Only uses available inventory variants
- `create_telefon_instance()` - Added inventory validation step

## Getting Started

### 1. Initialize Sample Inventory

```bash
python configurator_v3.py --init-sample-inventory
```

This creates the database and populates it with sample data:
- Bottom Covers (4 variants)
- Top Covers (3 variants)
- PCBs (standard)
- Fuses (1A, 2A, 3A ratings)

### 2. View Current Inventory

```bash
python configurator_v3.py --print-inventory
```

Output example:
```
================================================================================
📦 INVENTORY SUMMARY
================================================================================

Bottom_Cover:
  ✓ Material: PLA-31212, Color: Red, Finish: Glossy      | Qty:   50
  ✓ Material: PLA-31212, Color: Blue, Finish: Glossy     | Qty:   35
  ✓ Material: ABS-5500, Color: Black, Finish: Matte      | Qty:   25
  ✓ Material: PETG-7700, Color: White, Finish: Textured  | Qty:   15

Top_Cover:
  ✓ Material: PLA-31212, Color: Red, Finish: Glossy      | Qty:   50
  ...
```

### 3. View Available Configurations

```bash
python configurator_v3.py --print-available
```

Shows only variants currently in stock and available for configuration.

### 4. Create Instance (Interactive Mode)

```bash
python configurator_v3.py --interactive
```

The system will:
1. Display available options
2. Prompt for configuration choices
3. Validate availability
4. Create instance and deduct from inventory

Example flow:
```
=== Telefon Configurator v3 — Interactive Mode ===

📋 AVAILABLE CONFIGURATION OPTIONS (Based on Current Inventory)

Bottom_Cover:
  ✓ Material: PLA-31212, Color: Red, Finish: Glossy     | Qty: 50
  ✓ Material: PLA-31212, Color: Blue, Finish: Glossy    | Qty: 35
  ...

Bottom Cover Configuration:
  Material [PLA-31212]: 
  Color [Red]: 
  Finish [Glossy]: 

🔍 Checking inventory availability...
  ✓ Bottom_Cover: 50 in stock
  ✓ Top_Cover: 50 in stock
  ✓ PCB: 100 in stock
  ✓ Fuse: 200 in stock

✓ Inventory available, proceeding...
  ✓ Inventory deducted: Bottom_Cover (...) → 49 remaining
  ...
✓ Successfully created Telefon instance: 001
```

### 5. Create from Configuration File

```bash
python configurator_v3.py --config my_config.json
```

Example `my_config.json`:
```json
{
  "bottom_cover_material": "PLA-31212",
  "bottom_cover_color": "Red",
  "bottom_cover_finish": "Glossy",
  "top_cover_material": "ABS-5500",
  "top_cover_color": "Black",
  "top_cover_finish": "Matte",
  "number_of_fuses": 2
}
```

### 6. Generate Random Instances

```bash
python configurator_v3.py --generate-random 5
```

Creates 5 random instances using only available inventory variants.

## Inventory Specification Format

Component variants are identified by specification strings:

```
"Material: PLA-31212, Color: Red, Finish: Glossy"
"Material: ABS-5500, Color: Black, Finish: Matte"
"1A Rating"
"Standard Configuration"
```

These specifications are:
- **Human-readable** - Easy to understand
- **Unique** - Identifies exact variant in inventory
- **Flexible** - Can include any property combinations

## Database Schema Details

### component_inventory Table

```sql
CREATE TABLE component_inventory (
    id INTEGER PRIMARY KEY,
    component_id TEXT NOT NULL,        -- e.g., "Bottom_Cover"
    component_name TEXT NOT NULL,      -- e.g., "Bottom Cover"
    variant_spec TEXT NOT NULL,        -- e.g., "Material: PLA-31212, Color: Red"
    quantity INTEGER NOT NULL,
    last_updated TEXT NOT NULL,        -- ISO format timestamp
    notes TEXT,
    UNIQUE(component_id, variant_spec)
);
```

### inventory_log Table

```sql
CREATE TABLE inventory_log (
    id INTEGER PRIMARY KEY,
    timestamp TEXT NOT NULL,
    component_id TEXT NOT NULL,
    component_name TEXT NOT NULL,
    variant_spec TEXT NOT NULL,
    quantity_change INTEGER NOT NULL,
    previous_quantity INTEGER NOT NULL,
    new_quantity INTEGER NOT NULL,
    transaction_type TEXT NOT NULL,    -- INITIAL_STOCK, CONSUMPTION, RESTOCK
    notes TEXT
);
```

### component_options Table

```sql
CREATE TABLE component_options (
    id INTEGER PRIMARY KEY,
    component_type TEXT NOT NULL,      -- e.g., "Bottom_Cover"
    option_type TEXT NOT NULL,         -- e.g., "Material", "Color"
    option_value TEXT NOT NULL,        -- e.g., "PLA-31212"
    UNIQUE(component_type, option_type, option_value)
);
```

## Advanced Usage

### Direct Python API

```python
from inventory_db import InventoryDatabase

# Initialize
db = InventoryDatabase("inventory.db")

# Add stock
db.add_component_inventory(
    "Bottom_Cover",
    "Bottom Cover",
    "Material: PLA-31212, Color: Red, Finish: Glossy",
    quantity=50,
    notes="Supplier: XYZ Company"
)

# Check availability
available, qty = db.check_availability(
    "Bottom_Cover",
    "Material: PLA-31212, Color: Red, Finish: Glossy",
    required_quantity=1
)

if available:
    print(f"In stock: {qty} units")
else:
    print("Out of stock")

# Update inventory
success, new_qty = db.update_inventory(
    "Bottom_Cover",
    "Material: PLA-31212, Color: Red, Finish: Glossy",
    quantity_change=-10,  # Reduce by 10
    notes="Used in production run"
)

# Check low stock
low_items = db.get_low_stock_items(threshold=10)
for item in low_items:
    print(f"LOW STOCK: {item.component_id} - {item.quantity}")

# View transaction history
history = db.get_transaction_history("Bottom_Cover", limit=20)
for transaction in history:
    print(f"{transaction['timestamp']}: {transaction['quantity_change']:+d} → {transaction['new_quantity']}")

db.close()
```

### With Configurator

```python
from configurator_v3 import TelefonConfiguratorV3

configurator = TelefonConfiguratorV3(".")

# Check what's available
available = configurator.get_available_configurations()
print(f"Available Bottom Covers: {len(available['Bottom_Cover'])}")

# Validate before creating
config = {
    "bottom_cover_material": "PLA-31212",
    "bottom_cover_color": "Red",
    "bottom_cover_finish": "Glossy",
    "top_cover_material": "ABS-5500",
    "top_cover_color": "Black",
    "top_cover_finish": "Matte",
    "number_of_fuses": 2
}

valid, messages = configurator.validate_configuration_availability(config)
if valid:
    configurator.create_telefon_instance(config)
else:
    print("Configuration not available:")
    for msg in messages:
        print(msg)
```

## Inventory Management Best Practices

### 1. Regular Inventory Checks

```bash
# Weekly summary
python configurator_v3.py --print-inventory

# Check specific component
python -c "
from inventory_db import InventoryDatabase
db = InventoryDatabase()
items = db.get_all_inventory_by_component('Bottom_Cover')
for item in items:
    print(f'{item.variant_spec}: {item.quantity}')
"
```

### 2. Monitor Low Stock

```python
db = InventoryDatabase()
low = db.get_low_stock_items(threshold=5)
if low:
    print("🚨 LOW STOCK ALERT:")
    for item in low:
        print(f"  {item.component_id}: {item.quantity} remaining")
```

### 3. Restock Operations

```python
db = InventoryDatabase()
success, new_qty = db.update_inventory(
    "Bottom_Cover",
    "Material: PLA-31212, Color: Red, Finish: Glossy",
    quantity_change=+100,
    notes="Restocked from supplier ABC on 2026-03-02"
)
print(f"New stock level: {new_qty}")
```

### 4. Audit Trail

```python
db = InventoryDatabase()
history = db.get_transaction_history("Bottom_Cover", limit=50)
for txn in history:
    print(f"{txn['timestamp']}: {txn['transaction_type']:15} {txn['quantity_change']:+4} ({txn['notes']})")
```

## Migration from v2 to v3

1. **Keep existing v2 code** - v3 is independent and doesn't modify v2
2. **Initialize inventory** - Use sample data or import your actual stock levels
3. **Run in parallel** - Both versions can coexist
4. **Gradual adoption** - Migrate to v3 once inventory is properly set up

## Troubleshooting

### Configuration not available?

```bash
# See what's in stock
python configurator_v3.py --print-available

# Check specific component quantities
python -c "
from inventory_db import InventoryDatabase
db = InventoryDatabase()
items = db.get_all_inventory_by_component('Bottom_Cover')
for item in items:
    print(f'{item.variant_spec}: {item.quantity}')
"
```

### Inventory out of sync?

Check the transaction log:

```python
from inventory_db import InventoryDatabase
db = InventoryDatabase()
history = db.get_transaction_history(limit=100)
for txn in history:
    print(f"{txn['timestamp']}: {txn['component_id']} {txn['transaction_type']} {txn['quantity_change']:+d}")
```

### Need to reset?

```bash
# Start fresh
rm inventory.db
python configurator_v3.py --init-sample-inventory
```

## Summary of Commands

```bash
# Initialization
python configurator_v3.py --init-sample-inventory   # Create & populate DB

# Viewing
python configurator_v3.py --print-inventory          # Full summary
python configurator_v3.py --print-available          # Based on stock

# Creating Instances
python configurator_v3.py --interactive              # Interactive mode
python configurator_v3.py --config config.json       # From file
python configurator_v3.py --generate-random 5        # Random instances

# Registry Management
python configurator_v3.py --reset-registry           # Clear instances
python configurator_v3.py --reset-registry --delete-instances  # Delete files
```
