class CapabilityMatcher:
    """
    Filter resources whose declared capability is compatible with a given
    process step. Identity is matched on capability semanticId. The matcher
    is a pure type-vs-type check — it never looks at inventory state and
    never resolves instance IRIs. That is the scheduler's job.
    """

    def __init__(self, resource_manager):
        self.resource_manager = resource_manager

    def match(self, step_info, excluded_resources: set[str] | None = None):
        """Filter resources whose capability is compatible with the step.

        Args:
            step_info: dict from WorkOrderHandler.get_step_execution_info().
                Required keys: CapabilityReference, Parameters,
                ComponentTypeReference, ProcessTransformation, Material.
            excluded_resources: shell IRIs to skip — used by order recovery
                to keep a restarted order from reaching for the resource
                that just failed it.

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

        excluded = excluded_resources or set()

        print(f"[match] looking for resources offering: {capability_semantic_id}")
        candidates = self.resource_manager.find_by_capability(capability_semantic_id)
        if not candidates:
            print("[match] no resources advertise that capability semanticId")
            return []
        if excluded:
            before = len(candidates)
            candidates = [c for c in candidates if c["resource_id"] not in excluded]
            removed = before - len(candidates)
            if removed:
                print(f"[match] {removed} candidate(s) excluded by recovery policy")
            if not candidates:
                print("[match] all candidates were excluded — no alternative")
                return []
        print(f"[match] {len(candidates)} initial candidate(s):")
        for c in candidates:
            print(f"          - {c['resource_id']}  (skill={c['skill_name']})")

        params = step_info.get("Parameters", {})
        material = step_info.get("Material")

        # ProcessTransformation: step's resolved type IRIs for the inputs and
        # outputs of this transformation. Compared as sets (order-independent)
        # against the resource's declared ProcessTransformations.
        step_transformation = step_info.get("ProcessTransformation") or {}
        step_input_types = [t for t in (step_transformation.get("InputTypes") or []) if t]
        step_output_types = [t for t in (step_transformation.get("OutputTypes") or []) if t]

        # Components to check against the resource's SupportedComponents:
        # every input type IRI, plus the step's main output (the ingredient
        # being produced/operated on, exposed as ComponentTypeReference).
        primary_type = step_info.get("ComponentTypeReference")
        component_types_to_check = list({
            t for t in ([*step_input_types, *step_output_types, primary_type]) if t
        })

        viable = []
        for cand in candidates:
            tag = f"{cand['resource_id']}/{cand['skill_name']}"
            cap_ref = cand.get("capability_submodel_reference")
            if not cap_ref:
                print(f"[match] [{tag}] rejected: no CapabilitySubmodelReference")
                continue

            cap_data = self.resource_manager.get_capability_parameters(cap_ref)
            if not cap_data:
                print(f"[match] [{tag}] rejected: capability submodel could not be read")
                continue

            cap_parameters, supported_components, allowed_materials, cap_transformations = cap_data

            ok, reason = self._check_parameters(params, cap_parameters)
            if not ok:
                print(
                    f"[match] [{tag}] rejected: parameter check failed — {reason} "
                    f"(work-order params={list(params)}, "
                    f"capability leaves={list(self._flatten_cap_parameters(cap_parameters))})"
                )
                continue
            ok, reason = self._check_process_transformation(
                step_input_types, step_output_types, cap_transformations
            )
            if not ok:
                print(f"[match] [{tag}] rejected: transformation check failed — {reason}")
                continue
            ok, reason = self._check_components(component_types_to_check, supported_components)
            if not ok:
                print(f"[match] [{tag}] rejected: component check failed — {reason}")
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
        """Validate every workorder parameter against the capability.

        Both sides are flattened to leaf id_shorts. If the capability declares
        a Range for a leaf, the workorder value must fall inside it. Property
        declarations are accepted as-is. Unknown work-order parameters reject.

        Returns (ok, reason). `reason` is a short human-readable string when
        ok is False, otherwise empty.
        """
        cap_by_name = self._flatten_cap_parameters(cap_parameters)
        step_by_name = self._flatten_step_params(step_params)

        for name, value in step_by_name.items():
            cap_param = cap_by_name.get(name)
            resolved_name = name
            if cap_param is None:
                aliased = self.PARAMETER_ALIASES.get(name)
                if aliased:
                    cap_param = cap_by_name.get(aliased)
                    resolved_name = aliased

            if cap_param is None:
                return False, f"work-order parameter '{name}' has no matching leaf in the capability"

            if hasattr(cap_param, "min") and hasattr(cap_param, "max"):
                try:
                    v = float(value)
                    lo = float(cap_param.min)
                    hi = float(cap_param.max)
                except (TypeError, ValueError):
                    return False, (
                        f"parameter '{resolved_name}' could not be coerced to float "
                        f"(value={value!r}, min={cap_param.min!r}, max={cap_param.max!r})"
                    )
                if not (lo <= v <= hi):
                    return False, (
                        f"parameter '{resolved_name}'={v} outside allowed range [{lo}, {hi}]"
                    )

        return True, ""

    def _check_process_transformation(self, step_inputs, step_outputs, cap_transformations):
        """Step's transformation must exactly match one of the capability's.

        Match is set equality on InputTypes and OutputTypes — order is not
        significant. The resource lists every transformation it supports;
        the matcher just asks "does my (inputs, outputs) appear in there?".

        A capability with no declared ProcessTransformations is treated as
        no constraint along this dimension (so simple capabilities like
        Drilling on the older schema still match). Once your stations all
        declare transformations explicitly, you can tighten this.
        """
        if not cap_transformations:
            return True, ""
        if not step_inputs and not step_outputs:
            # No transformation requested by the step; nothing to check.
            return True, ""
        wanted_in = set(step_inputs)
        wanted_out = set(step_outputs)
        for t in cap_transformations:
            if (set(t.get("input_types") or []) == wanted_in
                    and set(t.get("output_types") or []) == wanted_out):
                return True, ""
        return False, (
            f"no capability transformation matches step inputs={sorted(wanted_in)} "
            f"outputs={sorted(wanted_out)} "
            f"(capability offers: {[t.get('name') for t in cap_transformations]})"
        )

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

    def _check_components(self, components, supported_components):
        """Every component type IRI must be in the resource's SupportedComponents.

        Empty/None `supported_components` means "no restriction" — the
        resource hasn't constrained which types it accepts. Components
        are compared at the type level: anything beyond `/Shells/<Cat>/<Type>`
        is trimmed off so per-instance IRIs match family declarations.

        Returns (ok, reason).
        """
        if not supported_components:
            return True, ""
        if not components:
            return True, ""
        supported_types = {self._component_type(s) for s in supported_components}
        for c in components:
            if self._component_type(c) not in supported_types:
                return False, (
                    f"component '{c}' (type '{self._component_type(c)}') not in "
                    f"supported list {sorted(supported_types)}"
                )
        return True, ""

    def _component_type(self, url):
        """Reduce a Shells URL to '/Shells/<Category>/<Type>', dropping any
        per-instance suffix. URLs already in that form pass through
        unchanged; non-URL input is returned as-is."""
        if not isinstance(url, str):
            return url
        parts = url.split("/")
        try:
            idx = parts.index("Shells")
        except ValueError:
            return url
        return "/".join(parts[: idx + 3])

    def _check_material(self, material, allowed_materials):
        """Material must be in the resource's AllowedMaterials.

        Empty/None `allowed_materials` means "no restriction". The capability
        AllowedMaterials are full URLs (e.g. 'https://aausmartlab.org/Materials/PLA').
        The workorder may hold either the same full URL or just the short
        name ('PLA') — both forms are accepted.
        """
        if not allowed_materials:
            return True
        if material is None:
            # Material unspecified on the workorder side — if the resource has
            # declared a list, we can't prove compatibility, so reject.
            return False
        if material in allowed_materials:
            return True
        basenames = {url.rsplit("/", 1)[-1] for url in allowed_materials}
        return material in basenames
