# Telefon Configurator v3 — Two-Phase Configuration & Assembly

## Overview

Configurator v3 splits product manufacturing into two distinct phases:

- **Phase 1 (Configuration)**: Validate that a configuration is allowed and that required components are in stock, then create an order record
- **Phase 2 (Assembly)**: Pick available component instances, assemble them into the final product, and record traceability

This mirrors real-world manufacturing where configuration is separate from assembly.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  INVENTORY SYSTEM (inventory_db.py)                         │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  inventory_items (physical instances)                │  │
│  │  inventory_stock (qty per model_number)              │  │
│  │  model_catalog (permanent record of variants)        │  │
│  │  configuration_orders (pending orders)               │  │
│  │  assembly_log (traceability)                         │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
        ↓                           ↓                    ↓
┌──────────────────┐    ┌──────────────────┐   ┌────────────────┐
│ CONFIGURATOR v3  │    │ ASSEMBLY MANAGER │   │    AAS TYPES   │
│ (Phase 1)        │    │ (Phase 2)        │   │                │
│                  │    │                  │   │ • Types define │
│ • Validates      │    │ • Finds instances│   │   allowed      │
│   configuration  │    │ • Reserves them  │   │   options      │
│ • Checks stock   │    │ • Creates        │   │ • Assembly_    │
│ • Creates order  │    │   product        │   │   Traceability │
│                  │    │ • Fills tracing  │   │   template     │
└──────────────────┘    └──────────────────┘   └────────────────┘
```

## Workflow

### Phase 1: Create Configuration Order

```bash
# Interactive mode
python configurator_v3.py --interactive

# From config file
python configurator_v3.py --config example_order.json

# List pending orders
python configurator_v3.py --list-orders
```

**What happens:**
1. User provides configuration (material, color, finish, fuse count)
2. Configurator validates against Configuration_Template rules
3. Configurator generates model numbers needed (e.g., BC-ABS-Black-Matte)
4. Configurator queries inventory: are these model numbers in stock?
5. **Configurator RESERVES component instances** (marks status as 'reserved')
6. Creates `configuration_orders` record with status "pending" and reserved instances stored
7. Returns order ID (e.g., ORD-001)

**Why reserve during Phase 1?**
- Prevents race condition: two orders can't reserve the same instance
- Assembly is guaranteed to succeed (instances already locked in)

**Output:**
```
Reserving component instances for this order...
  ✓ Reserved Bottom_Cover: BC-ABS-Black-Matte (instance 042)
  ✓ Reserved Top_Cover: TC-PLA-Red-Glossy (instance 087)
  ✓ Reserved PCB_With_Fuse: PWF-F2 (instance 011)
  ✓ Reserved Housing_With_PCB: HWP-ABS-Black-F2 (instance 005)

✓ Configuration order created: ORD-001
  Product Type: Telefon_Pro_Max
  Status: pending (waiting for assembly)
  Reserved Instances: [Bottom_Cover-042, Top_Cover-087, PCB_With_Fuse-011, Housing_With_PCB-005]
```

### Phase 2: Assemble Order

```bash
# Assemble a specific order
python assembly_manager.py --assemble ORD-001

# List pending orders
python assembly_manager.py --list-pending

# List all orders
python assembly_manager.py --list-all
```

**What happens:**
1. Manager loads the order (which includes reserved instances from Phase 1)
2. Uses the reserved instances (no searching needed — race condition impossible)
3. Creates the final product instance (e.g., Telefon-001)
4. Fills `Assembly_Traceability` with:
   - Configuration order ID (ORD-001)
   - Assembly date
   - Actual instances used (instance_ids, instance_numbers, model_numbers)
5. Updates component instances to status "consumed"
6. Updates order status to "assembled"

**Output:**
```
Using reserved component instances for ORD-001:
  ✓ Bottom_Cover: BC-ABS-Black-Matte (instance 042)
  ✓ Top_Cover: TC-PLA-Red-Glossy (instance 087)
  ✓ PCB_With_Fuse: PWF-F2 (instance 011)
  ✓ Housing_With_PCB: HWP-ABS-Black-F2 (instance 005)

Creating final product instance 001...
  ✓ Created instance: https://aausmartlab.com/Assets/Product/Final_Product/Telefon/001/...
  ✓ Filled Assembly_Traceability

Updating component instances to 'consumed'...
  ✓ Consumed Bottom_Cover instance 042
  ✓ Consumed Top_Cover instance 087
  ✓ Consumed PCB_With_Fuse instance 011
  ✓ Consumed Housing_With_PCB instance 005

✓ Successfully assembled ORD-001

✓ Successfully assembled ORD-001
  Product Instance ID: https://aausmartlab.com/Assets/Product/Final_Product/Telefon/001/...
  Assembly Date: 2026-03-04 14:23:15
```

## Data Flow

### Before Assembly
```
inventory_items:
  instance_id              model_number          status
  Bottom_Cover-042         BC-ABS-Black-Matte    available
  Top_Cover-087            TC-PLA-Red-Glossy     available
  PCB-015                  PCB-Standard          available
  Housing-003              HWP-ABS-Black-Matte   available

