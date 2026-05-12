class CapabilityMatcher:
    """
    Filter resources whose declared capability is compatible with a given
    process step. Identity is matched on capability semanticId. The matcher
    only filters — it never picks a winner. The scheduler does that.
    """

    def __init__(self, resource_manager):
        self.resource_manager = resource_manager

    def match(self, step_info):
        """
        Args:
            step_info: dict from WorkOrderHandler.get_step_execution_info().
                Expected keys: CapabilityReference, Parameters,
                ComponentReference, Material.

        Returns:
            List of viable candidates, each:
                {
                    "resource_id": <shell_id>,
                    "skill_name": <skill idShort>,
                    "capability_submodel_reference": <submodel id>,
                }
        """
        capability_semantic_id = step_info.get("CapabilityReference")
        if not capability_semantic_id:
            print("[match] no CapabilityReference on step_info — rejecting")
            return []

        print(f"[match] looking for resources offering: {capability_semantic_id}")
        candidates = self.resource_manager.find_by_capability(capability_semantic_id)
        if not candidates:
            print("[match] no resources advertise that capability semanticId")
            return []
        print(f"[match] {len(candidates)} initial candidate(s):")
        for c in candidates:
            print(f"          - {c['resource_id']}  (skill={c['skill_name']})")

        params = step_info.get("Parameters", {})
        component = step_info.get("ComponentReference")
        material = step_info.get("Material")

        viable = []
        for cand in candidates:
            tag = f"{cand['resource_id']}/{cand['skill_name']}"
            cap_ref = cand.get("capability_submodel_reference")
            if not cap_ref:
                print(f"[match] [{tag}] rejected: no CapabilitySubmodelReference")
                continue

            cap_data = self.resource_manager.get_capability_parameters(cap_ref)
            if not cap_data:
                print(f"[match] [{tag}] rejected: capability submodel had no parameters")
                continue

            cap_parameters, supported_components, allowed_materials = cap_data

            if not self._check_parameters(params, cap_parameters):
                print(
                    f"[match] [{tag}] rejected: parameter check failed "
                    f"(work-order params={list(params)}, "
                    f"capability leaves={list(self._flatten_cap_parameters(cap_parameters))})"
                )
                continue
            if not self._check_component(component, supported_components):
                print(
                    f"[match] [{tag}] rejected: component '{component}' not in "
                    f"supported list {supported_components}"
                )
                continue
            if not self._check_material(material, allowed_materials):
                print(
                    f"[match] [{tag}] rejected: material '{material}' not in "
                    f"allowed list {allowed_materials}"
                )
                continue

            print(f"[match] [{tag}] accepted")
            viable.append(cand)

        return viable

    # ---- helpers ----

    # Workorder-side names that should be resolved against differently named
    # leaves in the capability tree. Pragmatic alias until parameter naming
    # is unified across workorders and capability submodels.
    PARAMETER_ALIASES = {
        "HolePlacement_X": "XPos",
        "HolePlacement_Y": "YPos",
    }

    def _check_parameters(self, step_params, cap_parameters):
        """
        Validate every workorder parameter against the capability. Both sides
        are flattened to leaf id_shorts, so nested structures (e.g.
        TargetPosition.XPos in the work order matched against the capability's
        Parameters.TargetPosition.XPos) compare cleanly. If the capability
        declares a Range for a leaf, the workorder value must fall inside it.
        Property declarations are accepted as-is. Unknown parameters on the
        workorder are rejected.
        """
        cap_by_name = self._flatten_cap_parameters(cap_parameters)
        step_by_name = self._flatten_step_params(step_params)

        for name, value in step_by_name.items():
            cap_param = cap_by_name.get(name)
            if cap_param is None:
                aliased = self.PARAMETER_ALIASES.get(name)
                if aliased:
                    cap_param = cap_by_name.get(aliased)

            if cap_param is None:
                return False

            if hasattr(cap_param, "min") and hasattr(cap_param, "max"):
                try:
                    v = float(value)
                    lo = float(cap_param.min)
                    hi = float(cap_param.max)
                except (TypeError, ValueError):
                    return False
                if not (lo <= v <= hi):
                    return False

        return True

    def _flatten_step_params(self, step_params):
        """Walk the work-order parameter tree, returning {leaf_idShort: value}.

        Treats any dict containing a 'value' key (with either 'semanticId' or
        'semantic_id' alongside it, or just 'value' on its own) as a leaf.
        Other dicts are recursed into. Bare scalar values pass through.
        """
        flat = {}

        def is_leaf_wrapper(node):
            return isinstance(node, dict) and "value" in node and (
                "semanticId" in node or "semantic_id" in node or len(node) <= 2
            )

        def walk(node):
            if not isinstance(node, dict):
                return
            for name, body in node.items():
                if is_leaf_wrapper(body):
                    flat[name] = body["value"]
                elif isinstance(body, dict):
                    walk(body)
                else:
                    flat[name] = body

        walk(step_params or {})
        return flat

    def _flatten_cap_parameters(self, cap_parameters):
        flat = {}
        for p in cap_parameters or []:
            self._flatten_into(p, flat)
        return flat

    def _flatten_into(self, node, flat):
        name = getattr(node, "id_short", None)
        children = getattr(node, "elements", None)
        if children:
            for child in children:
                self._flatten_into(child, flat)
            return
        if name:
            flat[name] = node

    def _check_component(self, component, supported_components):
        if not supported_components:
            return True
        if component is None:
            return False
        return component in supported_components

    def _check_material(self, material, allowed_materials):
        """
        Capability AllowedMaterials are full URLs (e.g.
        'https://aausmartlab.org/Materials/PLA'). The workorder may hold
        either the same full URL or just the short name as its Material
        value (e.g. 'PLA'). Accept both: compare full URLs directly, and
        fall back to comparing against the URL basename.
        """
        if not allowed_materials:
            return True
        if material is None:
            return False
        if material in allowed_materials:
            return True
        basenames = {url.rsplit("/", 1)[-1] for url in allowed_materials}
        return material in basenames
