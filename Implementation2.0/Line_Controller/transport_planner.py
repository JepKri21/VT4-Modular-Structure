"""Routing and transport-command helper.

The line is small enough that resources move via direct point-to-point
transport — there is no graph pathfinding. This module wraps the
LineConfiguration submodel so the pre-process planner can ask
"where do I send a shuttle to handoff with resource X?" without knowing
anything about AAS structure.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
# Parsed LineConfiguration
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ResourceLocation:
    """Where a resource sits in the line, in global (shuttle) coordinates."""
    resource_id: str       # idShort — same as MQTT client_id
    resource_iri: str      # full IRI (note: dashes, not underscores)
    x: float
    y: float
    theta: int


@dataclass(frozen=True)
class ConnectedResource:
    """One resource attached to a ConnectionPoint."""
    resource_iri: str
    zone_type: str         # e.g. "in_outfeed"
    local_x: float
    local_y: float


@dataclass(frozen=True)
class ConnectionPoint:
    """A physical location where a shuttle can handoff with one or more resources."""
    id_short: str
    global_x: float
    global_y: float
    connected: tuple[ConnectedResource, ...]


@dataclass(frozen=True)
class LineConfig:
    """Parsed LineConfiguration submodel."""
    locations: dict[str, ResourceLocation]    # idShort -> ResourceLocation
    iri_to_id: dict[str, str]                  # IRI -> idShort
    connection_points: tuple[ConnectionPoint, ...]


# ─────────────────────────────────────────────────────────────────────────────
# Parsing helpers
# ─────────────────────────────────────────────────────────────────────────────

def _find(elements, id_short: str) -> dict | None:
    for el in elements or []:
        if el.get("idShort") == id_short:
            return el
    return None


def _read_float(props, id_short: str, default: float = 0.0) -> float:
    el = _find(props, id_short)
    return float(el["value"]) if el is not None else default


def _read_int(props, id_short: str, default: int = 0) -> int:
    el = _find(props, id_short)
    return int(el["value"]) if el is not None else default


def _read_str(props, id_short: str) -> str:
    el = _find(props, id_short)
    if el is None:
        raise KeyError(f"Missing required property '{id_short}'")
    return str(el["value"])


def parse_line_config(submodel: dict) -> LineConfig:
    """Parse a LineConfiguration submodel JSON into a LineConfig.

    Args:
        submodel: the submodel JSON as returned by the BaSyx server
            (i.e. a dict with 'submodelElements').

    Returns:
        Fully-populated LineConfig.
    """
    elements = submodel.get("submodelElements", [])

    # ResourceLocations
    locations: dict[str, ResourceLocation] = {}
    iri_to_id: dict[str, str] = {}
    rl_collection = _find(elements, "ResourceLocations")
    for entry in (rl_collection or {}).get("value", []):
        id_short = entry["idShort"]
        props = entry.get("value", [])
        iri = _read_str(props, "ResourceReference")
        gloc = (_find(props, "GlobalLocation") or {}).get("value", [])
        loc = ResourceLocation(
            resource_id=id_short,
            resource_iri=iri,
            x=_read_float(gloc, "XPos"),
            y=_read_float(gloc, "YPos"),
            theta=_read_int(gloc, "ThetaAngle"),
        )
        locations[id_short] = loc
        iri_to_id[iri] = id_short

    # ConnectionPoints
    cps: list[ConnectionPoint] = []
    cp_collection = _find(elements, "ConnectionPoints")
    for cp_entry in (cp_collection or {}).get("value", []):
        cp_props = cp_entry.get("value", [])
        gloc = (_find(cp_props, "GlobalLocation") or {}).get("value", [])

        connected: list[ConnectedResource] = []
        cr_collection = _find(cp_props, "ConnectedResources")
        for res_entry in (cr_collection or {}).get("value", []):
            res_props = res_entry.get("value", [])
            local = (_find(res_props, "LocalLocation") or {}).get("value", [])
            connected.append(ConnectedResource(
                resource_iri=_read_str(res_props, "ResourceReference"),
                zone_type=_read_str(res_props, "ZoneType"),
                local_x=_read_float(local, "XPos"),
                local_y=_read_float(local, "YPos"),
            ))

        cps.append(ConnectionPoint(
            id_short=cp_entry["idShort"],
            global_x=_read_float(gloc, "XPos"),
            global_y=_read_float(gloc, "YPos"),
            connected=tuple(connected),
        ))

    return LineConfig(
        locations=locations,
        iri_to_id=iri_to_id,
        connection_points=tuple(cps),
    )


def load_line_config_from_file(path: str | Path) -> LineConfig:
    """Load and parse a LineConfiguration submodel from a JSON file."""
    with open(path) as f:
        return parse_line_config(json.load(f))


# ─────────────────────────────────────────────────────────────────────────────
# Transport planner
# ─────────────────────────────────────────────────────────────────────────────

class TransportPlanner:
    """Provides positions and Transport-command parameters for the pre-process planner.

    Does no MQTT, no pathfinding. Pure lookups over the LineConfiguration.
    """

    def __init__(
        self,
        line_config: LineConfig,
        default_speed: float = 0.2,
        default_accel: float = 0.5,
    ) -> None:
        self.config = line_config
        self.default_speed = default_speed
        self.default_accel = default_accel

    # ── Position lookup ──────────────────────────────────────────────────────

    def handoff_position(self, resource_id: str) -> tuple[float, float]:
        """Global (x, y) where a shuttle should sit to handoff with a resource.

        Args:
            resource_id: idShort of the resource (e.g. "Drilling_12345678").

        Returns:
            (x, y) in shuttle global coordinates.

        Raises:
            ValueError: if the resource is unknown or has no connection point.
        """
        loc = self.config.locations.get(resource_id)
        if loc is None:
            raise ValueError(f"Resource '{resource_id}' not in line configuration")

        for cp in self.config.connection_points:
            for cr in cp.connected:
                if cr.resource_iri == loc.resource_iri:
                    return (cp.global_x, cp.global_y)

        raise ValueError(f"No connection point connects to resource '{resource_id}'")

    def resource_position(self, resource_id: str) -> tuple[float, float]:
        """Global (x, y) of the resource itself (its center, not the handoff zone)."""
        loc = self.config.locations.get(resource_id)
        if loc is None:
            raise ValueError(f"Resource '{resource_id}' not in line configuration")
        return (loc.x, loc.y)

    # ── Command-parameter builder ────────────────────────────────────────────

    def transport_params(
        self,
        target_position: tuple[float, float],
        component_reference: str,
        speed_constraint: float | None = None,
        accel_constraint: float | None = None,
    ) -> dict:
        """Build the `parameters` dict for a Transport-skill CommandMessage.

        Args:
            target_position: where the shuttle should move to (global xy).
            component_reference: IRI of the part the shuttle is (or will be) carrying.
            speed_constraint: m/s; falls back to default_speed.
            accel_constraint: m/s^2; falls back to default_accel.
        """
        return {
            "SpeedConstraint": self.default_speed if speed_constraint is None else speed_constraint,
            "AccelerationConstraint": self.default_accel if accel_constraint is None else accel_constraint,
            "TargetPosition": {
                "XPos": float(target_position[0]),
                "YPos": float(target_position[1]),
            },
            "ComponentReference": component_reference,
        }

    def handoff_params(
        self,
        handoff_position: tuple[float, float],
        component_reference: str,
    ) -> dict:
        """Build the `parameters` dict for a Handoff-skill CommandMessage."""
        return {
            "TargetPosition": {
                "XPos": float(handoff_position[0]),
                "YPos": float(handoff_position[1]),
            },
            "ComponentReference": component_reference,
        }
