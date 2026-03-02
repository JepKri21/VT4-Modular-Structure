# SQL Server Integration - Implementation Steps

## Quick Start (30 Minutes)

### Step 1: Install pyodbc

```bash
pip install pyodbc
```

### Step 2: Create SQL Server Tables

Run this in SQL Server Management Studio:

```sql
-- Create AAS Shells table
CREATE TABLE aas_shells (
    id INT PRIMARY KEY IDENTITY(1,1),
    component_type NVARCHAR(100) NOT NULL,
    variant_id NVARCHAR(100) NOT NULL,
    version INT DEFAULT 1,
    shell_json NVARCHAR(MAX) NOT NULL,
    created_date DATETIME DEFAULT GETDATE(),
    modified_date DATETIME DEFAULT GETDATE(),
    UNIQUE(component_type, variant_id, version)
);

-- Create AAS Submodels table
CREATE TABLE aas_submodels (
    id INT PRIMARY KEY IDENTITY(1,1),
    component_type NVARCHAR(100) NOT NULL,
    submodel_name NVARCHAR(100) NOT NULL,
    variant_id NVARCHAR(100) NOT NULL,
    version INT DEFAULT 1,
    submodel_json NVARCHAR(MAX) NOT NULL,
    created_date DATETIME DEFAULT GETDATE(),
    modified_date DATETIME DEFAULT GETDATE(),
    UNIQUE(component_type, submodel_name, variant_id, version)
);

-- Create indices
CREATE INDEX idx_aas_shells ON aas_shells(component_type, variant_id);
CREATE INDEX idx_aas_submodels ON aas_submodels(component_type, submodel_name, variant_id);
```

### Step 3: Create Configuration File

Create `.env.sql` in your Telefon-Produktion directory:

```
SQL_SERVER=192.168.1.100
SQL_DATABASE=AAS_SHELLS
SQL_USERNAME=sa
SQL_PASSWORD=YourPassword
SQL_DRIVER=ODBC Driver 17 for SQL Server
```

**Or use environment variables:**

```bash
export SQL_SERVER=192.168.1.100
export SQL_DATABASE=AAS_SHELLS
export SQL_USERNAME=sa
export SQL_PASSWORD=YourPassword
```

### Step 4: Migrate Your JSON Shells to SQL Server

Create a migration script:

```python
"""
migrate_json_to_sql.py

Reads your existing JSON files and inserts them into SQL Server.
"""

import json
from pathlib import Path
import pyodbc
import os

def migrate_shells_to_sql():
    """Migrate existing JSON shells to SQL Server."""
    
    # Connect to SQL Server
    server = os.environ.get('SQL_SERVER', '192.168.1.100')
    database = os.environ.get('SQL_DATABASE', 'AAS_SHELLS')
    username = os.environ.get('SQL_USERNAME', 'sa')
    password = os.environ.get('SQL_PASSWORD')
    
    connection_string = (
        f"Driver={{ODBC Driver 17 for SQL Server}};"
        f"Server={server};"
        f"Database={database};"
        f"UID={username};"
        f"PWD={password};"
    )
    
    conn = pyodbc.connect(connection_string)
    cursor = conn.cursor()
    
    # Define shell locations (update these paths for your structure)
    shell_paths = [
        ("Bottom_Cover", "JSON_Shells/Product_Shells_JSON/Types/Component_Types/Product-Component-AAU-Bottom_Cover-Type.json"),
        ("Top_Cover", "JSON_Shells/Product_Shells_JSON/Types/Component_Types/Product-Component-AAU-Top_Cover-Type.json"),
        ("PCB", "JSON_Shells/Product_Shells_JSON/Types/Component_Types/Product-Component-AAU-PCB-Type.json"),
        ("Fuse", "JSON_Shells/Product_Shells_JSON/Types/Component_Types/Product-Component-AAU-Fuse-Type.json"),
    ]
    
    for component_type, shell_path in shell_paths:
        if not Path(shell_path).exists():
            print(f"⚠️  {shell_path} not found, skipping")
            continue
        
        with open(shell_path, 'r', encoding='utf-8') as f:
            shell_json = json.load(f)
        
        # Convert back to JSON string for storage
        shell_json_str = json.dumps(shell_json)
        
        # Insert into SQL Server
        insert_query = """
            INSERT INTO aas_shells (component_type, variant_id, shell_json)
            VALUES (?, ?, ?)
        """
        
        try:
            cursor.execute(insert_query, (component_type, "Type", shell_json_str))
            conn.commit()
            print(f"✓ Migrated {component_type} shell")
        except pyodbc.Error as e:
            print(f"❌ Error migrating {component_type}: {e}")
    
    conn.close()
    print("\n✓ Migration complete")

if __name__ == "__main__":
    migrate_shells_to_sql()
```

