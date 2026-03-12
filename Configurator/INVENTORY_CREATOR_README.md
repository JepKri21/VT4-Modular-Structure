# Inventory Creator - User Guide

## Overview
The **Inventory Creator** is a tool that allows you to generate component instances based on predefined type templates. Instead of creating complete products (like a Telefon), you can now quickly populate inventory with individual component instances.

## Features
- ✅ Select component type (Bottom Cover, Top Cover, PCB, Fuse)
- ✅ Specify quantity to create
- ✅ Configure component properties (Material, Color, Finish) 
- ✅ Automatic asset ID generation (unique, sequential numbering)
- ✅ Generate complete AAS shell and submodel files
- ✅ Automatic timestamp tracking (Created_Date)
- ✅ Type-driven template system (changes to types automatically flow to instances)

## How to Use

### Running the Program

```bash
python inventory_creator.py
```

### Interactive Steps

1. **Select Component Type**
   - Choose from: Bottom_Cover, Top_Cover, PCB, Fuse
   - Enter the number (1-4)

2. **Specify Quantity**
   - Enter how many instances to create
   - Values must be positive (e.g., 20)

3. **Configure Properties** (if applicable)
   - Some components have configurable properties:
     - **Bottom_Cover**: Material, Color, Finish
     - **Top_Cover**: Material, Color, Finish
     - **PCB**: No properties
     - **Fuse**: No properties
   - Examples:
     - Material: ABS, Plastic, Steel
     - Color: black, white, red, blue
     - Finish: matte, glossy, textured

4. **Confirm and Create**
   - Review the summary
   - Type "yes" or "y" to proceed
   - Files are generated immediately

## Output Structure

### Generated Files
For each instance, the tool creates:

1. **Shell File** (AAS)
   - Location: `JSON_Shells/Product_Shells_JSON/Instances/Component_Instances/`
   - Format: `Product-Component-AAU-{Type}-{Number}.json`

2. **Submodel Files**
   - Location: `JSON_Submodels/Product_Submodels_JSON/Instances/Component_Instance_Submodels/`
   - Files created:
     - `Product-Component-AAU-{Type}-{Number}-Documentation.json`
     - `Product-Component-AAU-{Type}-{Number}-Properties.json`
     - `Product-Component-AAU-{Type}-{Number}-Bill_Of_Processes.json`

### Example
Creating 3 instances of Bottom_Cover with Material=ABS, Color=black, Finish=matte generates:

- Keys: 012, 013, 014
- Documentation: Instance numbers and creation date filled in
- Properties: Configured values populated (Material, Color, Finish)
- Bill_Of_Processes: Inherited from type

## Auto-Numbering Logic

The tool automatically detects the highest existing instance number and increments from there:

- Existing: Bottom_Cover-001 through Bottom_Cover-011 → Next: 012
- Separate counters per component type
- No gaps or duplicates

## File Structure Details

### Properties Submodel Example (Bottom_Cover)
```json
{
  "idShort": "Properties",
  "id": "https://aausmartlab.com/Assets/Product/Component/AAU/Bottom_Cover/012/Properties",
  "submodelElements": [
    {
      "idShort": "Material",
      "value": "ABS"  // ← Configured at creation
    },
    {
      "idShort": "Color",
      "value": "black"  // ← Configured at creation
    },
    {
      "idShort": "Finish",
      "value": "matte"  // ← Configured at creation
    }
  ]
}
```

### Documentation Submodel Example
```json
{
  "idShort": "Documentation",
  "submodelElements": [
    {
      "idShort": "Instance_Number",
      "value": "012"  // ← Auto-populated
    },
    {
      "idShort": "Created_Date",
      "value": "2026-03-03"  // ← Current date
    }
  ]
}
```

## Asset Type Registry

The tool uses a registry that maps component types to their corresponding files:

```python
COMPONENT_REGISTRY = {
    "Bottom_Cover": {
        "type_shell": "JSON_Shells/Product_Shells_JSON/Types/Component_Types/...",
        "instance_shell_dir": "JSON_Shells/Product_Shells_JSON/Instances/Component_Instances/",
        "properties_config_map": {
            "Material": "bottom_cover_material",
            "Color": "bottom_cover_color",
            "Finish": "bottom_cover_finish",
        },
    },
    ...
}
```

## Adding New Component Types

To add a new component type:

1. Create Type files:
   - `JSON_Shells/Product_Shells_JSON/Types/Component_Types/Product-Component-AAU-{Name}-Type.json`
   - Type submodels in `JSON_Submodels/Product_Submodels_JSON/Types/Component_Type_Submodels/`

2. Add entry to `COMPONENT_REGISTRY` in `inventory_creator.py`:
   ```python
   "NewType": {
       "type_shell": "path/to/Type/shell",
       "type_submodels_dir": "path/to/Type/submodels",
       "type_submodel_prefix": "Product-Component-AAU-NewType",
       "instance_shell_dir": "JSON_Shells/...",
       "instance_submodels_dir": "JSON_Submodels/...",
       "instance_file_prefix": "Product-Component-AAU-NewType",
       "submodels": ["Documentation", "Properties", "Bill_Of_Processes"],
       "properties_config_map": {
           "PropertyName": "config_key",
       },
   }
   ```

3. Run the tool—no other code changes needed!

## Testing

Run the included test script:

```bash
python test_inventory_creator.py
```

This will:
- Create 2 Bottom_Cover instances with configuration
- Create 3 Fuse instances (no configuration)
- Create 2 PCB instances
- Verify next instance numbers for each type

## Troubleshooting

### Issue: "File not found" error
- Ensure you're running from the Configurator folder
- Check that all type files exist in `JSON_Shells/` and `JSON_Submodels/`

### Issue: Duplicate instance numbers
- This shouldn't happen—the tool scans existing files
- If it occurs, manually adjust Type file paths in COMPONENT_REGISTRY

### Issue: Properties not getting configured
- Check that the property name matches the Type definition
- Verify the property exists in the Type's Properties submodel

## Future Enhancements

Potential improvements:
- [ ] Batch import from CSV/Excel
- [ ] GUI interface (tkinter/PyQt)
- [ ] Default configuration profiles
- [ ] Inventory metadata (warehouse location, batch number)
- [ ] Integration with instance_registry.json
- [ ] Export to different formats (CSV, XML)

---

**Version**: 1.0  
**Updated**: 2026-03-03
