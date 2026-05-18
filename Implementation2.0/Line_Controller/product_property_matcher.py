from typing import Dict, List, Optional, Any
import base64
import requests
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from ClassesAndBuilderMethods.InformationModels import MessageStructure as MS


# ============================================================
# Inventory Indexer
# ============================================================

class InventoryIndexer:

    def __init__(self):

        # Flat searchable component list
        self.indexed_components: List[MS.IndexedComponent] = []

        # Fast exact lookup
        self.component_id_index: Dict[str, MS.IndexedComponent] = {}

        # Fast type lookup
        self.component_type_index: Dict[str, List[MS.IndexedComponent]] = {}

    # ========================================================
    # Public API
    # ========================================================

    def rebuild_index(self, inventory_runtime_data: Dict):

        """
        Rebuilds the entire runtime inventory index
        from the shared runtime inventory structure.
        """

        self.indexed_components.clear()
        self.component_id_index.clear()
        self.component_type_index.clear()

        for resource_shell_id, inventories in inventory_runtime_data.items():

            for inventory_name, inventory_data in inventories.items():

                accessible_actors = inventory_data.accessible_actors

                for slot_id, slot in inventory_data.storage.items():

                    if slot.component_id is None:
                        continue

                    indexed_component = self._create_indexed_component(
                        component_id=slot.component_id,
                        resource_shell_id=resource_shell_id,
                        inventory_name=inventory_name,
                        slot_id=slot_id,
                        accessible_actors=accessible_actors
                    )

                    self._add_to_indexes(indexed_component)

        #print("[COMPONENT ID INDEX]",self.component_id_index)
        #print("[COMPONENT TYPE INDEX]",self.component_type_index)

    def find_by_component_id(self,component_id: str) -> Optional[MS.IndexedComponent]:

        return self.component_id_index.get(component_id)

    def find_by_component_type(self,component_type: str) -> List[MS.IndexedComponent]:

        return self.component_type_index.get(component_type, [])

    def get_all_components(self) -> List[MS.IndexedComponent]:

        return self.indexed_components

    # ========================================================
    # Internal Helpers
    # ========================================================

    def _create_indexed_component(
        self,
        component_id: str,
        resource_shell_id: str,
        inventory_name: str,
        slot_id: str,
        accessible_actors: List[str]
    ) -> MS.IndexedComponent:

        parsed = self._parse_component_reference(component_id)

        return MS.IndexedComponent(
            component_id=component_id,

            component_category=parsed["component_category"],
            component_type=parsed["component_type"],
            component_instance=parsed["component_instance"],

            component_type_reference=parsed["component_type_reference"],

            resource_shell_id=resource_shell_id,
            inventory_name=inventory_name,
            slot_id=slot_id,

            accessible_actors=accessible_actors
        )

    def _add_to_indexes(self,indexed_component: MS.IndexedComponent):

        # Flat list
        self.indexed_components.append(indexed_component)

        # Exact component lookup
        self.component_id_index[
            indexed_component.component_id
        ] = indexed_component

        # Type lookup
        component_type_reference = indexed_component.component_type_reference

        if component_type_reference not in self.component_type_index:
            self.component_type_index[component_type_reference] = []

        self.component_type_index[component_type_reference].append(
            indexed_component
        )

    def _parse_component_reference(self,component_reference: str) -> Dict[str, str]:

        """
        Example input:

        https://aausmartlab.org/Shells/Component/BottomCover/BottomCover-BC001

        Example output:

        {
            "component_category": "Component",
            "component_type": "BottomCover",
            "component_instance": "BottomCover-BC001",
            "component_type_reference":
                "https://aausmartlab.org/Shells/Component/BottomCover"
        }
        """

        parts = component_reference.strip("/").split("/")

        if len(parts) < 3:
            raise ValueError(
                f"Invalid component reference: {component_reference}"
            )

        component_category = parts[-3]
        component_type = parts[-2]
        component_instance = parts[-1]

        component_type_reference = "/".join(parts[:-1])

        return {
            "component_category": component_category,
            "component_type": component_type,
            "component_instance": component_instance,
            "component_type_reference": component_type_reference
        }
    
# ============================================================
# AAS Shell Property Resolver
# ============================================================

