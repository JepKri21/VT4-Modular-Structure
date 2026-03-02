# SQL Server Integration - Visual Diagrams

## System Architecture

### Current (v3 with JSON)
```
User Application
      ↓
Configurator v3
      ├→ Reads JSON files (AAS shells)
      ├→ Reads JSON files (submodels)
      ├→ Validates config
      ├→ Checks SQLite inventory
      └→ Creates instance

Local Filesystem          SQLite
├─ JSON Shells           ├─ component_inventory
├─ JSON Submodels       ├─ inventory_log
└─ Generated instances  └─ component_options
```

### New (v3 with SQL Server)
```
User Application
      ↓
Configurator v3 + SQL Server Integration
      ├→ Queries SQL Server (AAS shells)
      ├→ Queries SQL Server (submodels)
      ├→ Validates config
      ├→ Checks SQLite inventory
      └→ Creates instance

SQL Server                 SQLite               Local Filesystem
├─ aas_shells             ├─ component_inv      ├─ Generated instances
├─ aas_submodels         ├─ inventory_log      └─ Registry
└─ component_options     └─ component_options
```

## Data Flow - Creating Instance

### With JSON Files
```
┌─────────────────────────────────────┐
│    User Configuration               │
│  (Material, Color, Finish, Fuses)  │
└────────────┬────────────────────────┘
             ↓
┌─────────────────────────────────────┐
│    Check Availability              │
│    (Query SQLite Inventory)         │
└────────────┬────────────────────────┘
             ↓
┌─────────────────────────────────────┐
│    Load AAS Shells                  │
│    (Read JSON files)                │
└────────────┬────────────────────────┘
             ↓
┌─────────────────────────────────────┐
│    Load Submodels                   │
│    (Read JSON files)                │
└────────────┬────────────────────────┘
             ↓
┌─────────────────────────────────────┐
│    Patch & Create Instance          │
│    (Write to local filesystem)       │
└────────────┬────────────────────────┘
             ↓
┌─────────────────────────────────────┐
│    Deduct from Inventory            │
│    (Update SQLite)                  │
└─────────────────────────────────────┘
```

### With SQL Server
```
┌─────────────────────────────────────┐
│    User Configuration               │
│  (Material, Color, Finish, Fuses)  │
└────────────┬────────────────────────┘
             ↓
┌─────────────────────────────────────┐
│    Check Availability              │
│    (Query SQLite Inventory)         │
└────────────┬────────────────────────┘
             ↓
┌─────────────────────────────────────┐
│    Load AAS Shells                  │
│    (Query SQL Server)               │
│    OR Cache (JSON file)             │
└────────────┬────────────────────────┘
             ↓
┌─────────────────────────────────────┐
│    Load Submodels                   │
│    (Query SQL Server)               │
│    OR Cache (JSON file)             │
└────────────┬────────────────────────┘
             ↓
┌─────────────────────────────────────┐
│    Patch & Create Instance          │
│    (Write to local filesystem)       │
└────────────┬────────────────────────┘
             ↓
┌─────────────────────────────────────┐
│    Deduct from Inventory            │
│    (Update SQLite)                  │
└─────────────────────────────────────┘
```

## Deployment Models

### Model 1: JSON Only (Current)
```
Developer Machine         Production
│                         │
├─ JSON files            ├─ JSON files
├─ SQLite inventory      ├─ SQLite inventory
├─ Configurator v3       ├─ Configurator v3
└─ Config files          └─ Config files
```
**Pros:** Simple, no DB dependencies  
**Cons:** File management, manual versioning

---

### Model 2: SQL Server Centralized
```
Developer Machines       Central SQL Server      Production Machines
│                        │                       │
├─ Cache (JSON)          ├─ aas_shells          ├─ Cache (JSON)
├─ SQLite inventory      ├─ aas_submodels       ├─ SQLite inventory
├─ Configurator         └─ Versioning           ├─ Configurator
└─ Config files                                  └─ Config files
```
**Pros:** Central management, versioning  
**Cons:** SQL Server dependency

---

### Model 3: Hybrid with Cache
```
Developer              SQL Server              Cache Layer           Prod
│                      │                       │                     │
├─ Configurator      ├─ Source of truth      ├─ Hot data            ├─ Fast local
├─ Config             ├─ Component defs      ├─ Common variants    ├─ Works offline
└─ Falls back         └─ Versioning          └─ Auto-sync          └─ Fallback
```
**Pros:** Best of both worlds  
**Cons:** Cache coherency

---

## Database Schema

