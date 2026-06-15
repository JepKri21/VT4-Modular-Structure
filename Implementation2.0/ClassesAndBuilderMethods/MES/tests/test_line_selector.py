"""Unit tests for line_selector with a stubbed basyx_client (stdlib unittest).

Run from the MES directory:
    python -m unittest tests.test_line_selector -v
"""

import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import line_selector  # noqa: E402
import basyx_client  # noqa: E402


# ─── fixtures ───────────────────────────────────────────────────────────────

LINE_IRI = "https://aausmartlab.org/Shells/Resources/ProductionLine/Line1"
SERVICE_IRI = "https://aausmartlab.org/Shells/Resources/ProductionLine/Line1/ServiceOffered"
DRILL_OFFERED_IRI = "https://aausmartlab.org/Shells/Resources/Drilling-1/DrillingCapabilityOffered"
DRILL_CAP_IRI = "https://aausmartlab.org/Submodels/Capability/Drilling"
BOTTOMCOVER = "https://aausmartlab.org/Shells/Component/BottomCover"


def _ref(iri):
    return {"value": {"keys": [{"value": iri}]}}


def _line_shell():
    return {
        "id": LINE_IRI,
        "idShort": "Line1",
        "submodels": [{"keys": [{"value": SERVICE_IRI}]}],
    }


def _service_offered_submodel():
    return {
        "submodelElements": [{
            "idShort": "OfferedCapabilities",
            "modelType": "SubmodelElementCollection",
            "value": [{
                "idShort": "Drilling_0",
                "modelType": "SubmodelElementCollection",
                "value": [
                    {"idShort": "CapabilityType", "modelType": "Property", "value": "Drilling"},
                    dict(_ref(DRILL_OFFERED_IRI), idShort="CapabilityReference",
                         modelType="ReferenceElement"),
                ],
            }],
        }]
    }


def _drilling_offered_submodel(lo=1.0, hi=20.0):
    return {
        "submodelElements": [{
            "idShort": "Parameters", "modelType": "SubmodelElementCollection",
            "value": [{
                "idShort": "HoleDiameter", "modelType": "Property",
                "semanticId": {"keys": [{"value": "S/mm"}]},
                "valueType": "xs:float",
                "qualifiers": [
                    {"type": "range_min", "value": str(lo)},
                    {"type": "range_max", "value": str(hi)},
                ],
            }],
        }]
    }


def _workorder(diameter):
    """Minimal stand-in for WorkOrderMessage (select_line only reads attributes)."""
    return types.SimpleNamespace(
        ingredients={"BottomCover_0": {"ComponentTypeReference": BOTTOMCOVER}},
        properties={"BottomCover_0": {}},
        process_steps={
            "BottomCover_0": {
                "ProcessStep1": {
                    "CapabilityReference": DRILL_CAP_IRI,
                    "Parameters": {"HoleDiameter": {"SemanticId": "S/mm", "value": diameter}},
                    "ProcessTransformations": {
                        "InputTypes": ["BottomCover_0"],
                        "OutputTypes": ["BottomCover_0"],
                    },
                },
            },
        },
    )


class _StubBasyx:
    """Context-manager that patches basyx_client's network calls with fixtures."""

    def __init__(self, shells, submodels):
        self.shells, self.submodels = shells, submodels
        self._orig = {}

    def __enter__(self):
        self._orig["list_shells"] = basyx_client.list_shells
        self._orig["fetch_submodel"] = basyx_client.fetch_submodel
        basyx_client.list_shells = lambda *a, **k: self.shells
        basyx_client.fetch_submodel = lambda iri, *a, **k: self.submodels.get(iri)
        return self

    def __exit__(self, *exc):
        basyx_client.list_shells = self._orig["list_shells"]
        basyx_client.fetch_submodel = self._orig["fetch_submodel"]


# ─── tests ────────────────────────────────────────────────────────────────

class TestSelectLine(unittest.TestCase):
    def _submodels(self, drill=None):
        return {
            SERVICE_IRI: _service_offered_submodel(),
            DRILL_OFFERED_IRI: drill if drill is not None else _drilling_offered_submodel(),
        }

    def test_in_range_selects_line(self):
        with _StubBasyx([_line_shell()], self._submodels()):
            self.assertEqual(line_selector.select_line(_workorder(5.0)), "Line1")

    def test_out_of_range_rejects_with_reason(self):
        with _StubBasyx([_line_shell()], self._submodels()):
            with self.assertRaises(ValueError) as ctx:
                line_selector.select_line(_workorder(25.0))
        self.assertIn("HoleDiameter", str(ctx.exception))

    def test_unfetchable_detail_is_permissive(self):
        # Detail submodel missing -> permissive type-only match still selects.
        subs = {SERVICE_IRI: _service_offered_submodel()}  # no DRILL_OFFERED_IRI
        with _StubBasyx([_line_shell()], subs):
            self.assertEqual(line_selector.select_line(_workorder(25.0)), "Line1")

    def test_strict_rejects_unfetchable_detail(self):
        subs = {SERVICE_IRI: _service_offered_submodel()}
        with _StubBasyx([_line_shell()], subs):
            with self.assertRaises(ValueError):
                line_selector.select_line(_workorder(5.0), strict=True)

    def test_transformation_resolution(self):
        # Offered transformation declared in type IRIs; step carries ingredient IDs.
        # Resolution must turn BottomCover_0 -> BottomCover type IRI so it matches.
        drill = _drilling_offered_submodel()
        drill["submodelElements"].append({
            "idShort": "ProcessTransformations", "modelType": "SubmodelElementCollection",
            "value": [{
                "idShort": "T1", "modelType": "SubmodelElementCollection",
                "value": [
                    {"idShort": "InputTypes", "modelType": "SubmodelElementCollection",
                     "value": [{"idShort": "ComponentTypeReference", "modelType": "SubmodelElementList",
                                "value": [{"modelType": "Property", "value": BOTTOMCOVER}]}]},
                    {"idShort": "OutputTypes", "modelType": "SubmodelElementCollection",
                     "value": [{"idShort": "ComponentTypeReference", "modelType": "SubmodelElementList",
                                "value": [{"modelType": "Property", "value": BOTTOMCOVER}]}]},
                ],
            }],
        })
        with _StubBasyx([_line_shell()], self._submodels(drill)):
            self.assertEqual(line_selector.select_line(_workorder(5.0)), "Line1")

    def test_no_lines_raises(self):
        with _StubBasyx([], {}):
            with self.assertRaises(ValueError):
                line_selector.select_line(_workorder(5.0))

    def test_missing_capability_type_rejects(self):
        wo = _workorder(5.0)
        wo.process_steps["BottomCover_0"]["ProcessStep1"]["CapabilityReference"] = (
            "https://aausmartlab.org/Submodels/Capability/Milling"
        )
        with _StubBasyx([_line_shell()], self._submodels()):
            with self.assertRaises(ValueError) as ctx:
                line_selector.select_line(wo)
        self.assertIn("no offered capability", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
