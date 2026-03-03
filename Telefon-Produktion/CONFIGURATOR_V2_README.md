# Telefon Product Configurator v2

## Overview

The **Telefon Configurator v2** is a template-driven configuration system that generates complete AAS (Asset Administration Shell) instances for the Telefon Pro Max product. It uses JSON Type files as templates and automatically generates instance files without requiring code changes.

### Key Features

- **Template-Driven Design**: All instance file layouts are defined entirely in Type JSON files
- **Zero-Code Updates**: Adding/removing properties, BOM components, or process steps in Type files automatically flows through to all newly generated instances
- **Modular Product Structure**: Supports components, sub-assemblies, and final products
- **Configurable Properties**: Dynamic configuration of materials, colors, finishes, and quantities
- **Registry Management**: Automatic instance ID tracking and registry updates
- **Validation**: Configuration validation against defined rules and constraints

---

## Directory Structure

```
Telefon-Produktion/
├── configurator_v2.py              # Main configurator script
├── CONFIGURATOR_V2_README.md        # This file
├── instance_registry.json           # Instance tracking database
├── example_order.json               # Example configuration file
├── JSON_Shells/
│   └── Product_Shells_JSON/
│       ├── Types/
│       │   ├── Component_Types/
│       │   ├── Sub_Assembly_Types/
│       │   └── Final_Product_Types/
│       └── Instances/
│           ├── Component_Instances/
│           ├── Sub_Assembly_Instances/
│           └── Final_Product_Instances/
└── JSON_Submodels/
    └── Product_Submodels_JSON/
        ├── Types/
        │   ├── Component_Type_Submodels/
        │   ├── Sub_Assembly_Type_Submodels/
        │   └── Final_Product_Type_Submodels/
        └── Instances/
            ├── Component_Instance_Submodels/
            ├── Sub_Assembly_Instance_Submodels/
            └── Final_Product_Instance_Submodels/
```

---

## Supported Product Types

The configurator supports the following asset types:

### Components
- **Bottom_Cover**: Phone housing bottom piece with configurable material, color, and finish
- **Top_Cover**: Phone housing top piece with configurable material, color, and finish
- **PCB**: Printed circuit board component
- **Fuse**: Individual fuse component (quantity configurable)

### Sub-Assemblies
- **PCB_With_Fuse**: PCB assembly with configurable number of fuses
- **Housing_With_PCB**: Complete housing assembly with integrated PCB

### Final Products
- **Telefon**: Complete Telefon Pro Max product with all components and materials

---

## Usage

### 1. Interactive Mode (Guided Configuration)

Run the configurator in interactive mode to be prompted for configuration values:

```powershell
python configurator_v2.py --interactive
```

You will be prompted to enter:
- Bottom Cover: Material, Color, Finish
- Top Cover: Material, Color, Finish
- Number of Fuses (1/2/3)

**Example output:**
```
=== Telefon Configurator v2 — Interactive Mode ===

Bottom Cover Configuration:
  Material (PLA-31212/ABS-5500/PETG-7700) [PLA-31212]: ABS-5500
  Color (Red/Blue/Black/White/Green) [Red]: Black
  Finish (Glossy/Matte/Textured) [Glossy]: Matte

Top Cover Configuration:
  Material (PLA-31212/ABS-5500/PETG-7700) [PLA-31212]: ABS-5500
  Color (Red/Blue/Black/White/Green) [Red]: Black
  Finish (Glossy/Matte/Textured) [Glossy]: Matte

Fuse Configuration:
  Number of fuses (1/2/3) [1]: 2
```

### 2. Configuration File Mode

Create a configuration JSON file and pass it to the configurator:

```powershell
python configurator_v2.py --config example_order.json
```

**Configuration file format** (`example_order.json`):
```json
{
  "bottom_cover_material": "ABS-5500",
  "bottom_cover_color": "Black",
  "bottom_cover_finish": "Matte",
  "top_cover_material": "ABS-5500",
  "top_cover_color": "Black",
  "top_cover_finish": "Matte",
  "number_of_fuses": 2
}
```

### 3. Generate Random Instances

Generate multiple random valid configurations automatically:

```powershell
python configurator_v2.py --generate-random 5
```

This creates 5 Telefon instances with randomly generated (but valid) configurations.

### 4. Reset Registry and Delete Files

Reset the instance registry to initial state and optionally delete all generated files:

```powershell
# Reset registry only (keeps instance files)
python configurator_v2.py --reset-registry

# Reset registry AND delete all instance files
python configurator_v2.py --reset-registry --delete-instances
```

**Warning**: The `--delete-instances` flag permanently deletes all generated JSON files. This is useful for a clean reset.

---

## Command-Line Arguments

| Argument | Type | Description |
|----------|------|-------------|
| `--interactive` | flag | Launch interactive mode for step-by-step configuration |
| `--config PATH` | string | Load configuration from JSON file |
| `--generate-random COUNT` | integer | Generate COUNT random valid instances |
| `--reset-registry` | flag | Reset instance registry to initial state |
| `--delete-instances` | flag | Delete all instance files when resetting (use with `--reset-registry`) |

---

## Configuration Parameters

### Required Parameters

| Parameter | Type | Values | Description |
|-----------|------|--------|-------------|
| `bottom_cover_material` | string | PLA-31212, ABS-5500, PETG-7700 | Bottom cover material ID |
| `bottom_cover_color` | string | Red, Blue, Black, White, Green | Bottom cover color |
| `bottom_cover_finish` | string | Glossy, Matte, Textured | Bottom cover surface finish |
| `top_cover_material` | string | PLA-31212, ABS-5500, PETG-7700 | Top cover material ID |
| `top_cover_color` | string | Red, Blue, Black, White, Green | Top cover color |
| `top_cover_finish` | string | Glossy, Matte, Textured | Top cover surface finish |
| `number_of_fuses` | integer | 1, 2, 3 | Number of fuses in the device |

### Configuration Rules

1. **Material-Finish Compatibility**: Not all material-finish combinations are valid
   - Check `Configuration_Rules.Material_Finish_Compatibility` in the configuration template

2. **Covers Must Match**: (Optional) Ensures top and bottom covers use the same material and finish
   - Controlled by `Configuration_Rules.Covers_Must_Match`

3. **Fuse Quantity Limits**: 
   - Minimum: 1 fuse
   - Maximum: 3 fuses
   - (Configurable in `Configuration_Rules`)

---

## Generated File Structure

