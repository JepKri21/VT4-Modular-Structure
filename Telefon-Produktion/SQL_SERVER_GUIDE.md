# SQL Server Integration Guide

## Overview

If you have access to a SQL Server database that holds the AAS shells for components, you can integrate it with the configurator while keeping inventory management local.

This gives you:
- ✅ **Centralized AAS Management** in SQL Server (single source of truth)
- ✅ **Local Inventory Tracking** in SQLite (fast, distributed)
- ✅ **Hybrid Architecture** (best of both worlds)

## Architecture

```
┌─────────────────────────────────────────┐
│       Configurator (configurator_v3.py) │
│                                          │
│  ┌──────────────────────────────────┐  │
│  │   SQL Server Integration         │  │
│  │                                  │  │
│  │  Fetches AAS shells and submodels│  │
│  │  for components, variants        │  │
│  └──────────────────────────────────┘  │
│            ↓          ↓                  │
│      ┌─────────┐  ┌─────────┐           │
│      │SQL Server│ │ Inventory│          │
│      │AAS Shells│ │ SQLite DB│          │
│      └─────────┘  └─────────┘           │
│                                          │
└─────────────────────────────────────────┘
```

## SQL Server Database Setup

### Required Tables

You need to create the following tables in your SQL Server:

#### 1. aas_shells Table
```sql
CREATE TABLE aas_shells (
    id INT PRIMARY KEY IDENTITY(1,1),
    component_type NVARCHAR(100) NOT NULL,      -- "Bottom_Cover", "Fuse", etc.
    variant_id NVARCHAR(100) NOT NULL,          -- "001", "RED_GLOSSY", etc.
    version INT DEFAULT 1,                       -- For versioning
    shell_json NVARCHAR(MAX) NOT NULL,          -- Complete AAS shell as JSON
    created_date DATETIME DEFAULT GETDATE(),
    modified_date DATETIME DEFAULT GETDATE(),
    UNIQUE(component_type, variant_id, version)
);

-- Create index for fast lookups
CREATE INDEX idx_aas_shells_component_variant 
ON aas_shells(component_type, variant_id);
```

#### 2. aas_submodels Table
```sql
CREATE TABLE aas_submodels (
    id INT PRIMARY KEY IDENTITY(1,1),
    component_type NVARCHAR(100) NOT NULL,
    submodel_name NVARCHAR(100) NOT NULL,       -- "Properties", "Bill_Of_Materials"
    variant_id NVARCHAR(100) NOT NULL,
    version INT DEFAULT 1,
    submodel_json NVARCHAR(MAX) NOT NULL,       -- Complete submodel as JSON
    created_date DATETIME DEFAULT GETDATE(),
    modified_date DATETIME DEFAULT GETDATE(),
    UNIQUE(component_type, submodel_name, variant_id, version)
);

-- Create index
CREATE INDEX idx_aas_submodels_component 
ON aas_submodels(component_type, submodel_name, variant_id);
```

### Sample Data

Insert your AAS shells and submodels as JSON:

```sql
-- Example: Insert Bottom Cover shell
INSERT INTO aas_shells (component_type, variant_id, shell_json)
VALUES (
    'Bottom_Cover',
    '001',
    '{
        "id": "https://aausmartlab.com/Assets/Product/Component/Bottom_Cover/001",
        "idShort": "Bottom_Cover",
        "assetInformation": {
            "assetKind": "Type"
        },
        ...complete shell JSON...
    }'
);

-- Example: Insert submodel
INSERT INTO aas_submodels (component_type, submodel_name, variant_id, submodel_json)
VALUES (
    'Bottom_Cover',
    'Properties',
    '001',
    '{
        "id": "https://aausmartlab.com/Assets/Product/Component/Bottom_Cover/001/Properties",
        "idShort": "Properties",
        "submodelElements": [...],
        ...complete submodel JSON...
    }'
);
```

## Using SQL Server Integration

### 1. Install Required Package

```bash
pip install pyodbc
```

Also install SQL Server ODBC driver:
- **Windows:** [ODBC Driver 17 for SQL Server](https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server)
- **Linux:** `apt install odbc-postgresql` (or mssql equivalent)

### 2. Create Configuration File

Create `.env.sql` in your Telefon-Produktion directory:

