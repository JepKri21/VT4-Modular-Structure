# Configurator v3 - Quick Start Guide

## What's New in v3

Configurator v3 adds **complete inventory management** to your telefon production system:

✅ **SQL Database** - SQLite inventory database with audit trail  
✅ **Stock Tracking** - Track exact quantities of each component variant  
✅ **Availability Checking** - Verify stock before creating instances  
✅ **Automatic Deduction** - Inventory updated when instances are created  
✅ **Smart Validation** - Only allow configurations using available components  
✅ **Transaction Logging** - Full audit trail of all inventory changes  

## 5-Minute Setup

### Step 1: Initialize Database

```bash
cd Telefon-Produktion
python configurator_v3.py --init-sample-inventory
```

This creates `inventory.db` with sample component stock.

### Step 2: View Inventory

```bash
python configurator_v3.py --print-inventory
```

**Sample Output:**
```
📦 INVENTORY SUMMARY
================================================================================

Bottom_Cover:
  ✓ Material: PLA-31212, Color: Red, Finish: Glossy      | Qty:   50
  ✓ Material: PLA-31212, Color: Blue, Finish: Glossy     | Qty:   35
  ...
```

### Step 3: Create an Instance

```bash
python configurator_v3.py --interactive
```

The system will:
1. Show available configuration options
2. Ask you to choose material, color, finish, fuses
3. Check inventory availability
4. Create the instance
5. Deduct from inventory

**Example:**
```
🔍 Checking inventory availability...

  ✓ Bottom_Cover: 50 in stock
  ✓ Top_Cover: 40 in stock
  ✓ PCB: 100 in stock
  ✓ Fuse: 200 x 2 needed in stock

✓ Inventory available, proceeding with instance creation...

  ✓ Inventory deducted: Bottom_Cover (...) → 49 remaining
  ✓ Inventory deducted: Top_Cover (...) → 39 remaining
  ✓ Created Telefon instance: 001
```

## Common Commands

### View Inventory
```bash
python configurator_v3.py --print-inventory
```

### See What's Available to Configure
```bash
python configurator_v3.py --print-available
```

### Create from JSON Config
```bash
python configurator_v3.py --config my_order.json
```

### Generate 5 Random Instances
```bash
python configurator_v3.py --generate-random 5
```

### Reset Everything
```bash
python configurator_v3.py --reset-registry --delete-instances
```

## Using in Your Code

```python
from configurator_v3 import TelefonConfiguratorV3

# Initialize
configurator = TelefonConfiguratorV3(".")

# Check what's available
available = configurator.get_available_configurations()
print(f"Available Bottom Covers: {available['Bottom_Cover']}")

# Create an instance
config = {
    "bottom_cover_material": "PLA-31212",
    "bottom_cover_color": "Red",
    "bottom_cover_finish": "Glossy",
    "top_cover_material": "ABS-5500",
    "top_cover_color": "Black",
    "top_cover_finish": "Matte",
    "number_of_fuses": 2
}

if configurator.create_telefon_instance(config):
    print("✓ Instance created and inventory deducted")
else:
    print("❌ Insufficient inventory")
```

## Working with Inventory Directly

```python
from inventory_db import InventoryDatabase

db = InventoryDatabase("inventory.db")

# Check stock
available, qty = db.check_availability(
    "Bottom_Cover",
    "Material: PLA-31212, Color: Red, Finish: Glossy",
    required_quantity=10
)

if available:
    print(f"✓ {qty} units in stock")
else:
    print("❌ Out of stock")

# Add stock (restock)
success, new_qty = db.update_inventory(
    "Bottom_Cover",
    "Material: PLA-31212, Color: Red, Finish: Glossy",
    quantity_change=+100,  # Add 100 units
    notes="Restock from supplier XYZ"
)

# Get low stock items
low = db.get_low_stock_items(threshold=10)
if low:
    print("⚠️ Low stock items:")
    for item in low:
        print(f"  {item.variant_spec}: {item.quantity} remaining")

db.close()
```

## File Structure

```
Telefon-Produktion/
├── configurator_v3.py              # Main configurator with inventory
├── inventory_db.py                 # Inventory database module
├── inventory.db                    # SQLite database (created on init)
├── INVENTORY_README.md             # Detailed documentation
└── JSON_Shells/                    # ... (unchanged from v2)
    JSON_Submodels/
    instance_registry.json
    example_order.json
```

## Key Features

### Automatic Validation
Before creating instances, v3 checks:
- Configuration validity
- Stock availability for all components
- Quantity requirements for fuses

### Flexible Inventory Specs
Components are identified by variant specifications:
- `"Material: PLA-31212, Color: Red, Finish: Glossy"`
- `"Standard Configuration"`
- `"1A Rating"`

### Audit Trail
Every transaction is logged with:
- Timestamp
- Component and quantity changed
- Previous and new inventory levels
- Transaction type (INITIAL_STOCK, CONSUMPTION, RESTOCK)
- Notes

### Low Stock Alerts
```python
low = db.get_low_stock_items(threshold=10)
for item in low:
    print(f"⚠️ {item.component_id}: only {item.quantity} left")
```

## Database Schema

**component_inventory** - Current stock
```
component_id     → "Bottom_Cover", "Fuse", etc.
variant_spec     → "Material: PLA-31212, Color: Red, ..."
quantity         → Current stock level
last_updated     → When last changed
```

**inventory_log** - Audit trail
```
timestamp        → When it happened
component_id     → Which component
variant_spec     → Which variant
quantity_change  → +100, -1, etc.
transaction_type → INITIAL_STOCK, CONSUMPTION, RESTOCK
notes            → Optional details
```

**component_options** - Valid values (for future validation)
```
component_type   → "Bottom_Cover"
option_type      → "Material", "Color", "Finish"
option_value     → "PLA-31212", "Red", "Glossy"
```

## Troubleshooting

**Q: "Cannot create instance: insufficient inventory"**

A: Check what's available:
```bash
python configurator_v3.py --print-available
```

**Q: How do I add more stock?**

A: Use the inventory API:
```python
db = InventoryDatabase("inventory.db")
db.update_inventory("Bottom_Cover", "Material: PLA-31212, Color: Red, Finish: Glossy", +50)
db.close()
```

**Q: Can I see all past transactions?**

A: Yes, check the audit log:
```python
db = InventoryDatabase("inventory.db")
history = db.get_transaction_history(limit=100)
for txn in history:
    print(f"{txn['timestamp']}: {txn['transaction_type']} {txn['quantity_change']:+d}")
```

**Q: How do I reset everything?**

A: Start fresh:
```bash
rm inventory.db
python configurator_v3.py --init-sample-inventory
```

## Integration with v2

Configurator v3 is **independent** of v2:
- v2 code remains unchanged
- v3 uses its own inventory database
- Can run both in parallel
- Migrate to v3 when ready

## Next Steps

1. **Review INVENTORY_README.md** for comprehensive documentation
2. **Customize sample data** - Add your actual components and quantities
3. **Integrate with your workflow** - Use the Python API in your applications
4. **Monitor inventory** - Set up regular stock checks
5. **Implement restock procedures** - Use the API to add new stock

## Support

For detailed API documentation, see **INVENTORY_README.md**

Common operations:
- Print inventory: `python configurator_v3.py --print-inventory`
- Create instance: `python configurator_v3.py --interactive`
- Check code: See `inventory_db.py` for InventoryDatabase API
- Check code: See `configurator_v3.py` for TelefonConfiguratorV3 API
