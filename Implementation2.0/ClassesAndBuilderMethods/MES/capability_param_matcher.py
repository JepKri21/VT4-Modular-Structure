"""
capability_param_matcher.py — dict-based capability parameter matcher for MES
line selection.

This mirrors the Line Controller's matcher
(``Line_Controller/capability_matcher.py``) but operates on the plain AAS JSON
dicts returned by ``basyx_client`` instead of basyx-SDK model objects. It lets
the MES validate that a production line can actually *run* a work order's
parameters — ranges, components, materials, transformations — not merely that it
offers the right capability *types*.

Parameter matching is **collision-aware semanticId-with-idShort-fallback**: a
work-order leaf is matched to an offered leaf by *identity* ``semanticId`` when
exactly one offered leaf carries that semanticId, otherwise by ``idShort`` (with
``PARAMETER_ALIASES`` bridging known name differences). This is safe on both
pre-migration data — where every dimensioned parameter shares the *unit*
semanticId (``…/Semantics/mm``), so the semanticId is non-unique and the matcher
falls back to idShort — and post-migration data, where each parameter carries a
distinct identity semanticId (e.g. ``…/Semantics/Parameter/HoleDiameter``) and is
matched by it regardless of idShort differences. The migration is therefore
incremental and never regresses an unmigrated parameter.

Matching is **permissive**: a missing range, an unreadable detail submodel, or an
unconstrained dimension is treated as "no constraint", matching the Line
Controller's behaviour and avoiding regressions of currently-working lines.
Because permissive fallback can silently hide a misconfiguration (a line gets
selected while nothing is actually checked), every check records *which path* it
took (see ``MatchPath``), and a ``strict`` flag turns permissive fallbacks into
hard failures for tests/CI.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Optional


# ─────────────────────────── observability ────────────────────────────────

class MatchPath(str, enum.Enum):
    """Which code path a check took — logged so permissive fallbacks are visible."""

    RANGE_OK = "range-ok"                 # value checked against a real min/max
    PROPERTY_OK = "property-ok"           # leaf present, no range declared — accepted as-is
    SET_OK = "set-ok"                     # component/material/transformation set matched
    NO_CONSTRAINT = "no-constraint"       # offered side declared nothing — permissive pass
    TYPE_ONLY = "type-only"               # detail submodel absent/unreadable — permissive pass
    REJECTED = "rejected"                 # hard failure


@dataclass
class CheckOutcome:
    """Result of one dimension's check, with a reason and the path taken."""

    ok: bool
    path: MatchPath
    reason: str = ""

    @property
    def is_permissive(self) -> bool:
        """True when this passed only because the offered side imposed no constraint."""
        return self.ok and self.path in (MatchPath.NO_CONSTRAINT, MatchPath.TYPE_ONLY)


@dataclass
class MatchResult:
    """Aggregate outcome of matching one step against one offered capability."""

    ok: bool
    outcomes: dict[str, CheckOutcome] = field(default_factory=dict)
    reason: str = ""

    def summary(self) -> str:
        """One-line per-dimension trace, e.g. 'parameters=range-ok components=no-constraint'."""
        return " ".join(f"{dim}={oc.path.value}" for dim, oc in self.outcomes.items())


# ─────────────────────────── offered parsing ──────────────────────────────

@dataclass
class OfferedLeaf:
    """A flattened leaf of an offered capability's Parameters tree.

    ``rng`` is ``(min, max)`` when the leaf declares a range (either a ``Range``
    element or a ``Property`` with ``range_min``/``range_max`` qualifiers), else
    ``None`` (no range constraint). ``semantic_id`` is captured for the Phase 2
    switch to identity-semanticId keying.
    """

    id_short: str
    semantic_id: str
    rng: Optional[tuple[float, float]]