```
SQL_SERVER=192.168.1.100
SQL_DATABASE=AAS_SHELLS
SQL_USERNAME=sa
SQL_PASSWORD=YourPassword123
```

Or hardcode in your script:

```python
config = {
    'sql_server': '192.168.1.100',
    'sql_database': 'AAS_SHELLS',
    'sql_username': 'sa',
    'sql_password': 'YourPassword123'
}
```

### 3. Use in Your Code

```python
from sql_server_integration import TelefonConfiguratorV3SQLServer

# Initialize with SQL Server backend
configurator = TelefonConfiguratorV3SQLServer(
    base_path=".",
    sql_server="192.168.1.100",
    sql_database="AAS_SHELLS",
    sql_username="sa",
    sql_password="YourPassword123"
)

# List available variants in SQL Server
variants = configurator.list_available_variants("Bottom_Cover")
print(f"Available variants: {variants}")

# Load AAS shell from SQL Server
shell = configurator.get_shell_from_sql("Bottom_Cover", "001")

# Load submodel from SQL Server
props = configurator.get_submodel_from_sql("Bottom_Cover", "Properties", "001")

# Inventory tracking still uses local SQLite
available = configurator.inventory.check_availability(
    "Bottom_Cover",
    "Material: PLA-31212, Color: Red",
    required_quantity=1
)
```

## Complete Example: Creating Instance from SQL Server

```python
from sql_server_integration import TelefonConfiguratorV3SQLServer
import copy

# Initialize
configurator = TelefonConfiguratorV3SQLServer(
    base_path=".",
    sql_server="192.168.1.100",
    sql_database="AAS_SHELLS",
    sql_username="sa",
    sql_password="YourPassword123"
)

# Configuration
config = {
    'bottom_cover_material': 'PLA-31212',
    'bottom_cover_color': 'Red',
    'bottom_cover_finish': 'Glossy',
    'top_cover_material': 'ABS-5500',
    'top_cover_color': 'Black',
    'top_cover_finish': 'Matte',
    'number_of_fuses': 2
}

# 1. Check inventory (local SQLite)
available, qty = configurator.inventory.check_availability(
    "Bottom_Cover",
    "Material: PLA-31212, Color: Red, Finish: Glossy"
)

if not available:
    print("❌ Out of stock")
    exit()

print(f"✓ Stock available: {qty} units")

# 2. Load AAS shell from SQL Server
try:
    shell = configurator.get_shell_from_sql("Bottom_Cover", "001")
    print("✓ Loaded shell from SQL Server")
except FileNotFoundError as e:
    print(f"❌ {e}")
    exit()

# 3. Load submodels from SQL Server
submodels = {}
for submodel_name in ["Properties", "Documentation", "Bill_Of_Processes"]:
    try:
        submodels[submodel_name] = configurator.get_submodel_from_sql(
            "Bottom_Cover", submodel_name, "001"
        )
    except FileNotFoundError:
        print(f"⚠️  Submodel {submodel_name} not found")

# 4. Create instance (local filesystem)
instance_num = "001"
configurator._save_json(
    "JSON_Shells/Product_Shells_JSON/Instances/Component_Instances",
    f"Product-Component-AAU-Bottom_Cover-{instance_num}.json",
    shell
)

# 5. Deduct from inventory (local SQLite)
success, new_qty = configurator.inventory.update_inventory(
    "Bottom_Cover",
    "Material: PLA-31212, Color: Red, Finish: Glossy",
    quantity_change=-1,
    notes=f"Created instance {instance_num} from SQL Server shell"
)

if success:
    print(f"✓ Instance created, inventory updated: {new_qty} remaining")
else:
    print("❌ Failed to update inventory")
```

## Hybrid Workflow

### Data Location Mapping

| Data | Location | Why |
|------|----------|-----|
| AAS Shells | SQL Server | Central source of truth, controlled versioning |
| AAS Submodels | SQL Server | Same as shells, managed together |
| Component Inventory | SQLite | Fast local queries, distributed |
| Instance Registry | Local JSON | Quick access, instance tracking |
| Generated Instances | Local Files | Output for downstream processes |

### Benefits

1. **Single Source of Truth** for AAS templates
2. **Centralized Management** - Update component definitions in one place
3. **Versioning** - SQL Server tracks shell versions
4. **Performance** - SQLite keeps inventory queries fast
5. **Offline Support** - Can work locally if SQL Server unavailable (with caching)