When an instance is created (e.g., instance #001), the following files are generated:

### Shell Files
```
JSON_Shells/Product_Shells_JSON/Instances/
├── Component_Instances/
│   ├── Product-Component-AAU-Bottom_Cover-001.json
│   ├── Product-Component-AAU-Top_Cover-001.json
│   ├── Product-Component-AAU-PCB-001.json
│   └── Product-Component-AAU-Fuse-001.json
│   └── Product-Component-AAU-Fuse-002.json
├── Sub_Assembly_Instances/
│   ├── Product-Sub_Assembly-AAU-PCB_With_Fuse-001.json
│   └── Product-Sub_Assembly-AAU-Housing_With_PCB-001.json
└── Final_Product_Instances/
    └── Product-Final_Product-Telefon-Telefon_Pro_Max-001.json
```

### Submodel Files
```
JSON_Submodels/Product_Submodels_JSON/Instances/
├── Component_Instance_Submodels/
│   ├── Product-Component-AAU-*-001-Properties.json
│   ├── Product-Component-AAU-*-001-Documentation.json
│   └── Product-Component-AAU-*-001-Bill_Of_Processes.json
├── Sub_Assembly_Instance_Submodels/
│   ├── Product-Sub_Assembly-AAU-*-001-Properties.json
│   ├── Product-Sub_Assembly-AAU-*-001-Documentation.json
│   ├── Product-Sub_Assembly-AAU-*-001-Bill_Of_Materials.json
│   └── Product-Sub_Assembly-AAU-*-001-Bill_Of_Processes.json
└── Final_Product_Instance_Submodels/
    ├── Product-Final_Product-Telefon-Telefon_Pro_Max-001-Properties.json
    ├── Product-Final_Product-Telefon-Telefon_Pro_Max-001-Documentation.json
    ├── Product-Final_Product-Telefon-Telefon_Pro_Max-001-Bill_Of_Materials.json
    └── Product-Final_Product-Telefon-Telefon_Pro_Max-001-Bill_Of_Processes.json
```

---

## Instance Registry

The `instance_registry.json` file maintains a record of all created instances:

```json
{
  "description": "Registry tracking all created product instances for ID management",
  "last_updated": "2026-03-03",
  "product_types": {
    "Bottom_Cover": {
      "last_instance_number": 5,
      "instances": [
        {
          "instance_number": "001",
          "instance_id": "https://example.com/Telefon/001/Bottom_Cover",
          "created_date": "2026-03-03",
          "configuration": { ... },
          "notes": "Created by configurator_v2"
        }
      ]
    }
  }
}
```

---

## Examples

### Example 1: Create a Single Instance Interactively

```powershell
cd Telefon-Produktion
python configurator_v2.py --interactive
```

### Example 2: Create Multiple Instances from Config Files

```powershell
# Create from example_order.json
python configurator_v2.py --config example_order.json

# Create from custom configuration
python configurator_v2.py --config my_custom_config.json
```

### Example 3: Generate Random Test Data

```powershell
# Create 10 random valid Telefon instances
python configurator_v2.py --generate-random 10
```

### Example 4: Clean Reset for Testing

```powershell
# Completely reset the system (registry + all files)
python configurator_v2.py --reset-registry --delete-instances

# Then generate fresh instances
python configurator_v2.py --generate-random 3
```

---

## How It Works: Template-Driven Architecture

### Type Files (Templates)
- Located in `JSON_Shells/*/Types/` and `JSON_Submodels/*/Types/`
- Contain complete AAS definitions with placeholder IDs following the pattern: `.../Type/...`
- Define the structure, properties, BOM, and processes for each product type

### Instance Generation Process

1. **Load Type File**: Read the Type JSON template (e.g., `Product-Component-AAU-Bottom_Cover-Type.json`)
2. **Deep Copy**: Create an independent copy to avoid modifying the template
3. **ID Transformation**: Replace all `/Type/` placeholders with instance number (e.g., `/001/`)
4. **Patch Fields**: Apply configuration values to properties, BOM quantities, and documentation
5. **Save Instances**: Write the transformed files to the Instances directories
6. **Update Registry**: Record the new instance in `instance_registry.json`

### Benefits
- **No Code Changes**: Update Type files to change product structure
- **Consistency**: All instances follow the same layout from the Type
- **Traceability**: Instance registry tracks every created asset
- **Scalability**: Easily generate dozens or hundreds of instances

---

## Adding a New Product Type

To add a new product type, follow these steps:

1. **Create Type Files**:
   - Add shell: `JSON_Shells/Product_Shells_JSON/Types/[Category]/Product-[Type]-Type.json`
   - Add submodels: `JSON_Submodels/Product_Submodels_JSON/Types/[Category]_Type_Submodels/`

2. **Register Asset Type** in `configurator_v2.py` `ASSET_REGISTRY`:
   ```python
   "MyNewType": {
       "type_shell": "JSON_Shells/Product_Shells_JSON/Types/.../Product-MyNewType-Type.json",
       "type_submodels_dir": "JSON_Submodels/.../MyNewType_Type_Submodels",
       "type_submodel_prefix": "Product-MyNewType",
       "instance_shell_dir": "JSON_Shells/.../Instances/MyNewType_Instances",
       "instance_submodels_dir": "JSON_Submodels/.../MyNewType_Instance_Submodels",
       "instance_file_prefix": "Product-MyNewType",
       "registry_key": "MyNewType",
       "submodels": ["Properties", "Documentation", ...],
       "properties_config_map": { "PropertyName": "config_key", ... },
       "bom_dynamic_quantities": { "BomComponent": "config_key", ... },
   }
   ```

3. **No code changes to `main()` or generation logic** — the registries handle everything!

---

## Troubleshooting

### Error: "Invalid configuration"
- **Cause**: Configuration values violate rules (e.g., incompatible material-finish combo)
- **Solution**: Review `Configuration_Rules` in the configuration template or adjust values

### Error: "Type submodel not found"
- **Cause**: Missing Type JSON file for a registered asset
- **Solution**: Ensure all required submodel Type files exist in the correct directories

### Instance registry out of sync
- **Cause**: Files were manually deleted without updating the registry
- **Solution**: Run `python configurator_v2.py --reset-registry --delete-instances` and regenerate

### File permission errors
- **Cause**: Instance files are read-only or directory permissions are restricted
- **Solution**: Check directory permissions in `JSON_Shells` and `JSON_Submodels`

---

## Contact & Support

For issues or questions about the configurator, refer to the inline code documentation in `configurator_v2.py`.

---

**Last Updated**: 2026-03-03  
**Version**: 2.0