@dataclass
class OfferedCapability:
    """Everything the matcher needs from one offered-capability detail submodel."""

    parameters: dict[str, OfferedLeaf]      # keyed by idShort (Phase 1)
    supported_components: list[str]
    allowed_materials: list[str]
    transformations: list[dict]             # [{"name", "input_types", "output_types"}]

    @property
    def is_empty(self) -> bool:
        """True when the submodel declared no constraints at all (fully permissive)."""
        return not (
            self.parameters
            or self.supported_components
            or self.allowed_materials
            or self.transformations
        )


def _semantic_id(elem: dict) -> str:
    """Primary semantic IRI of a BaSyx v3 element dict (keys[-1].value), or ''."""
    keys = (elem.get("semanticId") or {}).get("keys", [])
    return keys[-1].get("value", "") if keys else ""


def _to_float(raw) -> Optional[float]:
    """Coerce a (possibly string) AAS value to float; None if not numeric."""
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _range_of(elem: dict) -> Optional[tuple[float, float]]:
    """Extract (min, max) from a Range element or a Property's range qualifiers.

    Returns None when the element declares no range (a plain Property, or a
    Range/qualifier pair whose bounds aren't numeric).
    """
    model_type = elem.get("modelType", "")
    if model_type == "Range":
        lo, hi = _to_float(elem.get("min")), _to_float(elem.get("max"))
        return (lo, hi) if lo is not None and hi is not None else None

    lo = hi = None
    for q in elem.get("qualifiers", []) or []:
        qtype = q.get("type", "")
        if qtype == "range_min":
            lo = _to_float(q.get("value"))
        elif qtype == "range_max":
            hi = _to_float(q.get("value"))
    return (lo, hi) if lo is not None and hi is not None else None


def _flatten_offered_params(elements: list, into: dict[str, OfferedLeaf]) -> None:
    """Walk an offered Parameters element list, collecting leaf ranges by idShort.

    SubmodelElementCollections (e.g. TargetPosition) are recursed into.
    MultiLanguageProperties (e.g. OperationLabel) and other non-constraint leaves
    are skipped — they carry no matchable value.
    """
    for elem in elements or []:
        id_short = elem.get("idShort", "")
        model_type = elem.get("modelType", "")
        if not id_short:
            continue
        if model_type == "SubmodelElementCollection":
            children = elem.get("value")
            if isinstance(children, list):
                _flatten_offered_params(children, into)
            continue
        if model_type == "MultiLanguageProperty":
            continue
        if model_type in ("Property", "Range"):
            into[id_short] = OfferedLeaf(
                id_short=id_short,
                semantic_id=_semantic_id(elem),
                rng=_range_of(elem),
            )


def _string_list(elem: Optional[dict]) -> list[str]:
    """Read a SubmodelElementList/collection of string Properties into a list."""
    if not elem:
        return []
    out = []
    for child in elem.get("value", []) or []:
        if isinstance(child, dict):
            v = child.get("value")
            if isinstance(v, str) and v:
                out.append(v)
    return out


def _parse_transformations(elem: Optional[dict]) -> list[dict]:
    """Parse a ProcessTransformations collection into a list of input/output sets.

    Each transformation entry is a collection holding InputTypes and OutputTypes
    collections, each containing a ComponentTypeReference list of type IRIs.
    """
    if not elem:
        return []
    transformations = []
    for entry in elem.get("value", []) or []:
        if not isinstance(entry, dict):
            continue
        children = entry.get("value", []) or []
        inputs = _component_type_refs(_find(children, "InputTypes"))
        outputs = _component_type_refs(_find(children, "OutputTypes"))
        if inputs or outputs:
            transformations.append({
                "name": entry.get("idShort", ""),
                "input_types": inputs,
                "output_types": outputs,
            })
    return transformations


def _component_type_refs(types_coll: Optional[dict]) -> list[str]:
    """Pull the ComponentTypeReference string list out of an InputTypes/OutputTypes
    collection (which wraps a list element of the same name)."""
    if not types_coll:
        return []
    ctr = _find(types_coll.get("value", []) or [], "ComponentTypeReference")
    return _string_list(ctr)


