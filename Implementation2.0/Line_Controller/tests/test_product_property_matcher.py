"""Tests for the Phase 3 product-property matcher changes: collision-aware
semanticId property matching + material IRI/basename tolerance.

Run from the Line_Controller directory:
    python -m unittest tests.test_product_property_matcher -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from product_property_matcher import ConstraintEvaluator  # noqa: E402
from ClassesAndBuilderMethods.InformationModels import MessageStructure as MS  # noqa: E402

MAT = "https://aausmartlab.org/Semantics/Material"
COLOR = "https://aausmartlab.org/Semantics/Color"
MM = "https://aausmartlab.org/Semantics/mm"


def req(name, sem, value):
    return MS.RequestedProperty(name=name, semantic_id=sem, value=value)


def act(name, sem, value):
    return MS.NormalizedProperty(name=name, semantic_id=sem, value=value, value_type="xs:string", unit=None)


def requested(collection, props):
    return MS.RequestedConstraints(
        ingredient_id="x",
        collections={collection: MS.RequestedCollection(
            name=collection, properties={p.name: p for p in props})},
    )


def actual(collection, props, sem=None):
    return MS.ComponentProperties(
        component_id="c",
        collections={collection: MS.PropertyCollection(
            name=collection, semantic_id=sem, properties={p.name: p for p in props})},
    )


class TestSemanticMatching(unittest.TestCase):
    def setUp(self):
        self.ev = ConstraintEvaluator()

    def test_match_by_semantic_across_idshort_difference(self):
        # Requested idShort "Material" vs actual idShort "Mat" — same identity sem.
        r = requested("MaterialProperties", [req("Material", MAT, "ABS")])
        a = actual("MaterialProperties", [act("Mat", MAT, "ABS")])
        self.assertTrue(self.ev.evaluate_constraints(r, a).matches)

    def test_shared_unit_semantic_falls_back_to_name(self):
        # Length/Width share the unit sem (…/mm) → non-unique → match by name.
        r = requested("PhysicalDimensions", [req("Length", MM, 10), req("Width", MM, 5)])
        a = actual("PhysicalDimensions", [act("Length", MM, 10), act("Width", MM, 5)])
        self.assertTrue(self.ev.evaluate_constraints(r, a).matches)

    def test_value_mismatch_fails(self):
        r = requested("PhysicalDimensions", [req("Length", MM, 10)])
        a = actual("PhysicalDimensions", [act("Length", MM, 99)])
        res = self.ev.evaluate_constraints(r, a)
        self.assertFalse(res.matches)
        self.assertEqual(res.failed_properties[0].reason, "Value mismatch")

    def test_semantic_mismatch_on_name_path_fails(self):
        # Same idShort, different (non-unique-ish) semantics on the name-fallback
        # path → real semantic mismatch is still caught.
        r = requested("MaterialProperties", [req("Material", MAT, "ABS")])
        a = actual("MaterialProperties", [act("Material", COLOR, "ABS")])
        res = self.ev.evaluate_constraints(r, a)
        self.assertFalse(res.matches)
        self.assertEqual(res.failed_properties[0].reason, "Semantic ID mismatch")

    def test_missing_property(self):
        r = requested("MaterialProperties", [req("Material", MAT, "ABS")])
        a = actual("MaterialProperties", [act("Color", COLOR, "Black")])
        res = self.ev.evaluate_constraints(r, a)
        self.assertFalse(res.matches)
        self.assertEqual(res.missing_properties[0].reason, "Property missing")


class TestMaterialIriTolerance(unittest.TestCase):
    def setUp(self):
        self.ev = ConstraintEvaluator()

    def test_iri_request_matches_bare_actual(self):
        # Work order carries the canonical IRI; component stores the bare name.
        r = requested("MaterialProperties",
                      [req("Material", MAT, "https://aausmartlab.org/Materials/ABS")])
        a = actual("MaterialProperties", [act("Material", MAT, "ABS")])
        self.assertTrue(self.ev.evaluate_constraints(r, a).matches)

    def test_iri_request_mismatch_still_fails(self):
        r = requested("MaterialProperties",
                      [req("Material", MAT, "https://aausmartlab.org/Materials/PLA")])
        a = actual("MaterialProperties", [act("Material", MAT, "ABS")])
        self.assertFalse(self.ev.evaluate_constraints(r, a).matches)


if __name__ == "__main__":
    unittest.main()