## Advanced Scenarios

### 1. Caching SQL Server Results

For better offline support:

```python
import json
from pathlib import Path

class CachedSQLConfigurator(TelefonConfiguratorV3SQLServer):
    """Cache SQL Server results locally."""
    
    def __init__(self, *args, cache_dir="./cache", **kwargs):
        super().__init__(*args, **kwargs)
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
    
    def get_shell_from_sql(self, component_type, variant_id):
        """Try cache first, fall back to SQL Server."""
        cache_file = self.cache_dir / f"{component_type}_{variant_id}_shell.json"
        
        # Try cache
        if cache_file.exists():
            with open(cache_file) as f:
                print(f"  ✓ Loaded {component_type} from cache")
                return json.load(f)
        
        # Fall back to SQL Server
        shell = super().get_shell_from_sql(component_type, variant_id)
        
        # Update cache
        with open(cache_file, 'w') as f:
            json.dump(shell, f, indent=2)
        
        return shell
```

### 2. Sync from SQL Server to JSON

For migration or backup:

```python
def sync_sql_to_json(configurator, output_dir="./JSON_Shells_Backup"):
    """Export all SQL Server shells to JSON files."""
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)
    
    component_types = ["Bottom_Cover", "Top_Cover", "PCB", "Fuse"]
    
    for component_type in component_types:
        variants = configurator.list_available_variants(component_type)
        
        for variant_id in variants:
            try:
                shell = configurator.get_shell_from_sql(component_type, variant_id)
                
                filename = f"{component_type}_{variant_id}.json"
                filepath = output_dir / filename
                
                with open(filepath, 'w') as f:
                    json.dump(shell, f, indent=2, ensure_ascii=False)
                
                print(f"✓ Exported {component_type} variant {variant_id}")
            except Exception as e:
                print(f"❌ Error exporting {component_type} {variant_id}: {e}")
```

### 3. Multi-Environment Setup

Support dev/staging/production SQL Servers:

```python
def get_configurator(environment="production"):
    """Load configurator for different environments."""
    
    config = {
        "development": {
            "sql_server": "localhost",
            "sql_database": "AAS_DEV",
            "sql_username": "dev_user",
            "sql_password": "dev_password"
        },
        "staging": {
            "sql_server": "staging-sql.internal",
            "sql_database": "AAS_STAGING",
            "sql_username": "staging_user",
            "sql_password": os.environ.get("SQL_STAGING_PASSWORD")
        },
        "production": {
            "sql_server": "prod-sql.internal",
            "sql_database": "AAS_PROD",
            "sql_username": "prod_user",
            "sql_password": os.environ.get("SQL_PROD_PASSWORD")
        }
    }
    
    cfg = config.get(environment, config["production"])
    
    return TelefonConfiguratorV3SQLServer(
        base_path=".",
        **cfg
    )

# Usage
prod_config = get_configurator("production")
dev_config = get_configurator("development")
```

## Troubleshooting

### Connection Issues

```python
# Test connection
try:
    config = TelefonConfiguratorV3SQLServer(...)
    print("✓ SQL Server connected")
except Exception as e:
    print(f"❌ Connection failed: {e}")
    print("  Check: SQL Server hostname, database name, credentials")
    print("  Check: ODBC driver installed")
    print("  Check: Network connectivity")
```

### Missing Shells

```python
# Check what's available
variants = configurator.list_available_variants("Bottom_Cover")
if not variants:
    print("❌ No variants found in SQL Server")
    print("  Check: Data inserted into aas_shells table")
    print("  Check: component_type matches exactly")
```

### JSON Parsing Errors

```python
# Verify JSON stored correctly
# Run in SQL Server:
SELECT TOP 1 shell_json FROM aas_shells WHERE component_type = 'Bottom_Cover'

# Result should be valid JSON, not escaped string
```

## Summary

With SQL Server integration, you get:

✅ **Centralized AAS Management** - One place to update templates  
✅ **Distributed Inventory** - Fast local tracking  
✅ **Version Control** - SQL Server tracks shell versions  
✅ **Scalability** - Supports many variants and components  
✅ **Enterprise Ready** - Backup, replication, security via SQL Server  

The configurator can work with:
- Pure JSON files (original v3)
- SQL Server shells + SQLite inventory (this approach)
- Or migrate between them as needed
