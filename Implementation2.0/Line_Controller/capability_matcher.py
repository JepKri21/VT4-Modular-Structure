class CapabilityMatcher:
    """
    This class can look at a required capability for the current process in a script and match it with the available resources on your production line
    """
    def __init__(self, resource_manager):
        self.resource_manager = resource_manager

    def match(self, step, capability_model):
        
        # 1. Check capability identity. SHOULD THIS ALSO BE semanticID?
        if step["required_capability"] != capability_model["idShort"]:
            return None
        
        params = step["parameters"]

        # 2. Validate numeric ranges:
        if not self._check_ranges(params, capability_model):
            return None
        
        # 3. Validate material/component constraints:
        if not self._check_constraints(step, capability_model):
            return None
        
        # 4. Find Resource
        resource = self.resource_manager.find_by_capability(capability_model["id"])
        return resource
    
    def _check_ranges(self, params, capability):
        param_block = capability["submodelElements"][0]["value"]

        for p in param_block:
            if "min" in p and "max" in p:
                step_value = params.get(p["idShort"], {}).get("value")

                if step_value is None:
                    return False
                
                if not (float(p["min"])<= float(step_value) <= (p["max"])):
                    return False
                
        return True
    
    def _check_constraints(self, step, capability):

        # Example: material check
        allowed = self._extract(capability, "AllowedMaterials")
        supported = self._extract(capability, "SupportedComponents")

        material = step.get("material")
        component = step.get("ingredient")

        if allowed and material not in allowed:
            return False

        if supported and component not in supported:
            return False

        return True
    
    def _extract(sellf, capability, idshort):
        for el in capability["submodelElements"]:
            if el["idShort"] == idshort:
                return [v["value"] for v in el.get("value" , [])]
        return None