class AASPropertyResolver:

    def __init__(self,AAS_BROKER, AAS_PORT):
    #def __init__(self, aas_capabilities): #These two were from something older?
        #self.capabilities = aas_capabilities #Not entirely sure
        self.AAS_BROKER = AAS_BROKER
        self.AAS_PORT = AAS_PORT

        self.AAS_SERVER_BASE = f"http://{self.AAS_BROKER}:{self.AAS_PORT}"
        self.SUBMODEL_ENDPOINT = f"{self.AAS_SERVER_BASE}/submodels"
        self.SHELL_ENDPOINT = f"{self.AAS_SERVER_BASE}/shells"

        # Simple in-memory cache
        self.property_cache = {}

        self.failed_components = set()

    #===============
    #Helper Methods
    #===============

    def _base64encode(self, value: str):

        encoded = base64.urlsafe_b64encode(
            value.encode("utf-8")
        ).decode("ascii")

        return encoded.rstrip("=")
    
    def _extract_semantic_id(self,data: dict) -> str | None:

        semantic = data.get("semanticId")

        if not semantic:
            return None

        keys = semantic.get("keys", [])

        if not keys:
            return None

        return keys[0].get("value")
    
    def _extract_unit(self,property_data: dict) -> str | None:

        qualifiers = property_data.get("qualifiers",[])

        for qualifier in qualifiers:

            if qualifier.get("type") == "unit":
                return qualifier.get("value")

        return None
    
    def _convert_value(self,value,value_type):

        if value is None:
            return None

        try:

            if value_type == "xs:integer":
                return int(value)

            if value_type == "xs:double":
                return float(value)

            return value

        except Exception:
            return value

    #===============
    #Public Methods
    #===============

    def get_component_properties(self,component_id: str) -> MS.ComponentProperties | None:

        # Previously failed
        if component_id in self.failed_components:
            return None

        # Cache hit
        if component_id in self.property_cache:
            return self.property_cache[component_id]

        try:

            properties = self._retrieve_properties_submodel(component_id)

            self.property_cache[component_id] = properties

            return properties

        except Exception as e:

            print(f"[AASPropertyResolver] "f"Failed retrieving properties "f"for {component_id}: {e}")

            self.failed_components.add(component_id)

            return None

    #=================
    #Private Methods
    #=================

    def _retrieve_properties_submodel(self,component_id: str) -> MS.ComponentProperties:

        shell_data = self._retrieve_shell(component_id)

        properties_submodel_reference = (self._find_properties_submodel_reference(shell_data))

        submodel_data = self._retrieve_submodel(properties_submodel_reference)

        return self._normalize_properties(component_id,submodel_data)
    
    def _normalize_properties(self,component_id: str,submodel_data: dict) -> MS.ComponentProperties:

        collections = {}

        for element in submodel_data.get("submodelElements",[]):

            if (element.get("modelType")!= "SubmodelElementCollection"):
                continue

            collection = self._parse_collection(element)

            collections[collection.name] = collection

        return MS.ComponentProperties(component_id=component_id,collections=collections)
    
    def _parse_collection(self,collection_data: dict) -> MS.PropertyCollection:

        collection_name = collection_data.get("idShort")

        semantic_id = self._extract_semantic_id(collection_data)

        properties = {}

        for element in collection_data.get("value", []):

            if element.get("modelType") != "Property":
                continue

            prop = self._parse_property(element)

            properties[prop.name] = prop

        return MS.PropertyCollection(name=collection_name,semantic_id=semantic_id,properties=properties)
    
    def _parse_property(self,property_data: dict) -> MS.NormalizedProperty:

        name = property_data.get("idShort")

        semantic_id = self._extract_semantic_id(property_data)

        value = self._convert_value(property_data.get("value"),property_data.get("valueType"))

        value_type = property_data.get("valueType")

        unit = self._extract_unit(property_data)

        return MS.NormalizedProperty(
            name=name,
            semantic_id=semantic_id,
            value=value,
            value_type=value_type,
            unit=unit
        )

    def _retrieve_shell(self,component_id: str) -> dict:

        encoded_shell_id = self._base64encode(component_id)

        response = requests.get(f"{self.SHELL_ENDPOINT}/{encoded_shell_id}")

        if not response.ok:
            raise Exception(f"Failed to fetch shell: "f"{response.status_code}")

        return response.json()
    
    def _find_properties_submodel_reference(self,shell_data: dict) -> str:

        submodels = shell_data.get("submodels", [])

        for submodel in submodels:

            keys = submodel.get("keys", [])

            if not keys:
                continue

            submodel_reference = keys[0].get("value", "")

            # The Properties submodel's IRI ends with the segment "Properties"
            # (e.g. ".../<instance_id>/Properties"). idShort is also
            # "Properties" but isn't exposed in the shell's submodel refs.
            if submodel_reference.rstrip("/").rsplit("/", 1)[-1] == "Properties":
                return submodel_reference

        raise Exception("Properties submodel reference not found")
    
    def _retrieve_submodel(self,submodel_reference: str) -> dict:

        encoded_submodel_id = self._base64encode(submodel_reference)

        response = requests.get(f"{self.SUBMODEL_ENDPOINT}/{encoded_submodel_id}")

        if not response.ok:
            raise Exception(f"Failed to fetch submodel: "f"{response.status_code}")

        return response.json()
    


