"""
Sub-Assembly Type definitions.

To add a new sub-assembly type: append a new dict to SUB_ASSEMBLY_TYPES.
To modify an existing type: edit the relevant dict entry.
No other files need to change.

Each dict fields:
  name                  - unique identifier used in URLs and file names
  category              - organisation label (e.g. "AAU")
  product_type          - fixed "Sub_Assembly"
  display_name          - human-readable name for Documentation submodel
  description           - free-text description for Documentation submodel
  model_number_template - {key} placeholders replaced by order config values
  properties            - list of property dicts for the Properties submodel
                          (same schema as component_types.py)
  bom_components        - list of component/sub-assembly entries for BOM submodel:
      id_short              - identifier used in the BOM collection
      component_type_url    - AAS type ID of the required component
      description           - human-readable description
      semantic_url          - (optional) semantic reference URL
      qty_min               - minimum quantity required
      qty_max               - maximum quantity required
      is_configurable       - True if quantity/variant is configurable per order
      is_configurable_note  - (optional) note explaining configurability
  bop_steps             - list of process step dicts for BOP submodel:
      id_short              - step identifier (e.g. "Assemble_1")
      operation             - operation name (e.g. "Assemble", "Drilling")
      required_components   - list of component reference strings (BOM id_short + "_1")
      constraints           - list of id_short values of steps that must run first
"""

BASE_NS = "https://aausmartlab.com"

SUB_ASSEMBLY_TYPES = [
    {
        "name": "Bottom_Cover-PCB",
        "category": "AAU",
        "product_type": "Sub_Assembly",
        "display_name": "Bottom Cover with PCB",
        "description": "PCB mounted on bottom cover sub-assembly",
        "model_number_template": "BC-PCB-{variant}",
        "properties": [],
        "bom_components": [
            {
                "id_short": "Bottom_Cover",
                "component_type_url": f"{BASE_NS}/Assets/Product/Component/AAU/Bottom_Cover",
                "description": "Bottom housing cover",
                "semantic_url": f"{BASE_NS}/Components/Bottom_Cover",
                "qty_min": 1,
                "qty_max": 1,
                "is_configurable": True,
            },
            {
                "id_short": "PCB",
                "component_type_url": f"{BASE_NS}/Assets/Product/Component/AAU/PCB",
                "description": "PCB",
                "semantic_url": f"{BASE_NS}/SubAssembly/PCB",
                "qty_min": 1,
                "qty_max": 1,
                "is_configurable": False,
                "is_configurable_note": (
                    "This component is not configurable since it is a specific "
                    "PCB design for the bottom cover sub-assembly"
                ),
            },
        ],
        "bop_steps": [
            {
                "id_short": "Drilling_1",
                "operation": "Drilling",
                "required_components": ["Bottom_Cover_1"],
                "constraints": [],
            },
            {
                "id_short": "Assemble_1",
                "operation": "Assemble",
                "required_components": ["PCB_1", "Bottom_Cover_1"],
                "constraints": ["Drilling_1"],
            },
        ],
    },
    {
        "name": "Bottom_Cover-PCB-Fuse",
        "category": "AAU",
        "product_type": "Sub_Assembly",
        "display_name": "Bottom Cover with PCB and Fuse",
        "description": "PCB with fuse(s) mounted on bottom cover sub-assembly",
        "model_number_template": "BC-PCB-F-{nr_fuses}",
        "properties": [
            {
                "id_short": "Nr_Fuses",
                "value_type": "xs:integer",
                "description": "Number of fuses mounted on the PCB",
            },
        ],
        "bom_components": [
            {
                "id_short": "Bottom_Cover_PCB",
                "component_type_url": f"{BASE_NS}/Assets/Product/Sub_Assembly/AAU/Bottom_Cover-PCB",
                "description": "Housing with PCB sub-assembly (from Station 1)",
                "semantic_url": f"{BASE_NS}/Components/Bottom_Cover-PCB",
                "qty_min": 1,
                "qty_max": 1,
                "is_configurable": False,
            },
            {
                "id_short": "Fuse",
                "component_type_url": f"{BASE_NS}/Assets/Product/Component/AAU/Fuse",
                "description": "Electrical fuse",
                "semantic_url": f"{BASE_NS}/Components/Fuse",
                "qty_min": 1,
                "qty_max": 3,
                "is_configurable": True,
                "is_configurable_note": "Quantity is configurable",
            },
        ],
        "bop_steps": [
            {
                "id_short": "Assemble_1",
                "operation": "Assemble",
                "required_components": ["Bottom_Cover-PCB_1", "Fuse_1"],
                "constraints": [],
            },
        ],
    },
]