def _find(elements: list, target: str) -> Optional[dict]:
    """Non-recursive idShort lookup within a single element list."""
    for elem in elements or []:
        if isinstance(elem, dict) and elem.get("idShort") == target:
            return elem
    return None


def parse_offered_capability(submodel: Optional[dict]) -> Optional[OfferedCapability]:
    """Parse an offered-capability detail submodel dict into an OfferedCapability.

    Returns None when ``submodel`` is falsy (unfetchable) so the caller can apply
    the TYPE_ONLY permissive fallback.
    """
    if not submodel:
        return None
    top = submodel.get("submodelElements", []) or []

    params: dict[str, OfferedLeaf] = {}
    params_coll = _find(top, "Parameters")
    if params_coll:
        _flatten_offered_params(params_coll.get("value", []) or [], params)

    return OfferedCapability(
        parameters=params,
        supported_components=_string_list(_find(top, "SupportedComponents")),
        allowed_materials=_string_list(_find(top, "AllowedMaterials")),
        transformations=_parse_transformations(_find(top, "ProcessTransformations")),
    )


# ─────────────────────────── step parsing ─────────────────────────────────

@dataclass
class StepLeaf:
    """A flattened work-order parameter leaf: its idShort, value, and semanticId."""

    id_short: str
    value: object
    semantic_id: str = ""


def _step_semantic_id(body: dict) -> str:
    """Read a work-order leaf's semanticId (workorder_builder emits 'SemanticId')."""
    return body.get("SemanticId") or body.get("semanticId") or body.get("semantic_id") or ""


def flatten_step_params(step_params: Optional[dict]) -> dict[str, StepLeaf]:
    """Flatten a work-order step's Parameters tree to {leaf_idShort: StepLeaf}.

    A leaf is a dict carrying a 'value' (optionally alongside 'SemanticId' /
    'semanticId'); other dicts are recursed into. Mirrors the Line Controller's
    ``_flatten_step_params`` but also captures each leaf's semanticId.
    """
    flat: dict[str, StepLeaf] = {}

    def is_leaf(node) -> bool:
        return isinstance(node, dict) and "value" in node and (
            "SemanticId" in node or "semanticId" in node or "semantic_id" in node
            or len(node) <= 2
        )

    def walk(node) -> None:
        if not isinstance(node, dict):
            return
        for name, body in node.items():
            if is_leaf(body):
                flat[name] = StepLeaf(name, body["value"], _step_semantic_id(body))
            elif isinstance(body, dict):
                walk(body)
            else:
                flat[name] = StepLeaf(name, body, "")

    walk(step_params or {})
    return flat


# ─────────────────────────── checks ───────────────────────────────────────

# Work-order idShorts that map to a differently-named offered leaf. Used only in
# the idShort fallback path; once both sides carry identity semanticIds the
# semanticId path matches first and this map becomes inert. Mirrors
# capability_matcher.PARAMETER_ALIASES.
PARAMETER_ALIASES = {
    "HolePlacement_X": "XPos",
    "HolePlacement_Y": "YPos",
}


def _unique_semantic_index(offered: OfferedCapability) -> dict[str, OfferedLeaf]:
    """Map identity semanticId -> offered leaf, but only for semanticIds carried by
    exactly one leaf. A semanticId shared by several leaves (e.g. the unit
    ``…/mm`` before migration) is not a usable identity and is excluded, so the
    matcher falls back to idShort for those — safe on pre-migration data."""
    counts: dict[str, int] = {}
    for leaf in offered.parameters.values():
        if leaf.semantic_id:
            counts[leaf.semantic_id] = counts.get(leaf.semantic_id, 0) + 1
    return {
        leaf.semantic_id: leaf
        for leaf in offered.parameters.values()
        if leaf.semantic_id and counts[leaf.semantic_id] == 1
    }