inventory_stock:
  model_number             qty_available
  BC-ABS-Black-Matte       8
  TC-PLA-Red-Glossy        12
  ...

configuration_orders:
  order_id    status      configuration
  ORD-001     pending      {...}
```

### After Assembly
```
inventory_items:
  instance_id              model_number          status
  Bottom_Cover-042         BC-ABS-Black-Matte    consumed ← changed
  Top_Cover-087            TC-PLA-Red-Glossy     consumed ← changed
  PCB-015                  PCB-Standard          consumed ← changed
  Housing-003              HWP-ABS-Black-Matte   consumed ← changed

inventory_stock:
  model_number             qty_available
  BC-ABS-Black-Matte       7              ← decremented
  TC-PLA-Red-Glossy        11             ← decremented
  ...

configuration_orders:
  order_id    status      assembled_date
  ORD-001     assembled   2026-03-04 14:23:15 ← updated

Telefon-001 Documentation.Assembly_Traceability:
  assembly_date: 2026-03-04
  order_id: ORD-001
  used_components:
    bottom_cover: {instance_id: ..., instance_number: 042, model_number: BC-ABS-Black-Matte}
    top_cover: {instance_id: ..., instance_number: 087, model_number: TC-PLA-Red-Glossy}
    ...
```

## Key Features

✅ **Inventory-Aware**: Configuration respects actual stock levels
✅ **Deferred Assembly**: Orders can be created before physical assembly happens
✅ **Traceability**: Final product knows exactly which components were used
✅ **No Instances Until Needed**: Components aren't created until assembled
✅ **Flexible Picking**: Any instance of the right model number can be used
✅ **Audit Trail**: assembly_log tracks what went into what

## Status Progression

```
Components:          pending → available → reserved → consumed
Orders:              pending → assembled
```

## Usage Examples

### Example 1: Full Workflow

```bash
# 1. Create an order
python configurator_v3.py --config example_order.json
# Output: ORD-001 created

# 2. (Later, when ready to assemble)
python assembly_manager.py --assemble ORD-001
# Creates Telefon-001 with full traceability
```

### Example 2: Multiple Orders, Staggered Assembly

```bash
# Day 1: Create 5 orders
for i in {1..5}; do
  python configurator_v3.py --interactive
done
# Created: ORD-001, ORD-002, ORD-003, ORD-004, ORD-005

# Day 2: Assemble first 3 in priority order
python assembly_manager.py --assemble ORD-001
python assembly_manager.py --assemble ORD-003
python assembly_manager.py --assemble ORD-005

# Day 3: Assemble remaining
python assembly_manager.py --assemble ORD-002
python assembly_manager.py --assemble ORD-004
```

## AAS Enhancements for v3

**New: Assembly_Traceability submodel** in Final Product Type Documentation

```json
{
  "idShort": "Assembly_Traceability",
  "value": [
    {
      "idShort": "Assembly_Date",
      "value": "2026-03-04"
    },
    {
      "idShort": "Configuration_Order_ID",
      "value": "ORD-001"
    },
    {
      "idShort": "Used_Components",
      "value": [
        {
          "idShort": "Bottom_Cover",
          "value": [
            {"idShort": "instance_id", "value": "...Bottom_Cover/042/..."},
            {"idShort": "instance_number", "value": "042"},
            {"idShort": "model_number", "value": "BC-ABS-Black-Matte"}
          ]
        },
        ...
      ]
    }
  ]
}
```

## Database Tables

| Table | Purpose |
|-------|---------|
| `inventory_items` | Physical instances (one row per unit produced) |
| `inventory_stock` | Aggregated stock by model number (qty counters) |
| `model_catalog` | Permanent record of variant SKUs (never cleared) |
| `configuration_orders` | Pending/assembled product orders |
| `assembly_log` | Traceability: which instances went into which products |

## Error Handling

**If model number not in stock:**
```
ValueError: Not in stock: BC-ABS-Black-Matte, TC-PETG-Blue-Matte
(Fix: Manufacture more instances or adjust order)
```

**If order already assembled:**
```
Exception: Order ORD-001 is not pending (status: assembled)
(Can't re-assemble same order)
```

**If no available instances at assembly time:**
```
Exception: No available Bottom_Cover instance for model BC-ABS-Black-Matte.
(Normally shouldn't happen if configuration order was valid)
```

## Comparison: v2 vs v3

| Aspect | v2 | v3 |
|--------|----|----|
| Instance creation | Immediate (during config) | Deferred (during assembly) |
| Traceability | None | Full (via Assembly_Traceability) |
| Inventory check | None | Phase 1 (prevents invalid orders) |
| Picking | N/A | Phase 2 (flexible picking by model) |
| Orders | None | Tracked in DB |
| Timeline | Config → Instances in seconds | Config → Order; Later → Assembly |

## Future Enhancements

- Batch assembly API (assemble multiple orders at once)
- Reservation timeout (release reserved components if not assembled in N hours)
- Cost calculation per order
- Quality gate checks before assembly
- Warehouse location tracking