Run the migration:

```bash
python migrate_json_to_sql.py
```

### Step 5: Test the Connection

Create a test script:

```python
"""
test_sql_connection.py

Test if SQL Server connection works and contains data.
"""

from sql_server_integration import TelefonConfiguratorV3SQLServer
import os

# Load from environment variables or .env file
config_args = {
    'sql_server': os.environ.get('SQL_SERVER', '192.168.1.100'),
    'sql_database': os.environ.get('SQL_DATABASE', 'AAS_SHELLS'),
    'sql_username': os.environ.get('SQL_USERNAME', 'sa'),
    'sql_password': os.environ.get('SQL_PASSWORD', 'password'),
}

try:
    print("🔗 Connecting to SQL Server...")
    configurator = TelefonConfiguratorV3SQLServer(
        base_path=".",
        **config_args
    )
    print("✓ Connected to SQL Server\n")
    
    # List available components
    components = ["Bottom_Cover", "Top_Cover", "PCB", "Fuse"]
    
    for component in components:
        variants = configurator.list_available_variants(component)
        print(f"{component}: {len(variants)} variants")
        if variants:
            print(f"  Examples: {variants[:3]}")
    
    # Try loading a shell
    try:
        shell = configurator.get_shell_from_sql("Bottom_Cover", "Type")
        print(f"\n✓ Successfully loaded Bottom_Cover shell")
        print(f"  ID: {shell.get('id')}")
        print(f"  idShort: {shell.get('idShort')}")
    except Exception as e:
        print(f"\n❌ Could not load shell: {e}")
    
except Exception as e:
    print(f"❌ Connection failed: {e}")
    print("\nCheck:")
    print(f"  - SQL Server: {config_args['sql_server']}")
    print(f"  - Database: {config_args['sql_database']}")
    print(f"  - Username: {config_args['sql_username']}")
    print(f"  - ODBC Driver 17 installed")
    print(f"  - Network connectivity")
```

Run the test:

```bash
python test_sql_connection.py
```

Expected output:
```
🔗 Connecting to SQL Server...
✓ Connected to SQL Server

Bottom_Cover: 1 variants
  Examples: ['Type']
Top_Cover: 1 variants
  Examples: ['Type']
...

✓ Successfully loaded Bottom_Cover shell
  ID: https://aausmartlab.com/Assets/...
  idShort: Bottom_Cover
```

## Full Implementation

### Use in Configurator

Modify your configurator to use SQL Server:

```python
from sql_server_integration import TelefonConfiguratorV3SQLServer
import os

# Initialize with SQL Server backend
configurator = TelefonConfiguratorV3SQLServer(
    base_path=".",
    sql_server=os.environ.get('SQL_SERVER'),
    sql_database=os.environ.get('SQL_DATABASE'),
    sql_username=os.environ.get('SQL_USERNAME'),
    sql_password=os.environ.get('SQL_PASSWORD')
)

# Everything else works the same:
# - Inventory tracking (SQLite)
# - Creating instances
# - But shells come from SQL Server!
```

### Hybrid: JSON Cache with SQL Server

For offline support, use caching:

```python
from sql_server_integration import TelefonConfiguratorV3SQLServer
import json
from pathlib import Path

class CachedSQLConfigurator(TelefonConfiguratorV3SQLServer):
    """Use SQL Server as source, cache locally."""
    
    def __init__(self, *args, cache_dir="./shell_cache", **kwargs):
        super().__init__(*args, **kwargs)
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
    
    def get_shell_from_sql(self, component_type, variant_id):
        """Try cache first, fetch from SQL if needed."""
        cache_file = self.cache_dir / f"{component_type}_{variant_id}.json"
        
        # Try cache
        if cache_file.exists():
            print(f"  ✓ Loaded {component_type} from cache")
            with open(cache_file) as f:
                return json.load(f)
        
        # Fetch from SQL Server
        print(f"  🔄 Fetching {component_type} from SQL Server...")
        shell = super().get_shell_from_sql(component_type, variant_id)
        
        # Cache it
        with open(cache_file, 'w') as f:
            json.dump(shell, f, indent=2, ensure_ascii=False)
        
        return shell

# Use like normal:
configurator = CachedSQLConfigurator(...)
```

## Data Migration Examples

### Insert Single Shell

```sql
INSERT INTO aas_shells (component_type, variant_id, shell_json)
SELECT 
    'Bottom_Cover',
    'RED_GLOSSY',
    '{"id":"https://...","idShort":"Bottom_Cover",...}'
```

### Insert from CSV Import

```python
import csv
import json

with open('shells.csv') as f:
    reader = csv.DictReader(f)
    cursor = conn.cursor()
    
    for row in reader:
        shell_json = json.dumps(row['shell'])  # Assuming JSON in column
        cursor.execute(
            "INSERT INTO aas_shells (component_type, variant_id, shell_json) VALUES (?, ?, ?)",
            (row['component_type'], row['variant_id'], shell_json)
        )
    
    conn.commit()
```

### Verify Data

```sql
-- Check what's in SQL Server
SELECT component_type, COUNT(DISTINCT variant_id) as variant_count
FROM aas_shells
GROUP BY component_type;

-- Sample: Bottom_Cover | 1
--         Top_Cover    | 1
--         PCB          | 1
--         Fuse         | 1
```

## Production Checklist

- [ ] SQL Server database created
- [ ] Tables created (aas_shells, aas_submodels)
- [ ] Indices created
- [ ] Data migrated from JSON
- [ ] Credentials configured (.env.sql or environment)
- [ ] pyodbc installed
- [ ] Test connection script runs successfully
- [ ] Backup of original JSON files made
- [ ] SQL Server backup configured
- [ ] Network connectivity verified
- [ ] Read/write permissions verified
- [ ] Connection pooling considered (for scale)

## Monitoring & Maintenance

### Monitor Connections

```python
def check_sql_health():
    """Quick health check of SQL Server connection."""
    try:
        configurator = TelefonConfiguratorV3SQLServer(...)
        variants = configurator.list_available_variants("Bottom_Cover")
        if variants:
            print("✓ SQL Server healthy")
            return True
        else:
            print("⚠️  No data in SQL Server")
            return False
    except Exception as e:
        print(f"❌ SQL Server error: {e}")
        return False

# Schedule this to run periodically
# Can alert if SQL Server becomes unavailable
```

### Query Performance

```sql
-- Check table sizes
SELECT 
    TABLE_NAME,
    DATALENGTH(OBJECT_ID(TABLE_NAME)) as bytes
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_NAME IN ('aas_shells', 'aas_submodels');

-- Check query times
SET STATISTICS TIME ON;
SELECT * FROM aas_shells WHERE component_type = 'Bottom_Cover';
SET STATISTICS TIME OFF;
```

## Next Steps

1. **Install pyodbc** - `pip install pyodbc`
2. **Create tables** - Run SQL scripts in SSMS
3. **Migrate data** - Run migration script
4. **Test connection** - Run test script
5. **Update configurator** - Use `TelefonConfiguratorV3SQLServer`
6. **Monitor** - Check health periodically

Questions? See **SQL_SERVER_GUIDE.md** for detailed documentation.