# =========================================================
# CONSTRAINT EVALUATOR
# =========================================================

class ConstraintEvaluator:

    """
    Compares requested order constraints against
    normalized AAS component properties.
    """

    # =====================================================
    # PUBLIC API
    # =====================================================

    def evaluate_constraints(self,requested_constraints: MS.RequestedConstraints,actual_properties) -> MS.ConstraintMatchResult:

        matched_properties = []

        failed_properties = []

        missing_properties = []

        # Iterate requested collections
        for (collection_name,requested_collection) in requested_constraints.collections.items():

            actual_collection = (actual_properties.collections.get(collection_name))

            # Collection missing entirely
            if actual_collection is None:

                for property_name in (requested_collection.properties):

                    missing_properties.append(
                        MS.PropertyMatchFailure(
                            collection_name=collection_name,
                            property_name=property_name,
                            reason="Collection missing"
                        )
                    )

                continue

            # Compare properties
            for (property_name,requested_property) in requested_collection.properties.items():

                actual_property = (
                    actual_collection.properties.get(property_name))

                # Property missing
                if actual_property is None:

                    missing_properties.append(
                        MS.PropertyMatchFailure(
                            collection_name=collection_name,
                            property_name=property_name,
                            reason="Property missing"
                        )
                    )

                    continue

                # Semantic mismatch
                if (requested_property.semantic_id!= actual_property.semantic_id):

                    failed_properties.append(
                        MS.PropertyMatchFailure(
                            collection_name=collection_name,
                            property_name=property_name,
                            reason="Semantic ID mismatch",
                            requested_value=(requested_property.semantic_id),
                            actual_value=(actual_property.semantic_id)
                        )
                    )

                    continue

                # Value mismatch
                if (requested_property.value!= actual_property.value):

                    failed_properties.append(
                        MS.PropertyMatchFailure(
                            collection_name=collection_name,
                            property_name=property_name,
                            reason="Value mismatch",
                            requested_value=(requested_property.value),
                            actual_value=(actual_property.value)
                        )
                    )

                    continue

                # Match success
                matched_properties.append(f"{collection_name}.{property_name}")

        matches = (len(failed_properties) == 0 and len(missing_properties) == 0)

        return MS.ConstraintMatchResult(
            matches=matches,
            matched_properties=matched_properties,
            failed_properties=failed_properties,
            missing_properties=missing_properties
        )

    # =====================================================
    # ORDER NORMALIZATION
    # =====================================================

    def build_requested_constraints(self,ingredient_id: str,order_properties: dict) -> MS.RequestedConstraints:

        collections = {}

        for (collection_name,collection_data) in order_properties.items():

            properties = {}

            for (property_name,property_data) in collection_data.items():

                # Work orders use PascalCase "SemanticId"; tolerate the AAS-
                # style "semanticId" too.
                semantic_id = (
                    property_data.get("SemanticId")
                    or property_data.get("semanticId")
                )

                properties[property_name] = (
                    MS.RequestedProperty(
                        name=property_name,
                        semantic_id=semantic_id,
                        value=(property_data.get("value"))
                    )
                )

            collections[collection_name] = (
                MS.RequestedCollection(name=collection_name,properties=properties))

        return MS.RequestedConstraints(ingredient_id=ingredient_id,collections=collections)
    

