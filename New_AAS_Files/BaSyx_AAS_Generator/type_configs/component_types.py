"""
Component Type definitions.

To add a new component type: append a new dict to COMPONENT_TYPES.
To modify an existing type: edit the relevant dict entry.
No other files need to change.

Each dict fields:
  name                  - unique identifier used in URLs and file names
  category              - organisation label (e.g. "AAU")
  product_type          - fixed "Component"
  display_name          - human-readable name stored in Documentation submodel
  description           - free-text description stored in Documentation submodel
  model_number_template - template string for instance model number generation;
                          {key} placeholders are replaced by order config values
  properties            - list of property dicts for the Properties submodel:
      id_short    - property identifier
      value_type  - XSD type string: xs:string | xs:integer | xs:double | xs:boolean
      value       - (optional) default/fixed value; omit or None for instance-filled fields
      unit_url    - (optional) semantic URL for the unit  e.g. .../Units/Millimeters
      description - (optional) short explanation
"""

BASE_NS = "https://aausmartlab.com"

COMPONENT_TYPES = [
    {
        "name": "Bottom_Cover",
        "category": "AAU",
        "product_type": "Component",
        "display_name": "Bottom Cover",
        "description": "Bottom housing cover component - configurable material, color, and finish",
        "model_number_template": "BC-{bottom_cover_material}-{bottom_cover_color}-{bottom_cover_finish}",
        "properties": [
            {
                "id_short": "Length",
                "value_type": "xs:integer",
                "value": 150,
                "unit_url": f"{BASE_NS}/Units/Millimeters",
                "description": "Length in millimeters",
            },
            {
                "id_short": "Width",
                "value_type": "xs:integer",
                "value": 75,
                "unit_url": f"{BASE_NS}/Units/Millimeters",
                "description": "Width in millimeters",
            },
            {
                "id_short": "Height",
                "value_type": "xs:integer",
                "value": 5,
                "unit_url": f"{BASE_NS}/Units/Millimeters",
                "description": "Height in millimeters",
            },
            {
                "id_short": "Material",
                "value_type": "xs:string",
                "description": "Material type - configured at instance creation",
            },
            {
                "id_short": "Color",
                "value_type": "xs:string",
                "description": "Color - configured at instance creation",
            },
            {
                "id_short": "Finish",
                "value_type": "xs:string",
                "description": "Surface finish - configured at instance creation",
            },
        ],
    },
    {
        "name": "Fuse",
        "category": "AAU",
        "product_type": "Component",
        "display_name": "Fuse",
        "description": "Electrical fuse component",
        "model_number_template": "FUSE-{fuse_type}-{fuse_current_rating}A",
        "properties": [
            {
                "id_short": "Voltage_Rating",
                "value_type": "xs:integer",
                "value": 250,
                "unit_url": f"{BASE_NS}/Units/Volts",
                "description": "Maximum voltage rating in volts",
            },
            {
                "id_short": "Current_Rating",
                "value_type": "xs:double",
                "value": 5.0,
                "unit_url": f"{BASE_NS}/Units/Amperes",
                "description": "Current rating in amperes",
            },
            {
                "id_short": "Type",
                "value_type": "xs:string",
                "value": "Fast-acting",
                "description": "Fuse type (e.g., fast-acting, slow-blow)",
            },
        ],
    },
    {
        "name": "PCB",
        "category": "AAU",
        "product_type": "Component",
        "display_name": "PCB",
        "description": "Printed circuit board for bottom cover sub-assembly",
        "model_number_template": "PCB-{pcb_variant}",
        "properties": [
            {
                "id_short": "Length",
                "value_type": "xs:integer",
                "value": 140,
                "unit_url": f"{BASE_NS}/Units/Millimeters",
                "description": "Length in millimeters",
            },
            {
                "id_short": "Width",
                "value_type": "xs:integer",
                "value": 55,
                "unit_url": f"{BASE_NS}/Units/Millimeters",
                "description": "Width in millimeters",
            },
            {
                "id_short": "Layers",
                "value_type": "xs:integer",
                "value": 2,
                "description": "Number of PCB layers",
            },
        ],
    },
    {
        "name": "Top_Cover",
        "category": "AAU",
        "product_type": "Component",
        "display_name": "Top Cover",
        "description": "Top housing cover component - configurable material, color, and finish",
        "model_number_template": "TC-{top_cover_material}-{top_cover_color}-{top_cover_finish}",
        "properties": [
            {
                "id_short": "Length",
                "value_type": "xs:integer",
                "value": 150,
                "unit_url": f"{BASE_NS}/Units/Millimeters",
                "description": "Length in millimeters",
            },
            {
                "id_short": "Width",
                "value_type": "xs:integer",
                "value": 75,
                "unit_url": f"{BASE_NS}/Units/Millimeters",
                "description": "Width in millimeters",
            },
            {
                "id_short": "Height",
                "value_type": "xs:integer",
                "value": 3,
                "unit_url": f"{BASE_NS}/Units/Millimeters",
                "description": "Height in millimeters",
            },
            {
                "id_short": "Material",
                "value_type": "xs:string",
                "description": "Material type - configured at instance creation",
            },
            {
                "id_short": "Color",
                "value_type": "xs:string",
                "description": "Color - configured at instance creation",
            },
            {
                "id_short": "Finish",
                "value_type": "xs:string",
                "description": "Surface finish - configured at instance creation",
            },
        ],
    },
]
