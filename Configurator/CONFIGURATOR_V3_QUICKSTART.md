# Configurator v3 — Quick Start Guide

## Setup

Make sure your inventory is populated first:

```bash
# Sync inventory from any existing JSON instance files
python inventory_db.py --sync

# Check current stock
python inventory_db.py --status
```

## How It Works

Configurator v3 uses a **two-phase approach with immediate reservation**:

1. **Phase 1 (Configuration)**: Validates configuration, checks stock, and **RESERVES instances immediately**
   - All component instances locked in for this order
   - No race condition: other orders cannot grab the same instances
   - Assembly is guaranteed to succeed

2. **Phase 2 (Assembly)**: Creates the final product using reserved instances
   - Always succeeds (instances already reserved)
   - Marks instances as "consumed"

## Quick Example

### Step 1: Create a Configuration Order (RESERVES Instances)

```bash
python configurator_v3.py --interactive
```

**What happens:**
- ✓ Queries inventory to see what's in stock
- ✓ Shows **only available options** for each configuration field
- ✓ Fuse count options only show if stock exists
- ✓ **RESERVES component instances** (updates inventory status to 'reserved')
- ✓ Creates a pending order record with reserved instances stored
- ✓ Assembly will always succeed because instances are already locked in!

Follow the prompts (example with limited stock):
```
Bottom Cover Configuration (Available in Stock):
  Material (ABS-5500/PLA-31212) [ABS-5500]: ABS-5500
  Color (Black/Red) [Black]: Black
  Finish (Matte/Glossy) [Matte]: Matte

PCB Component (Standard):
  Model: PCB-AAU (fixed standard component)

Top Cover Configuration (Available in Stock):
  Material (PLA-31212) [PLA-31212]: PLA-31212
  Color (Red) [Red]: Red
  Finish (Glossy) [Glossy]: Glossy

PCB with Fuse Assembly Configuration (Available in Stock):
  Number of fuses (1/2) [1]: 2
```

**Output:**
```
✓ Configuration order created: ORD-001
  Product Type: Telefon_Pro_Max
  Status: pending (waiting for assembly)
  Model Numbers Needed:
    - Bottom_Cover:     BC-ABS-5500-Black-Matte
    - PCB:              PCB-AAU
    - Top_Cover:        TC-PLA-31212-Red-Glossy
    - PCB_With_Fuse:    PWF-F2
    - Housing_With_PCB: HWP-ABS-5500-Black-F2

Use assembly_manager.py to assemble this order:
  python assembly_manager.py --assemble ORD-001
```

### Step 2: List Pending Orders

```bash
python configurator_v3.py --list-orders
```

### Step 3: Assemble the Order (Uses Reserved Instances)

```bash
python assembly_manager.py --assemble ORD-001
```

**What happens:**
- ✓ Loads reserved instances from the order (no searching needed)
- ✓ Creates the final product (Telefon instance)
- ✓ Fills Assembly_Traceability with component details
- ✓ Marks reserved instances as "consumed"
- ✓ **Always succeeds** (no availability check needed because instances were reserved in Phase 1)

**Output:**
```
Finding available component instances for ORD-001...
  ✓ Bottom_Cover:     BC-ABS-5500-Black-Matte (instance 042)
  ✓ PCB:              PCB-AAU (instance 156)
  ✓ Top_Cover:        TC-PLA-31212-Red-Glossy (instance 087)
  ✓ PCB_With_Fuse:    PWF-F2 (instance 011)
  ✓ Housing_With_PCB: HWP-ABS-5500-Black-F2 (instance 005)

Reserving instances...
  ✓ Reserved Bottom_Cover instance 042
  ✓ Reserved PCB instance 156
  ✓ Reserved Top_Cover instance 087
  ✓ Reserved PCB_With_Fuse instance 011
  ✓ Reserved Housing_With_PCB instance 005

Creating final product instance 001...
  ✓ Created instance: https://aausmartlab.com/...

✓ Successfully assembled ORD-001
  Product Instance ID: https://aausmartlab.com/Assets/Product/Final_Product/Telefon/001/...
  Assembly Date: 2026-03-04 14:25:30
```

### Step 4: Check Inventory After Assembly

```bash
python inventory_db.py --status
```

Stock quantities should have decreased!

## Key Differences from v2

| Feature | v2 | v3 |
|---------|----|----|
| Instance creation | Immediate | On demand (during assembly) |
| Stock check | None | Yes (during configuration) |
| Order tracking | None | Yes |
| Traceability | None | Full (which components in which product) |
| Timeline | Config instant, all files created | Config fast, assembly later |

## Troubleshooting

**"Not in stock: BC-ABS-5500-Black-Matte"**
→ Model number not available. Check `inventory_db.py --status`. You may need to create more component instances first using v2 or import from elsewhere.

**"No available Bottom_Cover instance for model BC-ABS-5500-Black-Matte"**
→ Order was valid when created, but components were consumed by another order before assembly. Try assemble immediately after configuration, or create more components.

**"Order ORD-001 is not pending"**
→ Order was already assembled. Each order can only be assembled once.

## Files Created/Modified

✅ **New Files:**
- `configurator_v3.py` — Phase 1: Configuration & order creation
- `assembly_manager.py` — Phase 2: Assembly & traceability
- `CONFIGURATOR_V3_README.md` — Full documentation

✅ **Modified Files:**
- `inventory_db.py` — Added 2 new tables: `configuration_orders`, `assembly_log`
- `Product-Final_Product-Telefon-Telefon_Pro_Max-Type-Documentation.json` — Added Assembly_Traceability submodel template

## Database Schema Changes

**New table: `configuration_orders`**
```sql
order_id            TEXT PRIMARY KEY   -- "ORD-001"
product_type        TEXT               -- "Telefon_Pro_Max"
configuration       TEXT               -- JSON config
model_numbers_needed TEXT              -- JSON needed model numbers
status              TEXT               -- "pending" or "assembled"
created_date        TEXT               -- When order was created
assembled_date      TEXT               -- When order was assembled (NULL if pending)
```

**New table: `assembly_log`**
```sql
assembly_id             TEXT PRIMARY KEY
product_instance_id     TEXT              -- Telefon instance ID
component_type          TEXT              -- "Bottom_Cover", etc.
component_instance_id   TEXT              -- Which instance was used
model_number            TEXT              -- Its model number
assembly_date           TEXT              -- When assembled
```

## Next Steps

1. ✅ Sync existing inventory: `python inventory_db.py --sync`
2. ✅ Create orders: `python configurator_v3.py --interactive`
3. ✅ Assemble them: `python assembly_manager.py --assemble ORD-001`
4. ✅ Check results: `python inventory_db.py --status`
5. 📋 Query traceability: Open the Telefon instance JSON and check Assembly_Traceability

Enjoy your two-phase manufacturing workflow!
