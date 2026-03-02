"""
Telefon Product Configurator

This script generates configured Telefon product instances from the Type templates
and Configuration_Template, creating all necessary AAS shells and submodels.

Usage:
    python configurator.py --config order_config.json
    python configurator.py --interactive
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List
import copy
import random


class TelefonConfigurator:
    """Main configurator class for generating Telefon product instances."""
    
    def __init__(self, base_path: str):
        """Initialize configurator with base workspace path."""
        self.base_path = Path(base_path)
        self.registry_path = self.base_path / "instance_registry.json"
        self.config_template_path = self.base_path / "JSON_Submodels" / "Product_Submodels_JSON" / "Final_Product_Submodels" / "Product-Final_Product-Telefon-Telefon_Pro_Max-Configuration_Template.json"
        
        # Define paths for Type definitions
        self.type_paths = {
            "Telefon": self.base_path / "JSON_Shells" / "Product_Shells_JSON" / "Types" / "Final_Product_Types" / "Product-Final_Product-AAU-Telefon-Type.json",
            "Bottom_Cover": self.base_path / "JSON_Shells" / "Product_Shells_JSON" / "Types" / "Component_Types" / "Product-Component-AAU-Bottom_Cover-Type.json",
            "Top_Cover": self.base_path / "JSON_Shells" / "Product_Shells_JSON" / "Types" / "Component_Types" / "Product-Component-AAU-Top_Cover-Type.json",
            "PCB": self.base_path / "JSON_Shells" / "Product_Shells_JSON" / "Types" / "Component_Types" / "Product-Component-AAU-PCB-Type.json",
            "Fuse": self.base_path / "JSON_Shells" / "Product_Shells_JSON" / "Types" / "Component_Types" / "Product-Component-AAU-Fuse-Type.json",
            "PCB_With_Fuse": self.base_path / "JSON_Shells" / "Product_Shells_JSON" / "Types" / "Sub_Assembly_Types" / "Product-Sub_Assembly-AAU-PCB_With_Fuse-Type.json",
            "Housing_With_PCB": self.base_path / "JSON_Shells" / "Product_Shells_JSON" / "Types" / "Sub_Assembly_Types" / "Product-Sub_Assembly-AAU-Housing_With_PCB-Type.json",
        }
        
        # Load registry
        self.registry = self._load_registry()
        
        # Load configuration template
        self.config_template = self._load_config_template()
    
    def _load_registry(self) -> Dict[str, Any]:
        """Load the instance registry."""
        with open(self.registry_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _save_registry(self):
        """Save the updated instance registry."""
        with open(self.registry_path, 'w', encoding='utf-8') as f:
            json.dump(self.registry, f, indent=2, ensure_ascii=False)
    
    def _load_config_template(self) -> Dict[str, Any]:
        """Load the configuration template."""
        with open(self.config_template_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _load_type_submodel(self, product_type: str, submodel_type: str) -> Dict[str, Any]:
        """Load a Type submodel (Properties, BOM, Documentation, BOP)."""
        submodel_paths = {
            "Telefon": {
                "Properties": "Product-Final_Product-Telefon-Telefon_Pro_Max-Type-Properties.json",
                "Bill_Of_Materials": "Product-Final_Product-Telefon-Telefon_Pro_Max-Type-Bill_Of_Materials.json",
                "Documentation": "Product-Final_Product-Telefon-Telefon_Pro_Max-Type-Documentation.json",
                "Bill_Of_Processes": "Product-Final_Product-Telefon-Telefon_Pro_Max-Type-Bill_Of_Processes.json",
            },
            "Bottom_Cover": {
                "Properties": "Product-Component-AAU-Bottom_Cover-Type-Properties.json",
                "Documentation": "Product-Component-AAU-Bottom_Cover-Type-Documentation.json",
                "Bill_Of_Processes": "Product-Component-AAU-Bottom_Cover-Type-Bill_Of_Processes.json",
            },
            "Top_Cover": {
                "Properties": "Product-Component-AAU-Top_Cover-Type-Properties.json",
                "Documentation": "Product-Component-AAU-Top_Cover-Type-Documentation.json",
                "Bill_Of_Processes": "Product-Component-AAU-Top_Cover-Type-Bill_Of_Processes.json",
            },
            "PCB": {
                "Properties": "Product-Component-AAU-PCB-Type-PropeFties.json",
                "Documentation": "Product-Component-AAU-PCB-Type-DocumentatiFon.json",
                "Bill_Of_Processes": "Product-Component-AAU-PCB-Type-Bill_Of_Processes.json",
            },
            "Fuse": {
                "Properties": "Product-Component-AAU-Fuse-Type-Properties.json",
                "Documentation": "Product-Component-AAU-Fuse-Type-Documentation.json",
                "Bill_Of_Processes": "Product-Component-AAU-Fuse-Type-Bill_Of_Processes.json",
            },
            "PCB_With_Fuse": {
                "Properties": "Product-Sub_Assembly-AAU-PCB_With_Fuse-Type-Properties.json",
                "Bill_Of_Materials": "Product-Sub_Assembly-AAU-PCB_With_Fuse-Type-Bill_Of_Materials.json",
                "Documentation": "Product-Sub_Assembly-AAU-PCB_With_Fuse-Type-Documentation.json",
                "Bill_Of_Processes": "Product-Sub_Assembly-AAU-PCB_With_Fuse-Type-Bill_Of_Processes.json",
            },
            "Housing_With_PCB": {
                "Properties": "Product-Sub_Assembly-AAU-Housing_With_PCB-Type-Properties.json",
                "Bill_Of_Materials": "Product-Sub_Assembly-AAU-Housing_With_PCB-Type-Bill_Of_Materials.json",
                "Documentation": "Product-Sub_Assembly-AAU-Housing_With_PCB-Type-Documentation.json",
                "Bill_Of_Processes": "Product-Sub_Assembly-AAU-Housing_With_PCB-Type-Bill_Of_Processes.json",
            },
        }
        
        # Determine folder based on product type
        if product_type == "Telefon":
            folder = "Types/Final_Product_Type_Submodels"
        elif product_type in ["PCB_With_Fuse", "Housing_With_PCB"]:
            folder = "Types/Sub_Assembly_Type_Submodels"
        else:
            folder = "Types/Component_Type_Submodels"
        
        filename = submodel_paths.get(product_type, {}).get(submodel_type)
        if not filename:
            return None
        
        path = self.base_path / "JSON_Submodels" / "Product_Submodels_JSON" / folder / filename
        
        if not path.exists():
            return None
        
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _get_type_properties_with_values(self, product_type: str, config_overrides: Dict[str, str] = None) -> list:
        """Get properties from Type submodel with configured values applied.
        
        Args:
            product_type: The product type (e.g., "Bottom_Cover", "PCB")
            config_overrides: Dictionary of property overrides (e.g., {"Material": "ABS-5500", "Color": "Blue"})
            
        Returns:
            List of property elements with values
        """
        type_properties = self._load_type_submodel(product_type, "Properties")
        if not type_properties:
            return []
        
        # Get the property list from Type submodel
        property_list = copy.deepcopy(type_properties['submodelElements'][0]['value'])
        
        # Apply configuration overrides
        if config_overrides:
            for prop in property_list:
                if prop['idShort'] in config_overrides:
                    prop['value'] = config_overrides[prop['idShort']]
        
        return property_list
    
    def _get_type_bill_of_processes(self, product_type: str, instance_id: str) -> Dict[str, Any]:
        """Build a Bill_Of_Processes instance submodel matching the Example format.

        Uses List_Of_Processes with Process_Id, Execution_Constraints and Parameters
        for each asset type's main process.

        Args:
            product_type: The product type (e.g., "Bottom_Cover", "PCB")
            instance_id: The instance ID to use in the BOP

        Returns:
            Complete Bill_Of_Processes submodel in List_Of_Processes format
        """
        # --- Define main process steps per asset type ---
        def _assemble_step(process_id: str, constraints: List[str], selected_operation: str) -> Dict:
            return {
                "modelType": "SubmodelElementCollection",
                "idShort": "Assemble",
                "semanticId": {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": "https://aausmartlab.com/Operations/Assemble"}]},
                "description": [{"language": "en", "text": "List of parameters to perform Assemble process."}],
                "value": [
                    {"modelType": "Property", "idShort": "Process_Id", "valueType": "xs:string", "value": process_id},
                    {
                        "modelType": "SubmodelElementCollection",
                        "idShort": "Execution_Constraints",
                        "value": [
                            {"modelType": "Property", "idShort": "Constraint_Id", "valueType": "xs:string", "value": c}
                            for c in constraints
                        ]
                    },
                    {
                        "modelType": "SubmodelElementCollection",
                        "idShort": "Parameters",
                        "value": [
                            {"modelType": "Property", "idShort": "Selected_Operation", "valueType": "xs:string", "value": selected_operation}
                        ]
                    }
                ]
            }

        process_steps_map = {
            "Bottom_Cover": [
                {
                    "modelType": "SubmodelElementCollection",
                    "idShort": "Drilling",
                    "semanticId": {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": "https://aausmartlab.com/Operations/Drilling"}]},
                    "description": [{"language": "en", "text": "List of parameters to perform Drilling process."}],
                    "value": [
                        {"modelType": "Property", "idShort": "Process_Id", "valueType": "xs:string", "value": "Drilling_1"},
                        {
                            "modelType": "SubmodelElementCollection",
                            "idShort": "Execution_Constraints",
                            "value": [
                                {"modelType": "Property", "idShort": "Constraint_Id", "valueType": "xs:string", "value": ""}
                            ]
                        },
                        {
                            "modelType": "SubmodelElementCollection",
                            "idShort": "Parameters",
                            "value": [
                                {"modelType": "Property", "idShort": "Component_Type", "valueType": "xs:string", "value": "https://aausmartlab.com/Asset/Product/Component/AAU/Bottom_Cover"},
                                {"modelType": "Property", "idShort": "Selected_Operation", "valueType": "xs:string", "value": "Bottom_Cover_Operation_1"}
                            ]
                        }
                    ]
                }
            ],
            "Top_Cover": [{}],
            "PCB": [{}],
            "Fuse": [{}],
            "PCB_With_Fuse": [
                _assemble_step(
                    "Assemble_1",
                    [
                        "https://aausmartlab.com/Assets/Product/Component/AAU/Fuse",
                        "https://aausmartlab.com/Assets/Product/Sub_Assembly/AAU/Housing_With_PCB"
                    ],
                    "Assemble_Housing_With_PCB"
                )
            ],
            "Housing_With_PCB": [
                _assemble_step(
                    "Assemble_1",
                    [
                        "https://aausmartlab.com/Assets/Product/Component/AAU/Bottom_Cover",
                        "https://aausmartlab.com/Assets/Product/Component/AAU/PCB"
                    ],
                    "Assemble_Housing_With_PCB"
                )
            ],
            "Telefon": [
                _assemble_step(
                    "Assemble_1",
                    [
                        "https://aausmartlab.com/Assets/Product/Sub_Assembly/AAU/PCB_With_Fuse",
                        "https://aausmartlab.com/Assets/Product/Component/AAU/Top_Cover"
                    ],
                    "Assemble_Final_Telefon"
                )
            ],
        }

        process_steps = process_steps_map.get(product_type, [{}])

        return {
            "idShort": "Bill_Of_Processes",
            "semanticId": {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": "https://aausmartlab.com/Data/BillOfOperations"}]},
            "id": f"{instance_id}/Bill_Of_Processes",
            "description": [{"language": "en", "text": "List of manufacturing and assembly operations for the product."}],
            "submodelElements": [
                {
                    "modelType": "SubmodelElementList",
                    "idShort": "List_Of_Processes",
                    "semanticId": {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": "https://aausmartlab.com/Submodel/Bill/List_Of_Processes"}]},
                    "typeValueListElement": "SubmodelElementCollection",
                    "valueTypeListElement": None,
                    "orderRelevant": True,
                    "description": [{"language": "en", "text": "Ordered list of operations required to manufacture and assemble the product."}],
                    "value": process_steps
                }
            ]
        }
    
    def get_next_instance_number(self, product_type: str) -> str:
        """Get the next available instance number for a product type."""
        if product_type not in self.registry['product_types']:
            # Initialize new product type in registry
            self.registry['product_types'][product_type] = {
                "last_instance_number": 0,
                "instances": []
            }
        
        next_num = self.registry['product_types'][product_type]['last_instance_number'] + 1
        return f"{next_num:03d}"
    
    def validate_configuration(self, config: Dict[str, Any]) -> tuple[bool, List[str]]:
        """Validate a configuration against the template and rules."""
        errors = []
        
        # Extract available options from template
        configurable_components = None
        for elem in self.config_template.get('submodelElements', []):
            if elem.get('idShort') == 'Configurable_Components':
                configurable_components = elem
                break
        
        if not configurable_components:
            errors.append("Configuration template missing Configurable_Components")
            return False, errors
        
        # Get configuration rules from template
        config_rules = {}
        material_finish_incompatible = []  # List of (material, finish) tuples that are incompatible
        
        for submodel_element in self.config_template.get('submodelElements', []):
            if submodel_element.get('idShort') == 'Configuration_Rules':
                for rule in submodel_element.get('value', []):
                    rule_id = rule.get('idShort')
                    if rule_id == 'Material_Finish_Compatibility':
                        # Extract incompatible material-finish combinations
                        for incompatibility in rule.get('value', []):
                            material = None
                            finish = None
                            for prop in incompatibility.get('value', []):
                                if prop.get('idShort') == 'Incompatible_Material':
                                    material = prop.get('value')
                                elif prop.get('idShort') == 'Incompatible_Finish':
                                    finish = prop.get('value')
                            if material and finish:
                                material_finish_incompatible.append((material, finish))
                    else:
                        config_rules[rule_id] = rule.get('value')
        
        # Validate material-finish compatibility for bottom cover
        if 'bottom_cover_material' in config and 'bottom_cover_finish' in config:
            combo = (config['bottom_cover_material'], config['bottom_cover_finish'])
            if combo in material_finish_incompatible:
                errors.append(f"Invalid combination: {combo[0]} cannot be {combo[1]}")
        
        # Validate material-finish compatibility for top cover
        if 'top_cover_material' in config and 'top_cover_finish' in config:
            combo = (config['top_cover_material'], config['top_cover_finish'])
            if combo in material_finish_incompatible:
                errors.append(f"Invalid combination: {combo[0]} cannot be {combo[1]}")
        
        # Extract fuse limits from previously loaded config_rules
        min_fuses = int(config_rules.get('Minimum_Fuses', 1))
        max_fuses = int(config_rules.get('Maximum_Fuses', 3))
        
        # Validate fuse count
        if 'number_of_fuses' in config:
            fuse_count = config['number_of_fuses']
            if not isinstance(fuse_count, int) or fuse_count < min_fuses or fuse_count > max_fuses:
                errors.append(f"Invalid number_of_fuses: {fuse_count}. Must be between {min_fuses} and {max_fuses}")
        
        return len(errors) == 0, errors
    
    def create_telefon_instance(self, config: Dict[str, Any]) -> Dict[str, str]:
        """
        Create a complete Telefon instance with all submodels and components.
        
        Args:
            config: Configuration dictionary with keys like:
                - bottom_cover_material
                - bottom_cover_color
                - bottom_cover_finish
                - top_cover_material
                - top_cover_color
                - top_cover_finish
                - number_of_fuses
        
        Returns:
            Dictionary with created instance IDs
        """
        # Validate configuration
        is_valid, errors = self.validate_configuration(config)
        if not is_valid:
            raise ValueError(f"Invalid configuration: {', '.join(errors)}")
        
        # Get next instance number
        instance_num = self.get_next_instance_number("Telefon_Pro_Max")
        
        print(f"\n=== Creating Telefon Instance {instance_num} ===")
        print(f"Configuration: {json.dumps(config, indent=2)}")
        
        # Create all instances
        created_instances = {}
        
        # 1. Create component instances
        bottom_cover_id = self._create_bottom_cover_instance(instance_num, config)
        created_instances['Bottom_Cover'] = bottom_cover_id
        
        top_cover_id = self._create_top_cover_instance(instance_num, config)
        created_instances['Top_Cover'] = top_cover_id
        
        pcb_id = self._create_pcb_instance(instance_num, config)
        created_instances['PCB'] = pcb_id
        
        fuse_ids = self._create_fuse_instances(instance_num, config)
        created_instances['Fuses'] = fuse_ids
        
        # 2. Create sub-assembly instances
        pcb_with_fuse_id = self._create_pcb_with_fuse_instance(instance_num, config, pcb_id, fuse_ids)
        created_instances['PCB_With_Fuse'] = pcb_with_fuse_id
        
        housing_with_pcb_id = self._create_housing_with_pcb_instance(instance_num, config, bottom_cover_id, pcb_with_fuse_id)
        created_instances['Housing_With_PCB'] = housing_with_pcb_id
        
        # 3. Create Telefon shell and submodels
        telefon_id = self._create_telefon_shell(instance_num)
        created_instances['Telefon'] = telefon_id
        
        self._create_telefon_properties(instance_num, config)
        self._create_telefon_bom(instance_num, config)
        self._create_telefon_bill_of_processes(instance_num, config)
        self._create_telefon_documentation(instance_num)
        
        # 4. Update registry
        self._update_registry("Telefon_Pro_Max", instance_num, config, telefon_id)
        
        print(f"\n✓ Successfully created Telefon instance {instance_num}")
        print(f"  Instance ID: {telefon_id}")
        
        return created_instances
    
    def _create_telefon_shell(self, instance_num: str) -> str:
        """Create the Telefon AAS shell."""
        instance_id = f"https://aausmartlab.com/Assets/Product/Final_Product/Telefon/Telefon_Pro_Max/{instance_num}"
        
        shell = {
            "idShort": "Telefon",
            "id": instance_id,
            "modelType": "AssetAdministrationShell",
            "assetInformation": {
                "assetKind": "Instance",
                "globalAssetId": f"https://aausmartlab.com/Assets/Product/AAU/Telefon/{instance_num}"
            },
            "submodels": [
                {
                    "type": "ModelReference",
                    "keys": [{
                        "type": "Submodel",
                        "value": f"{instance_id}/Documentation"
                    }]
                },
                {
                    "type": "ModelReference",
                    "keys": [{
                        "type": "Submodel",
                        "value": f"{instance_id}/Bill_Of_Processes"
                    }]
                },
                {
                    "type": "ModelReference",
                    "keys": [{
                        "type": "Submodel",
                        "value": f"{instance_id}/Bill_Of_Materials"
                    }]
                },
                {
                    "type": "ModelReference",
                    "keys": [{
                        "type": "Submodel",
                        "value": f"{instance_id}/Properties"
                    }]
                }
            ]
        }
        
        # Save shell
        output_path = self.base_path / "JSON_Shells" / "Product_Shells_JSON" / "Instances" / "Final_Product_Instances" / f"Product-Final_Product-AAU-Telefon-{instance_num}.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(shell, f, indent=2, ensure_ascii=False)
        
        print(f"  ✓ Created Telefon shell: {output_path.name}")
        return instance_id
    
    def _create_telefon_properties(self, instance_num: str, config: Dict[str, Any]):
        """Create the Telefon Properties submodel with configured values."""
        instance_id = f"https://aausmartlab.com/Assets/Product/Final_Product/Telefon/Telefon_Pro_Max/{instance_num}"
        
        properties = {
            "idShort": "Properties",
            "semanticId": {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": "https://aausmartlab.com/Data/Parts/Variants"}]},
            "id": f"{instance_id}/Properties",
            "description": [{"language": "en", "text": "Properties for this Telefon instance"}],
            "submodelElements": [
                {
                    "modelType": "SubmodelElementList",
                    "idShort": "List_Of_Properties",
                    "semanticId": {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": "https://aausmartlab.com/Submodels/List_Of_Properties"}]},
                    "typeValueListElement": "SubmodelElementCollection",
                    "valueTypeListElement": None,
                    "orderRelevant": True,
                    "description": [{"language": "en", "text": "List of properties of this Telefon instance"}],
                    "value": [
                        {
                            "modelType": "Property",
                            "idShort": "Length",
                            "valueType": "xs:integer",
                            "value": "150",
                            "semanticId": {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": "https://aausmartlab.com/Units/Millimeters"}]}
                        },
                        {
                            "modelType": "Property",
                            "idShort": "Width",
                            "valueType": "xs:integer",
                            "value": "60",
                            "semanticId": {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": "https://aausmartlab.com/Units/Millimeters"}]}
                        },
                        {
                            "modelType": "Property",
                            "idShort": "Height",
                            "valueType": "xs:integer",
                            "value": "12",
                            "semanticId": {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": "https://aausmartlab.com/Units/Millimeters"}]}
                        },
                        {
                            "modelType": "Property",
                            "idShort": "Material",
                            "valueType": "xs:string",
                            "value": config.get('bottom_cover_material', 'PLA-31212'),
                            "semanticId": {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": f"https://aausmartlab.com/Materials/{config.get('bottom_cover_material', 'PLA-31212')}"}]}
                        },
                        {
                            "modelType": "Property",
                            "idShort": "Color",
                            "valueType": "xs:string",
                            "value": config.get('bottom_cover_color', 'Red'),
                            "semanticId": {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": f"https://aausmartlab.com/Colors/{config.get('bottom_cover_color', 'Red')}"}]}
                        },
                        {
                            "modelType": "Property",
                            "idShort": "Nr_Fuses",
                            "valueType": "xs:integer",
                            "value": str(config.get('number_of_fuses', 1))
                        }
                    ]
                }
            ]
        }
        
        # Save properties
        output_path = self.base_path / "JSON_Submodels" / "Product_Submodels_JSON" / "Instances" / "Final_Product_Instance_Submodels" / f"Product-Final_Product-Telefon-Telefon_Pro_Max-{instance_num}-Properties.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(properties, f, indent=2, ensure_ascii=False)
        
        print(f"  ✓ Created Properties submodel: {output_path.name}")
    
    def _create_telefon_bom(self, instance_num: str, config: Dict[str, Any]):
        """Create the Telefon Bill of Materials submodel."""
        instance_id = f"https://aausmartlab.com/Assets/Product/Final_Product/Telefon/Telefon_Pro_Max/{instance_num}"
        
        bom = {
            "idShort": "Bill_Of_Materials",
            "semanticId": {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": "https://aausmartlab.com/Data/Bill_Of_Materials"}]},
            "id": f"{instance_id}/Bill_Of_Materials",
            "description": [{"language": "en", "text": "List of materials required to produce this Telefon instance"}],
            "submodelElements": [
                {
                    "modelType": "SubmodelElementList",
                    "idShort": "List_Of_Materials",
                    "semanticId": {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": "https://aausmartlab.com/Data/ListOfMaterials"}]},
                    "typeValueListElement": "SubmodelElementCollection",
                    "valueTypeListElement": None,
                    "orderRelevant": True,
                    "description": [{"language": "en", "text": "Collection of all parts in the product"}],
                    "value": [
                        {
                            "modelType": "SubmodelElementCollection",
                            "idShort": "Bottom_Cover_1",
                            "value": [
                                {
                                    "modelType": "Property",
                                    "idShort": "Component_Variant",
                                    "valueType": "xs:string",
                                    "value": "https://aausmartlab.com/Assets/Product/Component/AAU/Bottom_Cover"
                                }
                            ]
                        },
                        {
                            "modelType": "SubmodelElementCollection",
                            "idShort": "Top_Cover_1",
                            "value": [
                                {
                                    "modelType": "Property",
                                    "idShort": "Component_Variant",
                                    "valueType": "xs:string",
                                    "value": "https://aausmartlab.com/Assets/Product/Component/AAU/Top_Cover"
                                }
                            ]
                        },
                        {
                            "modelType": "SubmodelElementCollection",
                            "idShort": "PCB_With_Fuse_1",
                            "value": [
                                {
                                    "modelType": "Property",
                                    "idShort": "Component_Variant",
                                    "valueType": "xs:string",
                                    "value": "https://aausmartlab.com/Assets/Product/Sub_Assembly/AAU/PCB_With_Fuse"
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        
        # Save BOM
        output_path = self.base_path / "JSON_Submodels" / "Product_Submodels_JSON" / "Instances" / "Final_Product_Instance_Submodels" / f"Product-Final_Product-Telefon-Telefon_Pro_Max-{instance_num}-Bill_Of_Materials.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(bom, f, indent=2, ensure_ascii=False)
        
        print(f"  ✓ Created Bill_Of_Materials submodel: {output_path.name}")
    
    def _create_telefon_bill_of_processes(self, instance_num: str, config: Dict[str, Any]):
        """Create the Telefon Bill_Of_Processes submodel."""
        instance_id = f"https://aausmartlab.com/Assets/Product/Final_Product/Telefon/Telefon_Pro_Max/{instance_num}"
        
        # Load Process_Categories from Telefon Type
        bop = self._get_type_bill_of_processes("Telefon", instance_id)
        
        # Save Bill_Of_Processes
        output_path = self.base_path / "JSON_Submodels" / "Product_Submodels_JSON" / "Instances" / "Final_Product_Instance_Submodels" / f"Product-Final_Product-Telefon-Telefon_Pro_Max-{instance_num}-Bill_Of_Processes.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(bop, f, indent=2, ensure_ascii=False)
        
        print(f"  ✓ Created Bill_Of_Processes submodel: {output_path.name}")
    
    def _create_telefon_documentation(self, instance_num: str):
        """Create the Telefon Documentation submodel."""
        instance_id = f"https://aausmartlab.com/Assets/Product/Final_Product/Telefon/Telefon_Pro_Max/{instance_num}"
        
        doc = {
            "idShort": "Documentation",
            "semanticId": {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": "https://aausmartlab.com/Data/Documentation"}]},
            "id": f"{instance_id}/Documentation",
            "description": [{"language": "en", "text": f"Documentation for Telefon instance {instance_num}"}],
            "submodelElements": [
                {
                    "modelType": "Property",
                    "idShort": "Product_Name",
                    "valueType": "xs:string",
                    "value": "Telefon Pro Max"
                },
                {
                    "modelType": "Property",
                    "idShort": "Instance_Number",
                    "valueType": "xs:string",
                    "value": instance_num
                },
                {
                    "modelType": "Property",
                    "idShort": "Created_Date",
                    "valueType": "xs:string",
                    "value": datetime.now().strftime("%Y-%m-%d")
                }
            ]
        }
        
        # Save documentation
        output_path = self.base_path / "JSON_Submodels" / "Product_Submodels_JSON" / "Instances" / "Final_Product_Instance_Submodels" / f"Product-Final_Product-Telefon-Telefon_Pro_Max-{instance_num}-Documentation.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(doc, f, indent=2, ensure_ascii=False)
        
        print(f"  ✓ Created Documentation submodel: {output_path.name}")
    
    def _create_bottom_cover_instance(self, instance_num: str, config: Dict[str, Any]) -> str:
        """Create Bottom_Cover component instance with all submodels."""
        instance_id = f"https://aausmartlab.com/Assets/Product/Component/AAU/Bottom_Cover/{instance_num}"
        
        # Create shell
        shell = {
            "idShort": "Bottom_Cover",
            "id": instance_id,
            "modelType": "AssetAdministrationShell",
            "assetInformation": {
                "assetKind": "Instance",
                "globalAssetId": f"https://aausmartlab.com/Assets/Product/AAU/Bottom_Cover/{instance_num}"
            },
            "submodels": [
                {"type": "ModelReference", "keys": [{"type": "Submodel", "value": f"{instance_id}/Documentation"}]},
                {"type": "ModelReference", "keys": [{"type": "Submodel", "value": f"{instance_id}/Bill_Of_Processes"}]},
                {"type": "ModelReference", "keys": [{"type": "Submodel", "value": f"{instance_id}/Properties"}]}
            ]
        }
        
        output_path = self.base_path / "JSON_Shells" / "Product_Shells_JSON" / "Instances" / "Component_Instances" / f"Product-Component-AAU-Bottom_Cover-{instance_num}.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(shell, f, indent=2, ensure_ascii=False)
        
        # Create Properties submodel using Type properties with configured overrides
        config_overrides = {
            "Material": config.get('bottom_cover_material', 'PLA-31212'),
            "Color": config.get('bottom_cover_color', 'Red'),
            "Finish": config.get('bottom_cover_finish', 'Glossy')
        }
        property_list = self._get_type_properties_with_values("Bottom_Cover", config_overrides)
        
        properties = {
            "idShort": "Properties",
            "semanticId": {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": "https://aausmartlab.com/Data/Parts/Variants"}]},
            "id": f"{instance_id}/Properties",
            "description": [{"language": "en", "text": "Properties for this Bottom_Cover instance"}],
            "submodelElements": [
                {
                    "modelType": "SubmodelElementList",
                    "idShort": "List_Of_Properties",
                    "semanticId": {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": "https://aausmartlab.com/Submodels/List_Of_Properties"}]},
                    "typeValueListElement": "SubmodelElementCollection",
                    "valueTypeListElement": None,
                    "orderRelevant": True,
                    "value": property_list
                }
            ]
        }
        
        props_path = self.base_path / "JSON_Submodels" / "Product_Submodels_JSON" / "Instances" / "Component_Instance_Submodels" / f"Product-Component-AAU-Bottom_Cover-{instance_num}-Properties.json"
        with open(props_path, 'w', encoding='utf-8') as f:
            json.dump(properties, f, indent=2, ensure_ascii=False)
        
        # Create Documentation submodel
        doc = {
            "idShort": "Documentation",
            "semanticId": {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": "https://aausmartlab.com/Data/Documentation"}]},
            "id": f"{instance_id}/Documentation",
            "submodelElements": [
                {"modelType": "Property", "idShort": "Product_Name", "valueType": "xs:string", "value": "Bottom Cover"},
                {"modelType": "Property", "idShort": "Instance_Number", "valueType": "xs:string", "value": instance_num},
                {"modelType": "Property", "idShort": "Created_Date", "valueType": "xs:string", "value": datetime.now().strftime("%Y-%m-%d")}
            ]
        }
        
        doc_path = self.base_path / "JSON_Submodels" / "Product_Submodels_JSON" / "Instances" / "Component_Instance_Submodels" / f"Product-Component-AAU-Bottom_Cover-{instance_num}-Documentation.json"
        with open(doc_path, 'w', encoding='utf-8') as f:
            json.dump(doc, f, indent=2, ensure_ascii=False)
        
        # Create Bill_Of_Processes submodel (copy Process_Categories from Type)
        bop = self._get_type_bill_of_processes("Bottom_Cover", instance_id)
        
        bop_path = self.base_path / "JSON_Submodels" / "Product_Submodels_JSON" / "Instances" / "Component_Instance_Submodels" / f"Product-Component-AAU-Bottom_Cover-{instance_num}-Bill_Of_Processes.json"
        with open(bop_path, 'w', encoding='utf-8') as f:
            json.dump(bop, f, indent=2, ensure_ascii=False)
        
        # Update registry
        self._update_registry("Bottom_Cover", instance_num, {
            "material": config.get('bottom_cover_material'),
            "color": config.get('bottom_cover_color'),
            "finish": config.get('bottom_cover_finish')
        }, instance_id)
        
        print(f"  ✓ Created Bottom_Cover instance: {instance_num}")
        return instance_id
    
    def _create_top_cover_instance(self, instance_num: str, config: Dict[str, Any]) -> str:
        """Create Top_Cover component instance with all submodels."""
        instance_id = f"https://aausmartlab.com/Assets/Product/Component/AAU/Top_Cover/{instance_num}"
        
        # Create shell
        shell = {
            "idShort": "Top_Cover",
            "id": instance_id,
            "modelType": "AssetAdministrationShell",
            "assetInformation": {
                "assetKind": "Instance",
                "globalAssetId": f"https://aausmartlab.com/Assets/Product/AAU/Top_Cover/{instance_num}"
            },
            "submodels": [
                {"type": "ModelReference", "keys": [{"type": "Submodel", "value": f"{instance_id}/Documentation"}]},
                {"type": "ModelReference", "keys": [{"type": "Submodel", "value": f"{instance_id}/Bill_Of_Processes"}]},
                {"type": "ModelReference", "keys": [{"type": "Submodel", "value": f"{instance_id}/Properties"}]}
            ]
        }
        
        output_path = self.base_path / "JSON_Shells" / "Product_Shells_JSON" / "Instances" / "Component_Instances" / f"Product-Component-AAU-Top_Cover-{instance_num}.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(shell, f, indent=2, ensure_ascii=False)
        
        # Load Type properties and apply configuration overrides
        config_overrides = {
            "Material": config.get('top_cover_material', 'PLA-31212'),
            "Color": config.get('top_cover_color', 'Red'),
            "Finish": config.get('top_cover_finish', 'Glossy')
        }
        property_list = self._get_type_properties_with_values("Top_Cover", config_overrides)
        
        # Create Properties submodel
        properties = {
            "idShort": "Properties",
            "semanticId": {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": "https://aausmartlab.com/Data/Parts/Variants"}]},
            "id": f"{instance_id}/Properties",
            "description": [{"language": "en", "text": "Properties for this Top_Cover instance"}],
            "submodelElements": [
                {
                    "modelType": "SubmodelElementList",
                    "idShort": "List_Of_Properties",
                    "semanticId": {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": "https://aausmartlab.com/Submodels/List_Of_Properties"}]},
                    "typeValueListElement": "SubmodelElementCollection",
                    "valueTypeListElement": None,
                    "orderRelevant": True,
                    "value": property_list
                }
            ]
        }
        
        props_path = self.base_path / "JSON_Submodels" / "Product_Submodels_JSON" / "Instances" / "Component_Instance_Submodels" / f"Product-Component-AAU-Top_Cover-{instance_num}-Properties.json"
        with open(props_path, 'w', encoding='utf-8') as f:
            json.dump(properties, f, indent=2, ensure_ascii=False)
        
        # Create Documentation submodel
        doc = {
            "idShort": "Documentation",
            "semanticId": {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": "https://aausmartlab.com/Data/Documentation"}]},
            "id": f"{instance_id}/Documentation",
            "submodelElements": [
                {"modelType": "Property", "idShort": "Product_Name", "valueType": "xs:string", "value": "Top Cover"},
                {"modelType": "Property", "idShort": "Instance_Number", "valueType": "xs:string", "value": instance_num},
                {"modelType": "Property", "idShort": "Created_Date", "valueType": "xs:string", "value": datetime.now().strftime("%Y-%m-%d")}
            ]
        }
        
        doc_path = self.base_path / "JSON_Submodels" / "Product_Submodels_JSON" / "Instances" / "Component_Instance_Submodels" / f"Product-Component-AAU-Top_Cover-{instance_num}-Documentation.json"
        with open(doc_path, 'w', encoding='utf-8') as f:
            json.dump(doc, f, indent=2, ensure_ascii=False)
        
        # Create Bill_Of_Processes submodel (copy Process_Categories from Type)
        bop = self._get_type_bill_of_processes("Top_Cover", instance_id)
        
        bop_path = self.base_path / "JSON_Submodels" / "Product_Submodels_JSON" / "Instances" / "Component_Instance_Submodels" / f"Product-Component-AAU-Top_Cover-{instance_num}-Bill_Of_Processes.json"
        with open(bop_path, 'w', encoding='utf-8') as f:
            json.dump(bop, f, indent=2, ensure_ascii=False)
        
        # Update registry
        self._update_registry("Top_Cover", instance_num, {
            "material": config.get('top_cover_material'),
            "color": config.get('top_cover_color'),
            "finish": config.get('top_cover_finish')
        }, instance_id)
        
        print(f"  ✓ Created Top_Cover instance: {instance_num}")
        return instance_id
    
    def _create_pcb_instance(self, instance_num: str, config: Dict[str, Any]) -> str:
        """Create PCB component instance with all submodels."""
        instance_id = f"https://aausmartlab.com/Assets/Product/Component/AAU/PCB/{instance_num}"
        
        # Create shell
        shell = {
            "idShort": "PCB",
            "id": instance_id,
            "modelType": "AssetAdministrationShell",
            "assetInformation": {
                "assetKind": "Instance",
                "globalAssetId": f"https://aausmartlab.com/Assets/Product/AAU/PCB/{instance_num}"
            },
            "submodels": [
                {"type": "ModelReference", "keys": [{"type": "Submodel", "value": f"{instance_id}/Documentation"}]},
                {"type": "ModelReference", "keys": [{"type": "Submodel", "value": f"{instance_id}/Bill_Of_Processes"}]},
                {"type": "ModelReference", "keys": [{"type": "Submodel", "value": f"{instance_id}/Properties"}]}
            ]
        }
        
        output_path = self.base_path / "JSON_Shells" / "Product_Shells_JSON" / "Instances" / "Component_Instances" / f"Product-Component-AAU-PCB-{instance_num}.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(shell, f, indent=2, ensure_ascii=False)
        
        # Load Type properties (PCB has no configurable properties, just inherit from Type)
        property_list = self._get_type_properties_with_values("PCB", {})
        
        # Create Properties submodel
        properties = {
            "idShort": "Properties",
            "semanticId": {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": "https://aausmartlab.com/Data/Parts/Variants"}]},
            "id": f"{instance_id}/Properties",
            "submodelElements": [
                {
                    "modelType": "SubmodelElementList",
                    "idShort": "List_Of_Properties",
                    "semanticId": {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": "https://aausmartlab.com/Submodels/List_Of_Properties"}]},
                    "typeValueListElement": "SubmodelElementCollection",
                    "valueTypeListElement": None,
                    "orderRelevant": True,
                    "value": property_list
                }
            ]
        }
        
        props_path = self.base_path / "JSON_Submodels" / "Product_Submodels_JSON" / "Instances" / "Component_Instance_Submodels" / f"Product-Component-AAU-PCB-{instance_num}-Properties.json"
        with open(props_path, 'w', encoding='utf-8') as f:
            json.dump(properties, f, indent=2, ensure_ascii=False)
        
        # Create Documentation submodel
        doc = {
            "idShort": "Documentation",
            "semanticId": {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": "https://aausmartlab.com/Data/Documentation"}]},
            "id": f"{instance_id}/Documentation",
            "submodelElements": [
                {"modelType": "Property", "idShort": "Product_Name", "valueType": "xs:string", "value": "Printed Circuit Board"},
                {"modelType": "Property", "idShort": "Instance_Number", "valueType": "xs:string", "value": instance_num}
            ]
        }
        
        doc_path = self.base_path / "JSON_Submodels" / "Product_Submodels_JSON" / "Instances" / "Component_Instance_Submodels" / f"Product-Component-AAU-PCB-{instance_num}-Documentation.json"
        with open(doc_path, 'w', encoding='utf-8') as f:
            json.dump(doc, f, indent=2, ensure_ascii=False)
        
        # Create Bill_Of_Processes submodel (copy Process_Categories from Type)
        bop = self._get_type_bill_of_processes("PCB", instance_id)
        
        bop_path = self.base_path / "JSON_Submodels" / "Product_Submodels_JSON" / "Instances" / "Component_Instance_Submodels" / f"Product-Component-AAU-PCB-{instance_num}-Bill_Of_Processes.json"
        with open(bop_path, 'w', encoding='utf-8') as f:
            json.dump(bop, f, indent=2, ensure_ascii=False)
        
        # Update registry
        self._update_registry("PCB", instance_num, {}, instance_id)
        
        print(f"  ✓ Created PCB instance: {instance_num}")
        return instance_id
    
    def _create_fuse_instances(self, base_instance_num: str, config: Dict[str, Any]) -> List[str]:
        """Create Fuse component instances (1-3 based on configuration)."""
        num_fuses = config.get('number_of_fuses', 1)
        fuse_ids = []
        
        base_num = int(base_instance_num)
        
        for i in range(num_fuses):
            fuse_instance_num = self.get_next_instance_number("Fuse")
            instance_id = f"https://aausmartlab.com/Assets/Product/Component/AAU/Fuse/{fuse_instance_num}"
            
            # Create shell
            shell = {
                "idShort": "Fuse",
                "id": instance_id,
                "modelType": "AssetAdministrationShell",
                "assetInformation": {
                    "assetKind": "Instance",
                    "globalAssetId": f"https://aausmartlab.com/Assets/Product/AAU/Fuse/{fuse_instance_num}"
                },
                "submodels": [
                    {"type": "ModelReference", "keys": [{"type": "Submodel", "value": f"{instance_id}/Documentation"}]},
                    {"type": "ModelReference", "keys": [{"type": "Submodel", "value": f"{instance_id}/Bill_Of_Processes"}]},
                    {"type": "ModelReference", "keys": [{"type": "Submodel", "value": f"{instance_id}/Properties"}]}
                ]
            }
            
            output_path = self.base_path / "JSON_Shells" / "Product_Shells_JSON" / "Instances" / "Component_Instances" / f"Product-Component-AAU-Fuse-{fuse_instance_num}.json"
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(shell, f, indent=2, ensure_ascii=False)
            
            # Load Type properties (Fuse has no configurable properties, just inherit from Type)
            property_list = self._get_type_properties_with_values("Fuse", {})
            
            # Create Properties submodel
            properties = {
                "idShort": "Properties",
                "semanticId": {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": "https://aausmartlab.com/Data/Parts/Variants"}]},
                "id": f"{instance_id}/Properties",
                "submodelElements": [
                    {
                        "modelType": "SubmodelElementList",
                        "idShort": "List_Of_Properties",
                        "semanticId": {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": "https://aausmartlab.com/Submodels/List_Of_Properties"}]},
                        "typeValueListElement": "SubmodelElementCollection",
                        "valueTypeListElement": None,
                        "orderRelevant": True,
                        "value": property_list
                    }
                ]
            }
            
            props_path = self.base_path / "JSON_Submodels" / "Product_Submodels_JSON" / "Instances" / "Component_Instance_Submodels" / f"Product-Component-AAU-Fuse-{fuse_instance_num}-Properties.json"
            with open(props_path, 'w', encoding='utf-8') as f:
                json.dump(properties, f, indent=2, ensure_ascii=False)
            
            # Create Documentation submodel
            doc = {
                "idShort": "Documentation",
                "semanticId": {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": "https://aausmartlab.com/Data/Documentation"}]},
                "id": f"{instance_id}/Documentation",
                "submodelElements": [
                    {"modelType": "Property", "idShort": "Product_Name", "valueType": "xs:string", "value": "Electrical Fuse"},
                    {"modelType": "Property", "idShort": "Instance_Number", "valueType": "xs:string", "value": fuse_instance_num}
                ]
            }
            
            doc_path = self.base_path / "JSON_Submodels" / "Product_Submodels_JSON" / "Instances" / "Component_Instance_Submodels" / f"Product-Component-AAU-Fuse-{fuse_instance_num}-Documentation.json"
            with open(doc_path, 'w', encoding='utf-8') as f:
                json.dump(doc, f, indent=2, ensure_ascii=False)
            
            # Create Bill_Of_Processes submodel (copy Process_Categories from Type)
            bop = self._get_type_bill_of_processes("Fuse", instance_id)
            
            bop_path = self.base_path / "JSON_Submodels" / "Product_Submodels_JSON" / "Instances" / "Component_Instance_Submodels" / f"Product-Component-AAU-Fuse-{fuse_instance_num}-Bill_Of_Processes.json"
            with open(bop_path, 'w', encoding='utf-8') as f:
                json.dump(bop, f, indent=2, ensure_ascii=False)
            
            # Update registry
            self._update_registry("Fuse", fuse_instance_num, {}, instance_id)
            
            fuse_ids.append(instance_id)
        
        print(f"  ✓ Created {num_fuses} Fuse instance(s)")
        return fuse_ids
    
    def _create_pcb_with_fuse_instance(self, instance_num: str, config: Dict[str, Any], pcb_id: str, fuse_ids: List[str]) -> str:
        """Create PCB_With_Fuse sub-assembly instance."""
        instance_id = f"https://aausmartlab.com/Assets/Product/Sub_Assembly/AAU/PCB_With_Fuse/{instance_num}"
        
        # Create shell
        shell = {
            "idShort": "PCB_With_Fuse",
            "id": instance_id,
            "modelType": "AssetAdministrationShell",
            "assetInformation": {
                "assetKind": "Instance",
                "globalAssetId": f"https://aausmartlab.com/Assets/Product/AAU/PCB_With_Fuse/{instance_num}"
            },
            "submodels": [
                {"type": "ModelReference", "keys": [{"type": "Submodel", "value": f"{instance_id}/Documentation"}]},
                {"type": "ModelReference", "keys": [{"type": "Submodel", "value": f"{instance_id}/Bill_Of_Processes"}]},
                {"type": "ModelReference", "keys": [{"type": "Submodel", "value": f"{instance_id}/Bill_Of_Materials"}]},
                {"type": "ModelReference", "keys": [{"type": "Submodel", "value": f"{instance_id}/Properties"}]}
            ]
        }
        
        output_path = self.base_path / "JSON_Shells" / "Product_Shells_JSON" / "Instances" / "Sub_Assembly_Instances" / f"Product-Sub_Assembly-AAU-PCB_With_Fuse-{instance_num}.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(shell, f, indent=2, ensure_ascii=False)
        
        # Create Properties submodel
        properties = {
            "idShort": "Properties",
            "semanticId": {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": "https://aausmartlab.com/Data/Parts/Variants"}]},
            "id": f"{instance_id}/Properties",
            "submodelElements": [
                {
                    "modelType": "SubmodelElementList",
                    "idShort": "List_Of_Properties",
                    "semanticId": {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": "https://aausmartlab.com/Submodels/List_Of_Properties"}]},
                    "typeValueListElement": "SubmodelElementCollection",
                    "valueTypeListElement": None,
                    "orderRelevant": True,
                    "value": [
                        {"modelType": "Property", "idShort": "Nr_Fuses", "valueType": "xs:integer", "value": str(len(fuse_ids))}
                    ]
                }
            ]
        }
        
        props_path = self.base_path / "JSON_Submodels" / "Product_Submodels_JSON" / "Instances" / "Sub_Assembly_Instance_Submodels" / f"Product-Sub_Assembly-AAU-PCB_With_Fuse-{instance_num}-Properties.json"
        with open(props_path, 'w', encoding='utf-8') as f:
            json.dump(properties, f, indent=2, ensure_ascii=False)
        
        # Create Bill_Of_Materials submodel
        bom = {
            "idShort": "Bill_Of_Materials",
            "semanticId": {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": "https://aausmartlab.com/Data/Bill_Of_Materials"}]},
            "id": f"{instance_id}/Bill_Of_Materials",
            "submodelElements": [
                {
                    "modelType": "SubmodelElementList",
                    "idShort": "List_Of_Materials",
                    "semanticId": {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": "https://aausmartlab.com/Data/ListOfMaterials"}]},
                    "typeValueListElement": "SubmodelElementCollection",
                    "valueTypeListElement": None,
                    "orderRelevant": True,
                    "value": [
                        {
                            "modelType": "SubmodelElementCollection",
                            "idShort": "PCB_1",
                            "value": [
                                {"modelType": "Property", "idShort": "Component_Variant", "valueType": "xs:string",
                                 "value": "https://aausmartlab.com/Assets/Product/Component/AAU/PCB"}
                            ]
                        }
                    ] + [
                        {
                            "modelType": "SubmodelElementCollection",
                            "idShort": f"Fuse_{i+1}",
                            "value": [
                                {"modelType": "Property", "idShort": "Component_Variant", "valueType": "xs:string",
                                 "value": "https://aausmartlab.com/Assets/Product/Component/AAU/Fuse"}
                            ]
                        } for i in range(len(fuse_ids))
                    ]
                }
            ]
        }
        
        bom_path = self.base_path / "JSON_Submodels" / "Product_Submodels_JSON" / "Instances" / "Sub_Assembly_Instance_Submodels" / f"Product-Sub_Assembly-AAU-PCB_With_Fuse-{instance_num}-Bill_Of_Materials.json"
        with open(bom_path, 'w', encoding='utf-8') as f:
            json.dump(bom, f, indent=2, ensure_ascii=False)
        
        # Create Documentation submodel
        doc = {
            "idShort": "Documentation",
            "semanticId": {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": "https://aausmartlab.com/Data/Documentation"}]},
            "id": f"{instance_id}/Documentation",
            "submodelElements": [
                {"modelType": "Property", "idShort": "Product_Name", "valueType": "xs:string", "value": "PCB With Fuse Assembly"},
                {"modelType": "Property", "idShort": "Instance_Number", "valueType": "xs:string", "value": instance_num}
            ]
        }
        
        doc_path = self.base_path / "JSON_Submodels" / "Product_Submodels_JSON" / "Instances" / "Sub_Assembly_Instance_Submodels" / f"Product-Sub_Assembly-AAU-PCB_With_Fuse-{instance_num}-Documentation.json"
        with open(doc_path, 'w', encoding='utf-8') as f:
            json.dump(doc, f, indent=2, ensure_ascii=False)
        
        # Create Bill_Of_Processes submodel — one Assemble step per fuse
        assemble_steps = [
            {
                "modelType": "SubmodelElementCollection",
                "idShort": "Assemble",
                "semanticId": {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": "https://aausmartlab.com/Operations/Assemble"}]},
                "description": [{"language": "en", "text": "List of parameters to perform Assemble process."}],
                "value": [
                    {"modelType": "Property", "idShort": "Process_Id", "valueType": "xs:string", "value": f"Assemble_{i + 1}"},
                    {
                        "modelType": "SubmodelElementCollection",
                        "idShort": "Execution_Constraints",
                        "value": [
                            {"modelType": "Property", "idShort": "Constraint_Id", "valueType": "xs:string", "value": fuse_id},
                            {"modelType": "Property", "idShort": "Constraint_Id", "valueType": "xs:string", "value": "https://aausmartlab.com/Assets/Product/Sub_Assembly/AAU/Housing_With_PCB"}
                        ]
                    },
                    {
                        "modelType": "SubmodelElementCollection",
                        "idShort": "Parameters",
                        "value": [
                            {"modelType": "Property", "idShort": "Selected_Operation", "valueType": "xs:string", "value": "Assemble_Housing_With_PCB"}
                        ]
                    }
                ]
            }
            for i, fuse_id in enumerate(fuse_ids)
        ]

        bop = {
            "idShort": "Bill_Of_Processes",
            "semanticId": {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": "https://aausmartlab.com/Data/BillOfOperations"}]},
            "id": f"{instance_id}/Bill_Of_Processes",
            "description": [{"language": "en", "text": "List of manufacturing and assembly operations for the product."}],
            "submodelElements": [
                {
                    "modelType": "SubmodelElementList",
                    "idShort": "List_Of_Processes",
                    "semanticId": {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": "https://aausmartlab.com/Submodel/Bill/List_Of_Processes"}]},
                    "typeValueListElement": "SubmodelElementCollection",
                    "valueTypeListElement": None,
                    "orderRelevant": True,
                    "description": [{"language": "en", "text": "Ordered list of operations required to manufacture and assemble the product."}],
                    "value": assemble_steps
                }
            ]
        }

        bop_path = self.base_path / "JSON_Submodels" / "Product_Submodels_JSON" / "Instances" / "Sub_Assembly_Instance_Submodels" / f"Product-Sub_Assembly-AAU-PCB_With_Fuse-{instance_num}-Bill_Of_Processes.json"
        with open(bop_path, 'w', encoding='utf-8') as f:
            json.dump(bop, f, indent=2, ensure_ascii=False)
        
        # Update registry
        self._update_registry("PCB_With_Fuse", instance_num, {"number_of_fuses": len(fuse_ids)}, instance_id)
        
        print(f"  ✓ Created PCB_With_Fuse sub-assembly: {instance_num}")
        return instance_id
    
    def _create_housing_with_pcb_instance(self, instance_num: str, config: Dict[str, Any], bottom_cover_id: str, pcb_with_fuse_id: str) -> str:
        """Create Housing_With_PCB sub-assembly instance."""
        instance_id = f"https://aausmartlab.com/Assets/Product/Sub_Assembly/AAU/Housing_With_PCB/{instance_num}"
        
        # Create shell
        shell = {
            "idShort": "Housing_With_PCB",
            "id": instance_id,
            "modelType": "AssetAdministrationShell",
            "assetInformation": {
                "assetKind": "Instance",
                "globalAssetId": f"https://aausmartlab.com/Assets/Product/AAU/Housing_With_PCB/{instance_num}"
            },
            "submodels": [
                {"type": "ModelReference", "keys": [{"type": "Submodel", "value": f"{instance_id}/Documentation"}]},
                {"type": "ModelReference", "keys": [{"type": "Submodel", "value": f"{instance_id}/Bill_Of_Processes"}]},
                {"type": "ModelReference", "keys": [{"type": "Submodel", "value": f"{instance_id}/Bill_Of_Materials"}]},
                {"type": "ModelReference", "keys": [{"type": "Submodel", "value": f"{instance_id}/Properties"}]}
            ]
        }
        
        output_path = self.base_path / "JSON_Shells" / "Product_Shells_JSON" / "Instances" / "Sub_Assembly_Instances" / f"Product-Sub_Assembly-AAU-Housing_With_PCB-{instance_num}.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(shell, f, indent=2, ensure_ascii=False)
        
        # Create Properties submodel
        properties = {
            "idShort": "Properties",
            "semanticId": {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": "https://aausmartlab.com/Data/Parts/Variants"}]},
            "id": f"{instance_id}/Properties",
            "submodelElements": [
                {
                    "modelType": "SubmodelElementList",
                    "idShort": "List_Of_Properties",
                    "semanticId": {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": "https://aausmartlab.com/Submodels/List_Of_Properties"}]},
                    "typeValueListElement": "SubmodelElementCollection",
                    "valueTypeListElement": None,
                    "orderRelevant": True,
                    "value": [
                        {"modelType": "Property", "idShort": "Material", "valueType": "xs:string", "value": config.get('bottom_cover_material', 'PLA-31212')},
                        {"modelType": "Property", "idShort": "Color", "valueType": "xs:string", "value": config.get('bottom_cover_color', 'Red')},
                        {"modelType": "Property", "idShort": "Finish", "valueType": "xs:string", "value": config.get('bottom_cover_finish', 'Glossy')},
                        {"modelType": "Property", "idShort": "Nr_Fuses", "valueType": "xs:integer", "value": str(config.get('number_of_fuses', 1))}
                    ]
                }
            ]
        }
        
        props_path = self.base_path / "JSON_Submodels" / "Product_Submodels_JSON" / "Instances" / "Sub_Assembly_Instance_Submodels" / f"Product-Sub_Assembly-AAU-Housing_With_PCB-{instance_num}-Properties.json"
        with open(props_path, 'w', encoding='utf-8') as f:
            json.dump(properties, f, indent=2, ensure_ascii=False)
        
        # Create Bill_Of_Materials submodel
        bom = {
            "idShort": "Bill_Of_Materials",
            "semanticId": {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": "https://aausmartlab.com/Data/Bill_Of_Materials"}]},
            "id": f"{instance_id}/Bill_Of_Materials",
            "submodelElements": [
                {
                    "modelType": "SubmodelElementList",
                    "idShort": "List_Of_Materials",
                    "semanticId": {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": "https://aausmartlab.com/Data/ListOfMaterials"}]},
                    "typeValueListElement": "SubmodelElementCollection",
                    "valueTypeListElement": None,
                    "orderRelevant": True,
                    "value": [
                        {
                            "modelType": "SubmodelElementCollection",
                            "idShort": "Bottom_Cover_1",
                            "value": [
                                {"modelType": "Property", "idShort": "Component_Variant", "valueType": "xs:string",
                                 "value": "https://aausmartlab.com/Assets/Product/Component/AAU/Bottom_Cover"}
                            ]
                        },
                        {
                            "modelType": "SubmodelElementCollection",
                            "idShort": "PCB_With_Fuse_1",
                            "value": [
                                {"modelType": "Property", "idShort": "Component_Variant", "valueType": "xs:string",
                                 "value": "https://aausmartlab.com/Assets/Product/Sub_Assembly/AAU/PCB_With_Fuse"}
                            ]
                        }
                    ]
                }
            ]
        }
        
        bom_path = self.base_path / "JSON_Submodels" / "Product_Submodels_JSON" / "Instances" / "Sub_Assembly_Instance_Submodels" / f"Product-Sub_Assembly-AAU-Housing_With_PCB-{instance_num}-Bill_Of_Materials.json"
        with open(bom_path, 'w', encoding='utf-8') as f:
            json.dump(bom, f, indent=2, ensure_ascii=False)
        
        # Create Documentation submodel
        doc = {
            "idShort": "Documentation",
            "semanticId": {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": "https://aausmartlab.com/Data/Documentation"}]},
            "id": f"{instance_id}/Documentation",
            "submodelElements": [
                {"modelType": "Property", "idShort": "Product_Name", "valueType": "xs:string", "value": "Housing With PCB Assembly"},
                {"modelType": "Property", "idShort": "Instance_Number", "valueType": "xs:string", "value": instance_num}
            ]
        }
        
        doc_path = self.base_path / "JSON_Submodels" / "Product_Submodels_JSON" / "Instances" / "Sub_Assembly_Instance_Submodels" / f"Product-Sub_Assembly-AAU-Housing_With_PCB-{instance_num}-Documentation.json"
        with open(doc_path, 'w', encoding='utf-8') as f:
            json.dump(doc, f, indent=2, ensure_ascii=False)
        
        # Create Bill_Of_Processes submodel (copy Process_Categories from Type)
        bop = self._get_type_bill_of_processes("Housing_With_PCB", instance_id)
        
        bop_path = self.base_path / "JSON_Submodels" / "Product_Submodels_JSON" / "Instances" / "Sub_Assembly_Instance_Submodels" / f"Product-Sub_Assembly-AAU-Housing_With_PCB-{instance_num}-Bill_Of_Processes.json"
        with open(bop_path, 'w', encoding='utf-8') as f:
            json.dump(bop, f, indent=2, ensure_ascii=False)
        
        # Update registry
        self._update_registry("Housing_With_PCB", instance_num, {
            "material": config.get('bottom_cover_material'),
            "color": config.get('bottom_cover_color'),
            "finish": config.get('bottom_cover_finish'),
            "number_of_fuses": config.get('number_of_fuses')
        }, instance_id)
        
        print(f"  ✓ Created Housing_With_PCB sub-assembly: {instance_num}")
        return instance_id
    
    def _update_registry(self, product_type: str, instance_num: str, config: Dict[str, Any], instance_id: str):
        """Update the instance registry with the new instance."""
        if product_type not in self.registry['product_types']:
            self.registry['product_types'][product_type] = {
                "last_instance_number": 0,
                "instances": []
            }
        
        self.registry['product_types'][product_type]['last_instance_number'] = int(instance_num)
        self.registry['product_types'][product_type]['instances'].append({
            "instance_number": instance_num,
            "instance_id": instance_id,
            "created_date": datetime.now().strftime("%Y-%m-%d"),
            "configuration": config,
            "notes": f"Created by configurator"
        })
        
        self.registry['last_updated'] = datetime.now().strftime("%Y-%m-%d")
        self._save_registry()
        
        print(f"  ✓ Updated instance registry")
    
    def reset_registry(self, confirm: bool = False, delete_instances: bool = False) -> bool:
        """Reset the instance registry to initial state.
        
        Args:
            confirm: If True, skip confirmation prompt
            delete_instances: If True, also delete all instance JSON files
            
        Returns:
            True if reset was performed, False if cancelled
        """
        if not confirm:
            print("\n⚠️  WARNING: This will reset the instance registry to initial state.")
            if delete_instances:
                print("⚠️  WARNING: All instance JSON files will be PERMANENTLY DELETED!")
            else:
                print("All instance tracking data will be lost (but existing JSON files will remain).")
            print()
            response = input("Are you sure you want to continue? (yes/no): ").strip().lower()
            if response != 'yes':
                print("Registry reset cancelled.")
                return False
        
        # Create initial registry structure
        initial_registry = {
            "description": "Registry tracking all created product instances for ID management",
            "last_updated": datetime.now().strftime("%Y-%m-%d"),
            "product_types": {
                "Telefon_Pro_Max": {
                    "type_id": "https://aausmartlab.com/Assets/Product/Final_Product/Telefon/Telefon_Pro_Max/Type",
                    "last_instance_number": 0,
                    "instances": []
                },
                "Bottom_Cover": {
                    "type_id": "https://aausmartlab.com/Assets/Product/Component/AAU/Bottom_Cover/Type",
                    "last_instance_number": 0,
                    "instances": []
                },
                "Top_Cover": {
                    "type_id": "https://aausmartlab.com/Assets/Product/Component/AAU/Top_Cover/Type",
                    "last_instance_number": 0,
                    "instances": []
                },
                "PCB": {
                    "type_id": "https://aausmartlab.com/Assets/Product/Component/AAU/PCB/Type",
                    "last_instance_number": 0,
                    "instances": []
                },
                "Fuse": {
                    "type_id": "https://aausmartlab.com/Assets/Product/Component/AAU/Fuse/Type",
                    "last_instance_number": 0,
                    "instances": []
                },
                "PCB_With_Fuse": {
                    "type_id": "https://aausmartlab.com/Assets/Product/Sub_Assembly/AAU/PCB_With_Fuse/Type",
                    "last_instance_number": 0,
                    "instances": []
                },
                "Housing_With_PCB": {
                    "type_id": "https://aausmartlab.com/Assets/Product/Sub_Assembly/AAU/Housing_With_PCB/Type",
                    "last_instance_number": 0,
                    "instances": []
                }
            }
        }
        
        # Delete instance files if requested
        if delete_instances:
            print("\nDeleting instance files...")
            deleted_count = 0
            
            # Delete component instance shells
            component_shells = self.base_path / "JSON_Shells" / "Product_Shells_JSON" / "Instances" / "Component_Instances"
            if component_shells.exists():
                for file in component_shells.glob("*.json"):
                    file.unlink()
                    deleted_count += 1
            
            # Delete sub-assembly instance shells
            subassembly_shells = self.base_path / "JSON_Shells" / "Product_Shells_JSON" / "Instances" / "Sub_Assembly_Instances"
            if subassembly_shells.exists():
                for file in subassembly_shells.glob("*.json"):
                    file.unlink()
                    deleted_count += 1
            
            # Delete final product instance shells
            final_shells = self.base_path / "JSON_Shells" / "Product_Shells_JSON" / "Instances" / "Final_Product_Instances"
            if final_shells.exists():
                for file in final_shells.glob("*.json"):
                    file.unlink()
                    deleted_count += 1
            
            # Delete component instance submodels
            component_submodels = self.base_path / "JSON_Submodels" / "Product_Submodels_JSON" / "Instances" / "Component_Instance_Submodels"
            if component_submodels.exists():
                for file in component_submodels.glob("*.json"):
                    file.unlink()
                    deleted_count += 1
            
            # Delete sub-assembly instance submodels
            subassembly_submodels = self.base_path / "JSON_Submodels" / "Product_Submodels_JSON" / "Instances" / "Sub_Assembly_Instance_Submodels"
            if subassembly_submodels.exists():
                for file in subassembly_submodels.glob("*.json"):
                    file.unlink()
                    deleted_count += 1
            
            # Delete final product instance submodels
            final_submodels = self.base_path / "JSON_Submodels" / "Product_Submodels_JSON" / "Instances" / "Final_Product_Instance_Submodels"
            if final_submodels.exists():
                for file in final_submodels.glob("*.json"):
                    file.unlink()
                    deleted_count += 1
            
            print(f"  ✓ Deleted {deleted_count} instance files")
        
        # Save reset registry
        with open(self.registry_path, 'w', encoding='utf-8') as f:
            json.dump(initial_registry, f, indent=2, ensure_ascii=False)
        
        # Reload registry
        self.registry = self._load_registry()
        
        print("\n✓ Instance registry has been reset to initial state.")
        print("  All instance numbers will start from 001 for new instances.\n")
        return True
    
    def generate_random_configuration(self) -> Dict[str, Any]:
        """Generate a random valid configuration based on the Configuration_Template.
        
        Returns:
            Random configuration dictionary
        """
        # Get available options from template using idShort lookups
        configurable_components = None
        config_rules_element = None
        
        for element in self.config_template['submodelElements']:
            if element['idShort'] == 'Configurable_Components':
                configurable_components = element['value']
            elif element['idShort'] == 'Configuration_Rules':
                config_rules_element = element['value']
        
        # Find Bottom_Cover_Options
        bottom_cover_options = None
        for component in configurable_components:
            if component['idShort'] == 'Bottom_Cover_Options':
                bottom_cover_options = component['value']
                break
        
        # Extract options using idShort lookups instead of array indices
        materials = []
        colors = []
        finishes = []
        material_finish_incompatible = []
        
        for option in bottom_cover_options:
            if option['idShort'] == 'Available_Materials':
                for material_collection in option['value']:
                    for prop in material_collection['value']:
                        if prop['idShort'] == 'Material_ID':
                            materials.append(prop['value'])
                            break
            elif option['idShort'] == 'Available_Colors':
                colors = [color_prop['value'] for color_prop in option['value']]
            elif option['idShort'] == 'Available_Finishes':
                finishes = [finish_prop['value'] for finish_prop in option['value']]
        
        # Get configuration rules
        min_fuses = 1
        max_fuses = 3
        covers_must_match = False
        
        for rule in config_rules_element:
            if rule['idShort'] == 'Minimum_Fuses':
                min_fuses = int(rule['value'])
            elif rule['idShort'] == 'Maximum_Fuses':
                max_fuses = int(rule['value'])
            elif rule['idShort'] == 'Covers_Must_Match':
                covers_must_match = rule['value'].lower() == 'true' if isinstance(rule['value'], str) else rule['value']
            elif rule['idShort'] == 'Material_Finish_Compatibility':
                for incompatibility in rule.get('value', []):
                    material = None
                    finish = None
                    for prop in incompatibility.get('value', []):
                        if prop.get('idShort') == 'Incompatible_Material':
                            material = prop.get('value')
                        elif prop.get('idShort') == 'Incompatible_Finish':
                            finish = prop.get('value')
                    if material and finish:
                        material_finish_incompatible.append((material, finish))
        
        # Generate random configuration with valid material-finish combinations
        # Keep trying until we get valid combinations
        max_attempts = 100
        for attempt in range(max_attempts):
            bottom_material = random.choice(materials)
            bottom_finish = random.choice(finishes)
            
            # Check if bottom cover combination is valid
            if (bottom_material, bottom_finish) in material_finish_incompatible:
                continue
            
            # Decide if covers should match (either enforced or 40% random chance)
            should_match = covers_must_match or (random.random() < 0.4)
            
            if should_match:
                top_material = bottom_material
                top_finish = bottom_finish
                top_color = random.choice(colors)
                bottom_color = top_color
            else:
                top_material = random.choice(materials)
                top_finish = random.choice(finishes)
                
                # Check if top cover combination is valid
                if (top_material, top_finish) in material_finish_incompatible:
                    continue
                
                top_color = random.choice(colors)
                bottom_color = random.choice(colors)
            
            # Valid configuration found
            config = {
                'bottom_cover_material': bottom_material,
                'bottom_cover_color': bottom_color,
                'bottom_cover_finish': bottom_finish,
                'top_cover_material': top_material,
                'top_cover_color': top_color,
                'top_cover_finish': top_finish,
                'number_of_fuses': random.randint(min_fuses, max_fuses)
            }
            break
        else:
            # Fallback if no valid combination found (shouldn't happen with reasonable data)
            config = {
                'bottom_cover_material': materials[0],
                'bottom_cover_color': colors[0],
                'bottom_cover_finish': finishes[0],
                'top_cover_material': materials[0],
                'top_cover_color': colors[0],
                'top_cover_finish': finishes[0],
                'number_of_fuses': min_fuses
            }
        
        return config
    
    def generate_random_instances(self, count: int):
        """Generate multiple random Telefon instances.
        
        Args:
            count: Number of random instances to generate
        """
        print(f"\n=== Generating {count} Random Telefon Instances ===\n")
        
        for i in range(count):
            config = self.generate_random_configuration()
            print(f"Instance {i+1}/{count}:")
            self.create_telefon_instance(config)
            print()  # Empty line between instances
        
        print(f"✓ Successfully generated {count} random instances\n")


def main():
    """Main entry point for the configurator."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Telefon Product Configurator')
    parser.add_argument('--config', type=str, help='Path to configuration JSON file')
    parser.add_argument('--interactive', action='store_true', help='Interactive configuration mode')
    parser.add_argument('--reset-registry', action='store_true', help='Reset instance registry to initial state')
    parser.add_argument('--delete-instances', action='store_true', help='Delete all instance files when resetting registry (use with --reset-registry)')
    parser.add_argument('--generate-random', type=int, metavar='COUNT', help='Generate COUNT random instances')
    
    args = parser.parse_args()
    
    # Get workspace path
    workspace_path = Path(__file__).parent
    
    # Initialize configurator
    configurator = TelefonConfigurator(str(workspace_path))
    
    if args.reset_registry:
        # Reset registry
        configurator.reset_registry(delete_instances=args.delete_instances)
        return
    
    if args.generate_random:
        # Generate random instances
        if args.generate_random < 1:
            print("Error: COUNT must be at least 1")
            return
        configurator.generate_random_instances(args.generate_random)
        return
    
    if args.config:
        # Load configuration from file
        with open(args.config, 'r') as f:
            config = json.load(f)
        
        # Create instance
        configurator.create_telefon_instance(config)
    
    elif args.interactive:
        print("\n=== Telefon Configurator - Interactive Mode ===\n")
        
        # Get configuration from user
        config = {}
        
        print("Bottom Cover Configuration:")
        config['bottom_cover_material'] = input("  Material (PLA-31212/ABS-5500/PETG-7700) [PLA-31212]: ") or "PLA-31212"
        config['bottom_cover_color'] = input("  Color (Red/Blue/Black/White/Green) [Red]: ") or "Red"
        config['bottom_cover_finish'] = input("  Finish (Glossy/Matte/Textured) [Glossy]: ") or "Glossy"
        
        print("\nTop Cover Configuration:")
        config['top_cover_material'] = input("  Material (PLA-31212/ABS-5500/PETG-7700) [PLA-31212]: ") or "PLA-31212"
        config['top_cover_color'] = input("  Color (Red/Blue/Black/White/Green) [Red]: ") or "Red"
        config['top_cover_finish'] = input("  Finish (Glossy/Matte/Textured) [Glossy]: ") or "Glossy"
        
        print("\nFuse Configuration:")
        fuses_str = input("  Number of fuses (1/2/3) [1]: ") or "1"
        config['number_of_fuses'] = int(fuses_str)
        
        # Create instance
        configurator.create_telefon_instance(config)
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
