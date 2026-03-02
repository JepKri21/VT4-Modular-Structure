"""
SQL Server Integration for Configurator v3

Extends configurator_v3.py to fetch AAS shells from a SQL Server database
instead of reading from JSON files.

This allows your AAS shells to be stored, versioned, and managed in a 
centralized SQL Server while keeping inventory tracking local (SQLite).
"""

import json
import pyodbc
from typing import Dict, Any, Optional
from datetime import datetime
from pathlib import Path


# =============================================================================
# SQL Server Connection Manager
# =============================================================================

class SQLServerConnection:
    """
    Manages connection to SQL Server database containing AAS shells.
    
    Expected database structure:
    - Table: aas_shells
    - Columns: id, component_type, variant_id, version, shell_json, created_date
    
    - Table: aas_submodels
    - Columns: id, component_type, submodel_name, variant_id, submodel_json, version
    """

    def __init__(
        self,
        server: str,
        database: str,
        username: str,
        password: str,
        driver: str = "ODBC Driver 17 for SQL Server"
    ):
        """
        Initialize SQL Server connection.
        
        Args:
            server: SQL Server hostname/IP (e.g., "192.168.1.100")
            database: Database name (e.g., "AAS_SHELLS")
            username: SQL Server username
            password: SQL Server password
            driver: ODBC driver to use
        """
        self.server = server
        self.database = database
        self.username = username
        self.password = password
        self.driver = driver
        self.connection = None
        self._connect()

    def _connect(self):
        """Establish connection to SQL Server."""
        try:
            connection_string = (
                f"Driver={{{self.driver}}};"
                f"Server={self.server};"
                f"Database={self.database};"
                f"UID={self.username};"
                f"PWD={self.password};"
            )
            self.connection = pyodbc.connect(connection_string)
            print(f"✓ Connected to SQL Server: {self.server}/{self.database}")
        except pyodbc.Error as e:
            print(f"❌ SQL Server connection failed: {e}")
            raise

    def get_shell_by_variant(
        self,
        component_type: str,
        variant_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch AAS shell for a specific component variant from SQL Server.
        
        Args:
            component_type: Component type (e.g., "Bottom_Cover")
            variant_id: Variant identifier (e.g., "001", "RED_GLOSSY")
        
        Returns:
            Parsed JSON shell as dict, or None if not found
        """
        cursor = self.connection.cursor()
        
        query = """
        SELECT shell_json
        FROM aas_shells
        WHERE component_type = ? AND variant_id = ?
        ORDER BY version DESC
        """
        
        cursor.execute(query, (component_type, variant_id))
        row = cursor.fetchone()
        
        if row:
            return json.loads(row[0])
        return None

    def get_submodel_by_variant(
        self,
        component_type: str,
        submodel_name: str,
        variant_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch AAS submodel for a specific component variant.
        
        Args:
            component_type: Component type
            submodel_name: Submodel name (e.g., "Properties", "Bill_Of_Materials")
            variant_id: Variant identifier
        
        Returns:
            Parsed JSON submodel as dict, or None if not found
        """
        cursor = self.connection.cursor()
        
        query = """
        SELECT submodel_json
        FROM aas_submodels
        WHERE component_type = ? AND submodel_name = ? AND variant_id = ?
        ORDER BY version DESC
        """
        
        cursor.execute(query, (component_type, submodel_name, variant_id))
        row = cursor.fetchone()
        
        if row:
            return json.loads(row[0])
        return None

    def list_available_variants(self, component_type: str) -> list:
        """
        Get all available variants for a component type.
        
        Returns:
            List of variant IDs
        """
        cursor = self.connection.cursor()
        
        query = """
        SELECT DISTINCT variant_id
        FROM aas_shells
        WHERE component_type = ?
        ORDER BY variant_id
        """
        
        cursor.execute(query, (component_type,))
        return [row[0] for row in cursor.fetchall()]

    def close(self):
        """Close SQL Server connection."""
        if self.connection:
            self.connection.close()

    def __del__(self):
        """Cleanup on garbage collection."""
        self.close()


# =============================================================================
# SQL Server-Backed Configurator
# =============================================================================

class TelefonConfiguratorV3SQLServer:
    """
    Extended configurator that fetches AAS shells from SQL Server.
    
    Combines:
    - AAS shells and submodels from SQL Server
    - Inventory tracking from SQLite (via InventoryDatabase)
    
    This is a hybrid approach:
    - Centralized AAS management in SQL Server
    - Distributed inventory management in SQLite
    """

    def __init__(
        self,
        base_path: str,
        sql_server: str,
        sql_database: str,
        sql_username: str,
        sql_password: str,
        sql_driver: str = "ODBC Driver 17 for SQL Server",
        inventory_db_path: Optional[str] = None
    ):
        """
        Initialize configurator with SQL Server backend.
        
        Args:
            base_path: Local working directory
            sql_server: SQL Server hostname/IP
            sql_database: SQL Server database name
            sql_username: SQL Server username
            sql_password: SQL Server password
            sql_driver: ODBC driver
            inventory_db_path: Path to inventory SQLite database
        """
        self.base_path = Path(base_path)
        self.registry_path = self.base_path / "instance_registry.json"
        
        # Initialize SQL Server connection
        self.sql_server = SQLServerConnection(
            server=sql_server,
            database=sql_database,
            username=sql_username,
            password=sql_password,
            driver=sql_driver
        )
        
        # Initialize inventory database (separate SQLite)
        if inventory_db_path is None:
            inventory_db_path = str(self.base_path / "inventory.db")
        
        from inventory_db import InventoryDatabase
        self.inventory = InventoryDatabase(inventory_db_path)
        
        self.registry = self._load_registry()

    def _load_registry(self) -> Dict[str, Any]:
        """Load local instance registry."""
        if self.registry_path.exists():
            with open(self.registry_path, encoding="utf-8") as f:
                return json.load(f)
        return {
            "description": "Registry tracking all created product instances",
            "last_updated": datetime.now().isoformat(),
            "product_types": {}
        }

    def _save_registry(self):
        """Save local instance registry."""
        with open(self.registry_path, "w", encoding="utf-8") as f:
            json.dump(self.registry, f, indent=2, ensure_ascii=False)

    def get_shell_from_sql(
        self,
        component_type: str,
        variant_id: str
    ) -> Dict[str, Any]:
        """
        Load AAS shell from SQL Server instead of JSON file.
        
        Args:
            component_type: Component type identifier
            variant_id: Variant ID
        
        Returns:
            AAS shell as dictionary
        
        Raises:
            FileNotFoundError: If shell not found in SQL Server
        """
        shell = self.sql_server.get_shell_by_variant(component_type, variant_id)
        
        if not shell:
            raise FileNotFoundError(
                f"AAS shell not found in SQL Server:\n"
                f"  Component: {component_type}\n"
                f"  Variant: {variant_id}"
            )
        
        print(f"  ✓ Loaded {component_type} shell from SQL Server")
        return shell

    def get_submodel_from_sql(
        self,
        component_type: str,
        submodel_name: str,
        variant_id: str
    ) -> Dict[str, Any]:
        """
        Load AAS submodel from SQL Server.
        
        Args:
            component_type: Component type
            submodel_name: Submodel name
            variant_id: Variant ID
        
        Returns:
            AAS submodel as dictionary
        
        Raises:
            FileNotFoundError: If submodel not found
        """
        submodel = self.sql_server.get_submodel_by_variant(
            component_type, submodel_name, variant_id
        )
        
        if not submodel:
            raise FileNotFoundError(
                f"AAS submodel not found in SQL Server:\n"
                f"  Component: {component_type}\n"
                f"  Submodel: {submodel_name}\n"
                f"  Variant: {variant_id}"
            )
        
        print(f"  ✓ Loaded {component_type}-{submodel_name} from SQL Server")
        return submodel

    def list_available_variants(self, component_type: str) -> list:
        """
        List all available variants for a component from SQL Server.
        
        Args:
            component_type: Component type
        
        Returns:
            List of variant IDs available in SQL Server
        """
        return self.sql_server.list_available_variants(component_type)

    def _save_json(self, rel_dir: str, filename: str, data: Dict[str, Any]) -> Path:
        """Write generated instance to local filesystem."""
        out_path = self.base_path / rel_dir / filename
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return out_path


# =============================================================================
# Configuration Helper
# =============================================================================

class SQLServerConfig:
    """Helper to load SQL Server config from file."""
    
    @staticmethod
    def load_from_env_file(env_file: str = ".env.sql") -> Dict[str, str]:
        """
        Load SQL Server configuration from .env file.
        
        Expected format:
        SQL_SERVER=192.168.1.100
        SQL_DATABASE=AAS_SHELLS
        SQL_USERNAME=sa
        SQL_PASSWORD=YourPassword123
        """
        config = {}
        
        if not Path(env_file).exists():
            print(f"⚠️  No {env_file} found. Using defaults or environment variables.")
            return config
        
        with open(env_file, "r") as f:
            for line in f:
                line = line.strip()
                if line and "=" in line and not line.startswith("#"):
                    key, value = line.split("=", 1)
                    config[key.strip()] = value.strip()
        
        return config
    
    @staticmethod
    def from_dict(config_dict: Dict[str, str]) -> 'SQLServerConfig':
        """Create config from dictionary."""
        return config_dict


# =============================================================================
# Usage Example
# =============================================================================

def example_usage():
    """
    Example: Using Configurator with SQL Server for AAS shells
    and SQLite for inventory tracking.
    """
    
    # Load SQL Server configuration
    config = SQLServerConfig.load_from_env_file()
    
    # Or configure manually
    sql_config = {
        'sql_server': config.get('SQL_SERVER', '192.168.1.100'),
        'sql_database': config.get('SQL_DATABASE', 'AAS_SHELLS'),
        'sql_username': config.get('SQL_USERNAME', 'sa'),
        'sql_password': config.get('SQL_PASSWORD', 'password'),
    }
    
    # Initialize configurator
    try:
        configurator = TelefonConfiguratorV3SQLServer(
            base_path=".",
            **sql_config
        )
        
        # Example: List available Bottom Cover variants in SQL Server
        variants = configurator.list_available_variants("Bottom_Cover")
        print(f"\nAvailable Bottom Cover variants in SQL Server:")
        for variant in variants:
            print(f"  - {variant}")
        
        # Example: Load a shell from SQL Server
        shell = configurator.get_shell_from_sql("Bottom_Cover", "001")
        print(f"\n✓ Loaded shell: {shell.get('idShort')}")
        
        # Example: Load a submodel from SQL Server
        props = configurator.get_submodel_from_sql(
            "Bottom_Cover", "Properties", "001"
        )
        print(f"✓ Loaded submodel with {len(props.get('submodelElements', []))} elements")
        
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    example_usage()
