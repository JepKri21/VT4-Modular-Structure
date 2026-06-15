"""LC matcher tests for the Phase 2 sync: collision-aware semanticId matching and
qualifier-range handling. Pure-logic (the matcher duck-types its capability leaves),
so we fake leaves with SimpleNamespace — no MQTT/AAS deps.

Run from the Line_Controller directory:
    python -m unittest tests.test_capability_matcher_semantic -v
"""

import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from capability_matcher import CapabilityMatcher  # noqa: E402

PARAM_HOLE = "https://aausmartlab.org/Semantics/Parameter/HoleDiameter"
PARAM_DEPTH = "https://aausmartlab.org/Semantics/Parameter/DrillDepth"
UNIT_MM = "https://aausmartlab.org/Semantics/mm"


def rng(id_short, lo, hi, sem):
    return types.SimpleNamespace(id_short=id_short, min=lo, max=hi, semantic_id=sem)


def prop(id_short, value, sem):
    return types.SimpleNamespace(id_short=id_short, value=value, semantic_id=sem)


def step(name, value, sem):
    return {name: {"SemanticId": sem, "value": value}}


class TestLCMatcherSemantic(unittest.TestCase):
    def setUp(self):
        self.m = CapabilityMatcher(resource_manager=None)  # _check_parameters needs no RM

    def test_identity_semantic_matches_across_idshort(self):
        # cap leaf id_short differs (BitDiameter) but identity semanticId matches.
        cap = [rng("BitDiameter", 1.0, 20.0, PARAM_HOLE)]
        ok, reason = self.m._check_parameters(step("HoleDiameter", 5.0, PARAM_HOLE), cap)
        self.assertTrue(ok, reason)

    def test_identity_semantic_out_of_range(self):
        cap = [rng("BitDiameter", 1.0, 20.0, PARAM_HOLE)]
        ok, reason = self.m._check_parameters(step("HoleDiameter", 25.0, PARAM_HOLE), cap)
        self.assertFalse(ok)
        self.assertIn("outside allowed range", reason)

    def test_shared_unit_semantic_falls_back_to_idshort(self):
        # Pre-migration: both leaves share the unit semanticId -> non-unique ->
        # match by id_short instead of colliding.
        cap = [rng("HoleDiameter", 1.0, 20.0, UNIT_MM), rng("DrillDepth", 0.0, 200.0, UNIT_MM)]
        ok, reason = self.m._check_parameters(step("HoleDiameter", 5.0, UNIT_MM), cap)
        self.assertTrue(ok, reason)
        ok2, _ = self.m._check_parameters(step("HoleDiameter", 25.0, UNIT_MM), cap)
        self.assertFalse(ok2)

    def test_unknown_param_rejects(self):
        cap = [rng("HoleDiameter", 1.0, 20.0, PARAM_HOLE)]
        ok, reason = self.m._check_parameters(step("Nonexistent", 1.0, ""), cap)
        self.assertFalse(ok)
        self.assertIn("no matching leaf", reason)

    def test_nonrange_property_accepted(self):
        cap = [prop("Label", "x", "S/Label")]
        ok, _ = self.m._check_parameters({"Label": {"value": "y"}}, cap)
        self.assertTrue(ok)


class TestResourceManagerQualifierRange(unittest.TestCase):
    """parse_property must promote a range_min/range_max-qualified Property to a Range."""

    def test_qualifier_property_becomes_range(self):
        try:
            import resource_manager as rm
        except Exception as e:  # heavy deps unavailable in this env
            self.skipTest(f"resource_manager import failed: {e}")
        elem = {
            "idShort": "HoleDiameter", "modelType": "Property", "valueType": "xs:float",
            "value": "5.0",
            "semanticId": {"keys": [{"value": PARAM_HOLE}]},
            "qualifiers": [
                {"type": "range_min", "value": "1.0"},
                {"type": "range_max", "value": "20.0"},
            ],
        }
        parsed = rm.ResourceManager.parse_property(None, elem)
        self.assertTrue(hasattr(parsed, "min") and hasattr(parsed, "max"))
        self.assertEqual((parsed.min, parsed.max), ("1.0", "20.0"))


if __name__ == "__main__":
    unittest.main()
