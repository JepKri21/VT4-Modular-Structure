"""Unit tests for capability_param_matcher (stdlib unittest — no pytest needed).

Run from the MES directory:
    python -m unittest tests.test_capability_param_matcher -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import capability_param_matcher as cpm  # noqa: E402
from capability_param_matcher import MatchPath  # noqa: E402


# ─── AAS JSON fixtures (shapes confirmed against the generator's out.json) ───

def _prop_qual_range(id_short, sem, lo, hi, value=None):
    """A Property with range_min/range_max qualifiers (values are strings, as BaSyx emits)."""
    elem = {
        "idShort": id_short,
        "modelType": "Property",
        "semanticId": {"keys": [{"value": sem}]},
        "qualifiers": [
            {"type": "range_min", "valueType": "xs:float", "value": str(lo)},
            {"type": "range_max", "valueType": "xs:float", "value": str(hi)},
        ],
        "valueType": "xs:float",
    }
    if value is not None:
        elem["value"] = str(value)
    return elem


def _range(id_short, sem, lo, hi):
    return {
        "idShort": id_short, "modelType": "Range",
        "semanticId": {"keys": [{"value": sem}]},
        "valueType": "xs:float", "min": str(lo), "max": str(hi),
    }


def _plain_prop(id_short, sem, value):
    return {
        "idShort": id_short, "modelType": "Property",
        "semanticId": {"keys": [{"value": sem}]},
        "valueType": "xs:string", "value": value,
    }


def _str_list(id_short, items):
    return {
        "idShort": id_short, "modelType": "SubmodelElementList",
        "value": [{"modelType": "Property", "valueType": "xs:string", "value": i} for i in items],
    }


def _collection(id_short, children):
    return {"idShort": id_short, "modelType": "SubmodelElementCollection", "value": children}


def drilling_submodel():
    """An offered drilling capability with both qualifier-range and Range params,
    a nested TargetPosition, SupportedComponents, AllowedMaterials, and a transformation."""
    return {
        "submodelElements": [
            _collection("Parameters", [
                _prop_qual_range("HoleDiameter", "S/mm", 1.0, 20.0),
                _range("DrillDepth", "S/mm", 0.0, 200.0),
                _collection("TargetPosition", [
                    _range("XPos", "S/mm", 0.0, 100.0),
                    _range("YPos", "S/mm", 0.0, 50.0),
                ]),
                {"idShort": "OperationLabel", "modelType": "MultiLanguageProperty",
                 "value": [{"language": "en", "text": "Drill"}]},
            ]),
            _str_list("SupportedComponents", [
                "https://aausmartlab.org/Shells/Component/BottomCover",
            ]),
            _str_list("AllowedMaterials", ["https://aausmartlab.org/Materials/PLA"]),
            _collection("ProcessTransformations", [
                _collection("T1", [
                    _collection("InputTypes", [
                        _str_list("ComponentTypeReference",
                                  ["https://aausmartlab.org/Shells/Component/BottomCover"]),
                    ]),
                    _collection("OutputTypes", [
                        _str_list("ComponentTypeReference",
                                  ["https://aausmartlab.org/Shells/Component/BottomCover"]),
                    ]),
                ]),
            ]),
        ]
    }


def step(params=None, **kw):
    base = {"Parameters": params or {}, "ComponentTypes": [], "Material": None,
            "InputTypes": [], "OutputTypes": []}
    base.update(kw)
    return base


def leaves(values, sem=None):
    """Build {idShort: StepLeaf} for check_parameters tests."""
    sem = sem or {}
    return {k: cpm.StepLeaf(k, v, sem.get(k, "")) for k, v in values.items()}


# ─────────────────────────── range parsing ────────────────────────────────

class TestRangeParsing(unittest.TestCase):
    def setUp(self):
        self.offered = cpm.parse_offered_capability(drilling_submodel())

    def test_qualifier_range_extracted(self):
        self.assertEqual(self.offered.parameters["HoleDiameter"].rng, (1.0, 20.0))

    def test_range_element_extracted(self):
        self.assertEqual(self.offered.parameters["DrillDepth"].rng, (0.0, 200.0))

    def test_nested_collection_flattened(self):
        self.assertIn("XPos", self.offered.parameters)
        self.assertEqual(self.offered.parameters["YPos"].rng, (0.0, 50.0))

    def test_mlp_skipped(self):
        self.assertNotIn("OperationLabel", self.offered.parameters)

    def test_semantic_id_captured(self):
        self.assertEqual(self.offered.parameters["HoleDiameter"].semantic_id, "S/mm")


# ─────────────────────────── parameter checks ─────────────────────────────

class TestParameters(unittest.TestCase):
    def setUp(self):
        self.offered = cpm.parse_offered_capability(drilling_submodel())

    def test_in_range_passes(self):
        oc = cpm.check_parameters(leaves({"HoleDiameter": 5.0, "DrillDepth": 100.0}), self.offered)
        self.assertTrue(oc.ok)

    def test_out_of_range_rejects_with_param_name(self):
        oc = cpm.check_parameters(leaves({"HoleDiameter": 25.0}), self.offered)
        self.assertFalse(oc.ok)
        self.assertIn("HoleDiameter", oc.reason)
        self.assertEqual(oc.path, MatchPath.REJECTED)

    def test_unknown_param_rejects(self):
        oc = cpm.check_parameters(leaves({"Nonexistent": 1.0}), self.offered)
        self.assertFalse(oc.ok)
        self.assertIn("no matching leaf", oc.reason)

    def test_alias_resolves(self):
        # HolePlacement_X (work order) -> XPos (offered) via PARAMETER_ALIASES fallback.
        oc = cpm.check_parameters(leaves({"HolePlacement_X": 50.0}), self.offered)
        self.assertTrue(oc.ok)

    def test_string_value_coerced(self):
        self.assertTrue(cpm.check_parameters(leaves({"HoleDiameter": "5.0"}), self.offered).ok)

    def test_non_numeric_value_rejects(self):
        oc = cpm.check_parameters(leaves({"HoleDiameter": "wide"}), self.offered)
        self.assertFalse(oc.ok)

    def test_empty_offered_is_permissive(self):
        empty = cpm.OfferedCapability({}, [], [], [])
        oc = cpm.check_parameters(leaves({"HoleDiameter": 999}), empty)
        self.assertTrue(oc.ok)
        self.assertEqual(oc.path, MatchPath.NO_CONSTRAINT)

    def test_shared_unit_semantic_falls_back_to_idshort(self):
        # All offered leaves share '…/mm' (pre-migration). semanticId is non-unique,
        # so matching must fall back to idShort and still work — not collide.
        oc = cpm.check_parameters(
            leaves({"HoleDiameter": 5.0}, sem={"HoleDiameter": "S/mm"}), self.offered)
        self.assertTrue(oc.ok)
        self.assertIn("idShort", oc.reason)

    def test_identity_semantic_matches_across_idshort_difference(self):
        # Offered leaf carries a unique identity semanticId; work-order leaf uses a
        # different idShort but the same identity -> matched by semanticId.
        offered = cpm.OfferedCapability(
            parameters={"BitDiameter": cpm.OfferedLeaf(
                "BitDiameter", "https://aausmartlab.org/Semantics/Parameter/HoleDiameter", (1.0, 20.0))},
            supported_components=[], allowed_materials=[], transformations=[])
        oc = cpm.check_parameters(
            leaves({"HoleDiameter": 5.0},
                   sem={"HoleDiameter": "https://aausmartlab.org/Semantics/Parameter/HoleDiameter"}),
            offered)
        self.assertTrue(oc.ok)
        self.assertIn("semanticId", oc.reason)

    def test_identity_semantic_out_of_range_rejects(self):
        offered = cpm.OfferedCapability(
            parameters={"BitDiameter": cpm.OfferedLeaf(
                "BitDiameter", "https://aausmartlab.org/Semantics/Parameter/HoleDiameter", (1.0, 20.0))},
            supported_components=[], allowed_materials=[], transformations=[])
        oc = cpm.check_parameters(
            leaves({"HoleDiameter": 99.0},
                   sem={"HoleDiameter": "https://aausmartlab.org/Semantics/Parameter/HoleDiameter"}),
            offered)
        self.assertFalse(oc.ok)


# ─────────────────────────── components / materials ───────────────────────

class TestComponentsAndMaterials(unittest.TestCase):
    def setUp(self):
        self.offered = cpm.parse_offered_capability(drilling_submodel())

    def test_supported_component_passes(self):
        comp = ["https://aausmartlab.org/Shells/Component/BottomCover/BottomCoverABSBlack"]
        self.assertTrue(cpm.check_components(comp, self.offered).ok)  # per-instance trimmed

    def test_unsupported_component_rejects(self):
        comp = ["https://aausmartlab.org/Shells/Component/TopCover"]
        self.assertFalse(cpm.check_components(comp, self.offered).ok)

    def test_no_supported_list_permissive(self):
        empty = cpm.OfferedCapability({}, [], [], [])
        self.assertEqual(cpm.check_components(["x"], empty).path, MatchPath.NO_CONSTRAINT)

    def test_material_basename_match(self):
        self.assertTrue(cpm.check_materials("PLA", self.offered).ok)

    def test_material_full_url_match(self):
        self.assertTrue(cpm.check_materials("https://aausmartlab.org/Materials/PLA", self.offered).ok)

    def test_material_mismatch_rejects(self):
        self.assertFalse(cpm.check_materials("ABS", self.offered).ok)

    def test_material_none_is_permissive(self):
        # MES divergence from LC: unresolved material must NOT reject.
        oc = cpm.check_materials(None, self.offered)
        self.assertTrue(oc.ok)
        self.assertEqual(oc.path, MatchPath.TYPE_ONLY)


# ─────────────────────────── transformation ───────────────────────────────

class TestTransformation(unittest.TestCase):
    def setUp(self):
        self.offered = cpm.parse_offered_capability(drilling_submodel())
        self.t = "https://aausmartlab.org/Shells/Component/BottomCover"

    def test_matching_sets_pass(self):
        self.assertTrue(cpm.check_transformation([self.t], [self.t], self.offered).ok)

    def test_ingredient_ids_would_fail(self):
        # Guards the universal-reject bug: unresolved ingredient IDs vs type IRIs.
        oc = cpm.check_transformation(["BottomCover_0"], ["BottomCover_0"], self.offered)
        self.assertFalse(oc.ok)

    def test_no_offered_transformation_permissive(self):
        empty = cpm.OfferedCapability({}, [], [], [])
        self.assertEqual(cpm.check_transformation(["a"], ["b"], empty).path, MatchPath.NO_CONSTRAINT)


# ─────────────────────────── step flattening ──────────────────────────────

class TestStepFlatten(unittest.TestCase):
    def test_leaf_with_semanticid(self):
        params = {"HoleDiameter": {"SemanticId": "S/mm", "value": 5.0}}
        flat = cpm.flatten_step_params(params)
        self.assertEqual(flat["HoleDiameter"].value, 5.0)
        self.assertEqual(flat["HoleDiameter"].semantic_id, "S/mm")

    def test_nested_collection(self):
        params = {"TargetPosition": {"XPos": {"value": 40.0}, "YPos": {"value": 10.0}}}
        flat = cpm.flatten_step_params(params)
        self.assertEqual({k: v.value for k, v in flat.items()}, {"XPos": 40.0, "YPos": 10.0})


# ─────────────────────────── top-level match ──────────────────────────────

class TestMatchStep(unittest.TestCase):
    def test_full_pass(self):
        s = step(
            params={"HoleDiameter": {"value": 5.0}},
            ComponentTypes=["https://aausmartlab.org/Shells/Component/BottomCover"],
            Material="PLA",
            InputTypes=["https://aausmartlab.org/Shells/Component/BottomCover"],
            OutputTypes=["https://aausmartlab.org/Shells/Component/BottomCover"],
        )
        res = cpm.match_step(s, drilling_submodel())
        self.assertTrue(res.ok, res.reason)
        self.assertEqual(res.outcomes["parameters"].path, MatchPath.RANGE_OK)

    def test_out_of_range_fails(self):
        s = step(params={"HoleDiameter": {"value": 99.0}})
        res = cpm.match_step(s, drilling_submodel())
        self.assertFalse(res.ok)
        self.assertIn("HoleDiameter", res.reason)

    def test_unfetchable_submodel_permissive(self):
        res = cpm.match_step(step(), None)
        self.assertTrue(res.ok)
        self.assertEqual(res.outcomes["detail"].path, MatchPath.TYPE_ONLY)

    def test_strict_rejects_unfetchable(self):
        res = cpm.match_step(step(), None, strict=True)
        self.assertFalse(res.ok)

    def test_strict_rejects_permissive_material(self):
        # Material None against a submodel that DOES declare AllowedMaterials.
        s = step(params={"HoleDiameter": {"value": 5.0}})
        res = cpm.match_step(s, drilling_submodel(), strict=True)
        self.assertFalse(res.ok)
        self.assertFalse(res.outcomes["materials"].ok)


if __name__ == "__main__":
    unittest.main()
