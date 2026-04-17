"""
Final Product Type definitions.

To add a new final product type: append a new dict to FINAL_PRODUCT_TYPES.
To modify an existing type: edit the relevant dict entry.
No other files need to change.

Each dict fields:
  name                  - unique identifier used in URLs and file names
  family                - product family used in URL path (e.g. "Telefon")
  category              - organisation label (e.g. "AAU")
  product_type          - fixed "Final_Product"
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
      qty_default           - (optional) default quantity
      is_configurable       - True if quantity/variant is configurable per order
      is_configurable_note  - (optional) note explaining configurability
  bop_steps             - list of process step dicts for BOP submodel:
      id_short              - step identifier
      operation             - operation name
      required_components   - list of component reference strings
      constraints           - list of id_short values of prerequisite steps

Note: Final product BOM entries do NOT include Instance_Refference fields
      (those are only on sub-assembly BOMs).
"""

BASE_NS = "https://aausmartlab.com"

FINAL_PRODUCT_TYPES = [
    {
        "name": "Telefon_Pro_Max",
        "family": "Telefon",
        "category": "AAU",
        "product_type": "Final_Product",
        "display_name": "Telefon Pro Max",
        "description": "Complete Telefon Pro Max assembly",
        "model_number_template": (
            "TEL-{bottom_cover_material}-{bottom_cover_color}"
            "-{top_cover_material}-{top_cover_color}-{nr_fuses}F"
        ),
        "properties": [
            {
                "id_short": "Length",
                "value_type": "xs:integer",
                "unit_url": f"{BASE_NS}/Units/Millimeters",
                "description": "Overall length of the phone in millimeters",
            },
            {
                "id_short": "Width",
                "value_type": "xs:integer",
                "unit_url": f"{BASE_NS}/Units/Millimeters",
                "description": "Overall width of the phone in millimeters",
            },
            {
                "id_short": "Height",
                "value_type": "xs:integer",
                "unit_url": f"{BASE_NS}/Units/Millimeters",
                "description": "Overall height of the phone in millimeters",
            },
            {
                "id_short": "Material",
                "value_type": "xs:string",
                "description": "Material used for the housing",
            },
            {
                "id_short": "Color",
                "value_type": "xs:string",
                "description": "Color of the phone housing",
            },
            {
                "id_short": "Nr_Fuses",
                "value_type": "xs:integer",
                "description": "Number of fuses installed in the phone",
            },
        ],
        "bom_components": [
            {
                "id_short": "Bottom_Cover_PCB_Fuse",
                "component_type_url": f"{BASE_NS}/Assets/Product/Sub_Assembly/AAU/Bottom_Cover-PCB-Fuse",
                "description": "Sub assembly of bottom cover with PCB and fuse",
                "semantic_url": f"{BASE_NS}/Sub_Assemblys/Bottom_Cover-PCB-Fuse",
                "qty_min": 1,
                "qty_max": 1,
                "qty_default": 1,
                "is_configurable": False,
                "is_configurable_note": (
                    "This component has configurable options "
                    "(material, color, finish and fuse quantity)"
                ),
            },
            {
                "id_short": "Top_Cover",
                "component_type_url": f"{BASE_NS}/Assets/Product/Component/AAU/Top_Cover",
                "description": "Top housing cover",
                "semantic_url": f"{BASE_NS}/Components/Top_Cover",
                "qty_min": 1,
                "qty_max": 1,
                "qty_default": 1,
                "is_configurable": True,
                "is_configurable_note": (
                    "This component has configurable options (material, color, finish)"
                ),
            },
        ],
        "bop_steps": [
            {
                "id_short": "Assemble_1",
                "operation": "Assemble",
                "required_components": ["Bottom_Cover-PCB-Fuse_1", "Top_Cover_1"],
                "constraints": [],
            },
        ],
    },
]