# =========================================================
# PRODUCT MATCHER
# =========================================================
class ProductMatcher:

    def __init__(self,AAS_BROKER, AAS_PORT):
    #def __init__(self, aas_capabilities): #These two were from something older?
        #self.capabilities = aas_capabilities #Not entirely sure
        self.AAS_BROKER = AAS_BROKER
        self.AAS_PORT = AAS_PORT

        self.AAS_SERVER_BASE = f"http://{self.AAS_BROKER}:{self.AAS_PORT}"
        self.SUBMODEL_ENDPOINT = f"{self.AAS_SERVER_BASE}/submodels"
        self.SHELL_ENDPOINT = f"{self.AAS_SERVER_BASE}/shells"


        self.inventory_indexer = InventoryIndexer()
        self.property_resolver = AASPropertyResolver(self.AAS_BROKER,AAS_PORT)
        self.constraint_evaluator = ConstraintEvaluator()

    def find_in_resource_inventory(
        self,
        resource_shell_id: str,
        component_type_reference: str,
    ) -> list[MS.ComponentLocation]:
        """Type-only lookup scoped to one resource's inventory.

        Use when picking from a resource we trust (typically the target
        resource itself): no AAS Properties fetch, no constraint check —
        just "does this resource hold a component of this type?".
        Returns ComponentLocations in storage order.
        """
        results = []
        for candidate in self.inventory_indexer.find_by_component_type(component_type_reference):
            if candidate.resource_shell_id != resource_shell_id:
                continue
            results.append(MS.ComponentLocation(
                component_id=candidate.component_id,
                resource_shell_id=candidate.resource_shell_id,
                inventory_name=candidate.inventory_name,
                slot_id=candidate.slot_id,
                actor_names=(candidate.accessible_actors if candidate.accessible_actors else None),
            ))
        return results

    def find_component_location(self, component_id: str):

        match = self.inventory_indexer.find_by_component_id(component_id)

        if not match:
            return None

        return MS.ComponentLocation(
            component_id=match.component_id,
            resource_shell_id=match.resource_shell_id,
            inventory_name=match.inventory_name,
            slot_id=match.slot_id,
            actor_names=match.accessible_actors if match.accessible_actors else None
        )
    
    def find_matching_components(self,component_type_reference: str,order_properties: dict) -> list[MS.ComponentLocation]:
        """
        Takes the full type topic such as: https://aausmartlab.org/Shells/Component/BottomCover
        AND the properties of that component from the MES order, as they are structured in the order
        Outputs a list of ComponentLocation classes, containing the component_id, resource_id, inventory_name, slot_id, and list of actors with access
        """
        results = []

        # 1. Build constraint model once
        requested_constraints = (
            self.constraint_evaluator.build_requested_constraints(
                ingredient_id=component_type_reference,
                order_properties=order_properties))

        # 2. Get candidates from inventory
        candidates = self.inventory_indexer.find_by_component_type(component_type_reference)
        #print("[CANDIDATES]",candidates)

        no_constraints = not requested_constraints.collections

        for candidate in candidates:

            if no_constraints:
                # Nothing to evaluate — accept by type alone. Avoids hitting
                # the AAS server for Properties that the order doesn't care
                # about (and that may not exist).
                results.append(
                    MS.ComponentLocation(
                        component_id=candidate.component_id,
                        resource_shell_id=candidate.resource_shell_id,
                        inventory_name=candidate.inventory_name,
                        slot_id=candidate.slot_id,
                        actor_names=(candidate.accessible_actors if candidate.accessible_actors else None)))
                continue

            # 3. Get AAS properties
            properties = (self.property_resolver.get_component_properties(candidate.component_id))

            if properties is None:
                continue

            # 4. Evaluate constraints
            result_eval = self.constraint_evaluator.evaluate_constraints(requested_constraints,properties)

            if result_eval.matches:

                results.append(
                    MS.ComponentLocation(
                        component_id=candidate.component_id,
                        resource_shell_id=candidate.resource_shell_id,
                        inventory_name=candidate.inventory_name,
                        slot_id=candidate.slot_id,
                        actor_names=(candidate.accessible_actors if candidate.accessible_actors else None)))

        return results
    