### SQL Server (Centralized)
```
┌──────────────────────────────┐
│      aas_shells              │
├──────────────────────────────┤
│ id (PK)                      │
│ component_type               │
│ variant_id                   │
│ version                      │
│ shell_json                   │
│ created_date                 │
│ modified_date                │
└──────────────────────────────┘
         ↑
    Created by: Admin/Engineer
    Updated by: Change process
    Queried by: Configurator
    
┌──────────────────────────────┐
│    aas_submodels             │
├──────────────────────────────┤
│ id (PK)                      │
│ component_type               │
│ submodel_name                │
│ variant_id                   │
│ version                      │
│ submodel_json                │
│ created_date                 │
│ modified_date                │
└──────────────────────────────┘
         ↑
    Created by: Admin/Engineer
    Updated by: Change process
    Queried by: Configurator
```

### SQLite (Distributed)
```
┌──────────────────────────────┐
│  component_inventory         │
├──────────────────────────────┤
│ id (PK)                      │
│ component_id                 │
│ variant_spec                 │
│ quantity                      │
│ last_updated                 │
│ notes                        │
└──────────────────────────────┘
         ↑
    Created by: Migration/Admin
    Updated by: Configurator
    Queried by: Inventory checks
    
┌──────────────────────────────┐
│     inventory_log            │
├──────────────────────────────┤
│ id (PK)                      │
│ timestamp                    │
│ component_id                 │
│ quantity_change              │
│ previous_quantity            │
│ new_quantity                 │
│ transaction_type             │
│ notes                        │
└──────────────────────────────┘
         ↑
    Created by: Configurator
    Queried by: Audit/Reports
```

## Migration Path

```
Week 1: Evaluation
├─ Review SQL Server architecture
├─ Plan migration
└─ Set up test SQL Server

Week 2: Setup
├─ Create SQL Server tables
├─ Create migration scripts
├─ Test connection
└─ Back up JSON files

Week 3: Migration
├─ Run migration scripts
├─ Verify data in SQL Server
├─ Test configurator with SQL Server
└─ Run parallel tests

Week 4: Deploy
├─ Update production config
├─ Monitor for issues
├─ Keep JSON as fallback
└─ Celebrate! 🎉

Ongoing: Optimization
├─ Monitor performance
├─ Add caching if needed
├─ Archive old JSON files
└─ Update documentation
```

## Network Diagram

### Local Development
```
Developer Laptop
│
├─ Configurator
├─ SQLite (inventory.db)
└─ JSON files (backup)
    
    [No SQL Server needed]
```

### Team Environment
```
Developer Team
│
├─ Each: Configurator + SQLite
├─ Central: SQL Server (AAS shells)
└─ Network: All connected via LAN

Production: same as Team
```

### Enterprise Deployment
```
HQ
├─ SQL Server (Primary)
├─ SQL Server (Backup/Replica)
└─ Cache server (optional)

Regional Offices
├─ Configurator + SQLite
├─ Cache (optional)
└─ Network: VPN to HQ SQL Server
```

## Comparison Matrix

```
                    JSON Files      SQL Server      SQL+Cache
─────────────────────────────────────────────────────────────────
Deployment Time     5 min          30 min          45 min
Learning Curve      Easy           Moderate        Moderate
Infrastructure      None           SQL Server      SQL + Cache
Backup Strategy     Git/Files      DB Backup       DB + Files
Versioning          Manual         Native          Native
Collaboration       Git Conflicts  Native Locking  Native Locking
Performance         File I/O       SQL Query       Cache Hit
Scalability         Files (limited) Enterprise      Enterprise
Offline Support     ✓              ✗ (can cache)   ✓
Cost               ✓ Free         $ SQL License   $ + Cache
Monitoring         ✗              ✓               ✓
Disaster Recovery  Backup files   DB Restore      DB + Cache
```

## Decision Tree

```
Do you have SQL Server?
│
├─ NO
│  │
│  └─ Use JSON files (v3 current state)
│
└─ YES
   │
   ├─ Teams using same components?
   │  │
   │  └─ YES → Use SQL Server directly
   │  └─ NO  → Use caching layer
   │
   └─ Need offline support?
      │
      └─ YES → Use caching layer
      └─ NO  → Use SQL Server directly
```

## Load Pattern Examples

### Example 1: Centralized Control
```
SQL Server
   ↓
(1 source, all read)
   ↓
├─ Developer Team
├─ Production Cluster
└─ Remote Office
```
**Result:** Everyone gets latest version, no conflicts

---

### Example 2: Edge Caching
```
SQL Server → Cache Layer → Local Copies
   ↓            ↓              ↓
   │     Local JSON files   Configurators
   │     Refresh hourly     Fall back to cache
   │
   └─ Changes sync back
```
**Result:** Fast local access, eventual consistency

---

### Example 3: Fallback Strategy
```
Try SQL Server
   ↓ (if available)
Try Cache
   ↓ (if available)
Use JSON files
   ↓ (always available)
Notify admin (if critical)
```
**Result:** Always works, with best data available

---

## Summary

- **JSON**: Simple, good for small teams
- **SQL Server**: Enterprise, centralized management
- **Hybrid**: Best performance and reliability
- **Caching**: Offline support with fresh data

Choose the model that fits your needs!