def check_parameters(
    step_leaves: dict[str, StepLeaf],
    offered: OfferedCapability,
    strict: bool = False,
) -> CheckOutcome:
    """Every work-order parameter must fit the offered capability.

    A leaf is matched to its offered counterpart by identity semanticId when that
    semanticId is unique on the offered side, else by idShort (with
    PARAMETER_ALIASES). If the matched offered leaf declares a range, the value
    must fall inside it. Unknown leaves reject — except when the offered side
    declares no parameters at all (permissive).
    """
    if not offered.parameters:
        oc = CheckOutcome(True, MatchPath.NO_CONSTRAINT,
                          "offered capability declares no parameters")
        return _maybe_strict(oc, strict)

    by_semantic = _unique_semantic_index(offered)
    saw_range = False
    matched_by_sem = False

    for name, sleaf in step_leaves.items():
        leaf = None
        resolved = name
        if sleaf.semantic_id and sleaf.semantic_id in by_semantic:
            leaf = by_semantic[sleaf.semantic_id]
            matched_by_sem = True
            resolved = f"{name} (sem={sleaf.semantic_id})"
        if leaf is None:
            leaf = offered.parameters.get(name)
        if leaf is None and name in PARAMETER_ALIASES:
            resolved = PARAMETER_ALIASES[name]
            leaf = offered.parameters.get(resolved)
        if leaf is None:
            return CheckOutcome(
                False, MatchPath.REJECTED,
                f"work-order parameter '{name}' has no matching leaf in the capability",
            )
        if leaf.rng is not None:
            v = _to_float(sleaf.value)
            if v is None:
                return CheckOutcome(
                    False, MatchPath.REJECTED,
                    f"parameter '{resolved}' value {sleaf.value!r} is not numeric",
                )
            lo, hi = leaf.rng
            if not (lo <= v <= hi):
                return CheckOutcome(
                    False, MatchPath.REJECTED,
                    f"parameter '{resolved}'={v} outside allowed range [{lo}, {hi}]",
                )
            saw_range = True

    key = "semanticId" if matched_by_sem else "idShort"
    return CheckOutcome(
        True,
        MatchPath.RANGE_OK if saw_range else MatchPath.PROPERTY_OK,
        f"matched-by-{key}",
    )


def _component_type(url: str) -> str:
    """Reduce a Shells URL to '/Shells/<Category>/<Type>', dropping any per-instance
    suffix. Non-URL input (bare names like 'BottomCoverALU') passes through."""
    if not isinstance(url, str):
        return url
    parts = url.split("/")
    try:
        idx = parts.index("Shells")
    except ValueError:
        return url
    return "/".join(parts[: idx + 3])


def check_components(
    component_iris: list[str],
    offered: OfferedCapability,
    strict: bool = False,
) -> CheckOutcome:
    """Every component type must be in the offered SupportedComponents.

    Empty SupportedComponents means no restriction (permissive).
    """
    supported = offered.supported_components
    if not supported:
        return _maybe_strict(
            CheckOutcome(True, MatchPath.NO_CONSTRAINT, "no SupportedComponents declared"),
            strict,
        )
    if not component_iris:
        return CheckOutcome(True, MatchPath.SET_OK)
    supported_types = {_component_type(s) for s in supported}
    for c in component_iris:
        if _component_type(c) not in supported_types:
            return CheckOutcome(
                False, MatchPath.REJECTED,
                f"component '{c}' (type '{_component_type(c)}') not in {sorted(supported_types)}",
            )
    return CheckOutcome(True, MatchPath.SET_OK)


def check_materials(
    material: Optional[str],
    offered: OfferedCapability,
    strict: bool = False,
) -> CheckOutcome:
    """Material must be in the offered AllowedMaterials (full URL or basename).

    Empty AllowedMaterials means no restriction. Unlike the Line Controller, an
    *unresolved* material (None) here is treated as no-constraint, not a reject —
    the MES often can't resolve the per-step material, and rejecting would wrongly
    drop valid lines.
    """
    allowed = offered.allowed_materials
    if not allowed:
        return _maybe_strict(
            CheckOutcome(True, MatchPath.NO_CONSTRAINT, "no AllowedMaterials declared"),
            strict,
        )
    if material is None:
        return _maybe_strict(
            CheckOutcome(True, MatchPath.TYPE_ONLY, "work-order material unresolved — permissive"),
            strict,
        )
    if material in allowed:
        return CheckOutcome(True, MatchPath.SET_OK)
    basenames = {url.rsplit("/", 1)[-1] for url in allowed}
    if material in basenames:
        return CheckOutcome(True, MatchPath.SET_OK)
    return CheckOutcome(
        False, MatchPath.REJECTED,
        f"material '{material}' not in allowed list {allowed}",
    )


def check_transformation(
    step_inputs: list[str],
    step_outputs: list[str],
    offered: OfferedCapability,
    strict: bool = False,
) -> CheckOutcome:
    """The step's (inputs, outputs) type-IRI sets must equal one offered transformation.

    Empty offered transformations means no constraint. ``step_inputs`` /
    ``step_outputs`` MUST be resolved type IRIs (the caller resolves ingredient
    IDs first) — comparing raw ingredient IDs against type IRIs would never match.
    """
    if not offered.transformations:
        return _maybe_strict(
            CheckOutcome(True, MatchPath.NO_CONSTRAINT, "no ProcessTransformations declared"),
            strict,
        )
    if not step_inputs and not step_outputs:
        return CheckOutcome(True, MatchPath.NO_CONSTRAINT, "step requests no transformation")
    wanted_in, wanted_out = set(step_inputs), set(step_outputs)
    for t in offered.transformations:
        if (set(t.get("input_types") or []) == wanted_in
                and set(t.get("output_types") or []) == wanted_out):
            return CheckOutcome(True, MatchPath.SET_OK)
    return CheckOutcome(
        False, MatchPath.REJECTED,
        f"no transformation matches inputs={sorted(wanted_in)} outputs={sorted(wanted_out)} "
        f"(offered: {[t.get('name') for t in offered.transformations]})",
    )


def _maybe_strict(oc: CheckOutcome, strict: bool) -> CheckOutcome:
    """In strict mode, downgrade a permissive pass to a hard failure."""
    if strict and oc.is_permissive:
        return CheckOutcome(False, MatchPath.REJECTED,
                            f"strict mode: {oc.reason or 'permissive fallback'} not allowed")
    return oc


# ─────────────────────────── top-level match ──────────────────────────────

def match_step(
    step_info: dict,
    offered_submodel: Optional[dict],
    *,
    strict: bool = False,
) -> MatchResult:
    """Match one work-order step against one offered-capability detail submodel.

    Args:
        step_info: dict with keys ``Parameters`` (work-order param tree),
            ``ComponentTypes`` (resolved type IRIs to check against
            SupportedComponents), ``Material`` (resolved material or None),
            ``InputTypes`` / ``OutputTypes`` (resolved transformation type IRIs).
        offered_submodel: the raw detail submodel dict (or None if unfetchable —
            yields a permissive TYPE_ONLY pass unless ``strict``).
        strict: turn permissive fallbacks into failures.

    Returns:
        MatchResult with per-dimension outcomes and an overall ``ok``.
    """
    offered = parse_offered_capability(offered_submodel)
    if offered is None:
        oc = _maybe_strict(
            CheckOutcome(True, MatchPath.TYPE_ONLY, "offered detail submodel unreadable"),
            strict,
        )
        return MatchResult(ok=oc.ok, outcomes={"detail": oc}, reason=oc.reason)

    step_flat = flatten_step_params(step_info.get("Parameters"))
    outcomes = {
        "parameters": check_parameters(step_flat, offered, strict),
        "components": check_components(step_info.get("ComponentTypes") or [], offered, strict),
        "materials": check_materials(step_info.get("Material"), offered, strict),
        "transformation": check_transformation(
            step_info.get("InputTypes") or [],
            step_info.get("OutputTypes") or [],
            offered, strict,
        ),
    }
    failed = [f"{dim}: {oc.reason}" for dim, oc in outcomes.items() if not oc.ok]
    return MatchResult(
        ok=not failed,
        outcomes=outcomes,
        reason="; ".join(failed),
    )
