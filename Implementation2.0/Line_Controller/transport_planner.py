"""Routing and transport-command helper.

This module owns everything about *where* parts can move on the line:

- It parses the `LineConfiguration` submodel (resource locations + connection
  points) into typed structures.
- It exposes `handoff_position(resource_id)` for direct point-to-point
  lookups — still useful when storage and target share a transport.
- It builds a `LineGraph` over the connection points: a node is a
  non-transport resource (where parts live), an edge means "some transport
  resource can directly carry a part between these two". `find_route(src,
  dst)` returns the ordered list of `RouteHop`s — one per transport leg.

What this module *doesn't* do:
- Decide *which* actor of a transport pool (Shuttle1 vs Shuttle2) does a
  hop — that's the scheduler's job (occupancy + state).
- Translate a route into MQTT commands (Move, Handoff) — that's the
  pre-process planner's job, expanding each hop with the 4-case handoff
  rule between consecutive resources.

For a one-shuttle line the graph collapses to a single edge per pair and
`find_route` returns a one-hop list — exactly the behaviour we had before.
"""

from __future__ import annotations

import json
from collections import deque
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


def _read_ref(props, id_short: str) -> str:
    """Extract shell IRI from a ReferenceElement (ModelReference) element."""
    el = _find(props, id_short)
    if el is None:
        raise KeyError(f"Missing required element '{id_short}'")
    val = el.get("value")
    if isinstance(val, dict):
        keys = val.get("keys", [])
        if keys:
            return str(keys[0]["value"])
    raise ValueError(f"Cannot extract IRI from '{id_short}': unexpected shape {el!r}")


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
        iri = _read_ref(props, "ResourceReference")
        gloc = (_find(props, "GlobalLocation") or {}).get("value", [])
        loc = ResourceLocation(
            resource_id=id_short,
            resource_iri=iri,
            x=_read_float(gloc, "XPos"),
            y=_read_float(gloc, "YPos"),
            theta=_read_int(gloc, "ThetaAngle"),
        )
        # Key by full IRI — that's the unambiguous identifier and matches
        # what every caller of handoff_position / resource_position now passes
        # via ResourceEndpoint.resource_iri. id_short is kept on the value
        # and in iri_to_id for the reverse lookup.
        locations[iri] = loc
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
                resource_iri=_read_ref(res_props, "ResourceReference"),
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


def load_line_config_from_aas(
    aas_server_base: str,
    line_shell_prefix: str = "https://aausmartlab.org/Shells/Resources/ProductionLine/",
) -> LineConfig:
    """Fetch the active ProductionLine shell from the AAS server and parse its
    LineConfiguration submodel.

    Finds the first shell whose id starts with `line_shell_prefix` and reads
    its `<shell_id>/LineConfiguration` submodel. If multiple production-line
    shells exist, the first one returned by the server is used — adjust the
    prefix to disambiguate.
    """
    import base64
    import requests

    def _b64(value: str) -> str:
        return base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=")

    shells_resp = requests.get(f"{aas_server_base}/shells")
    shells_resp.raise_for_status()
    shells = shells_resp.json().get("result", [])

    line_shell_id = next(
        (s["id"] for s in shells if s["id"].startswith(line_shell_prefix)),
        None,
    )
    if line_shell_id is None:
        raise RuntimeError(
            f"No ProductionLine shell found on AAS server with prefix '{line_shell_prefix}'"
        )

    submodel_id = f"{line_shell_id}/LineConfiguration"
    sm_resp = requests.get(f"{aas_server_base}/submodels/{_b64(submodel_id)}")
    sm_resp.raise_for_status()
    return parse_line_config(sm_resp.json())


# ─────────────────────────────────────────────────────────────────────────────
# Graph + routing
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TransportEdge:
    """One direct transport relation between two non-transport resources.

    "Direct" means: there is a transport resource that touches a connection
    point shared with the source AND a connection point shared with the
    destination (possibly the same connection point — in that case the
    transport doesn't have to move between zones, just hand off).
    """
    transport_resource_id: str         # idShort, e.g. "Transport_12345678"
    src_connection_point: str          # idShort of the CP at the pickup side
    dst_connection_point: str          # idShort of the CP at the dropoff side
    pickup_position: tuple[float, float]
    dropoff_position: tuple[float, float]


@dataclass(frozen=True)
class RouteHop:
    """One leg of a route: one transport carries a part from A to B."""
    transport_resource_id: str
    from_resource_id: str
    to_resource_id: str
    pickup_position: tuple[float, float]
    dropoff_position: tuple[float, float]


class LineGraph:
    """Graph derived from a LineConfig. Used by `TransportPlanner.find_route`.

    Args:
        config: the parsed LineConfig.
        transport_resource_ids: idShorts of resources that are transports
            (shuttles, conveyors, AGVs). If None, transports are inferred as
            the resources that appear in 2 or more `ConnectionPoint`s — the
            usual signature of "something that moves between zones".
    """

    def __init__(
        self,
        config: LineConfig,
        transport_resource_ids: set[str] | None = None,
    ) -> None:
        self.config = config
        self.transport_resource_ids: set[str] = (
            transport_resource_ids
            if transport_resource_ids is not None
            else self._infer_transports()
        )
        # iri -> [(neighbour_iri, TransportEdge), ...]
        self._adjacency: dict[str, list[tuple[str, TransportEdge]]] = (
            self._build_adjacency()
        )

    # ── Public queries ──────────────────────────────────────────────────────

    def find_route(
        self, src_resource_id: str, dst_resource_id: str
    ) -> list[RouteHop] | None:
        """BFS over transport edges. Returns:

        - `[]` if `src == dst` (already there, no transport needed).
        - `[RouteHop, ...]` for a found path, one hop per transport leg.
        - `None` if no route exists in the current line topology.
        """
        src_iri = self._iri_for(src_resource_id)
        dst_iri = self._iri_for(dst_resource_id)
        if src_iri is None or dst_iri is None:
            return None
        if src_iri == dst_iri:
            return []

        queue: deque[tuple[str, list[RouteHop]]] = deque([(src_iri, [])])
        visited: set[str] = {src_iri}
        while queue:
            current_iri, path = queue.popleft()
            for neighbour_iri, edge in self._adjacency.get(current_iri, []):
                if neighbour_iri in visited:
                    continue
                hop = RouteHop(
                    transport_resource_id=edge.transport_resource_id,
                    from_resource_id=self._id_for(current_iri),
                    to_resource_id=self._id_for(neighbour_iri),
                    pickup_position=edge.pickup_position,
                    dropoff_position=edge.dropoff_position,
                )
                extended = path + [hop]
                if neighbour_iri == dst_iri:
                    return extended
                visited.add(neighbour_iri)
                queue.append((neighbour_iri, extended))
        return None

    def transports_between(
        self, src_resource_id: str, dst_resource_id: str
    ) -> list[str]:
        """idShorts of transport resources that can directly carry src → dst.

        Empty list means no single transport spans this pair (multi-hop needed).
        """
        src_iri = self._iri_for(src_resource_id)
        dst_iri = self._iri_for(dst_resource_id)
        if src_iri is None or dst_iri is None:
            return []
        return [
            edge.transport_resource_id
            for neighbour_iri, edge in self._adjacency.get(src_iri, [])
            if neighbour_iri == dst_iri
        ]

    # ── Construction ────────────────────────────────────────────────────────

    def _infer_transports(self) -> set[str]:
        """Resources appearing in 2+ ConnectionPoints are treated as transports."""
        counts: dict[str, int] = {}
        for cp in self.config.connection_points:
            seen_here: set[str] = set()  # don't double-count one CP
            for cr in cp.connected:
                if cr.resource_iri in seen_here:
                    continue
                seen_here.add(cr.resource_iri)
                counts[cr.resource_iri] = counts.get(cr.resource_iri, 0) + 1
        return {iri for iri, n in counts.items() if n >= 2}

    # ZoneType semantics:
    #   "infeed"      -> parts can enter the resource through this zone (receive only)
    #   "outfeed"     -> parts can leave the resource through this zone  (send only)
    #   "in_outfeed"  -> bidirectional (the common case in this lab)
    # An edge A -> B via transport T requires:
    #   * A's zone at the pickup CP allows sending  ("outfeed" or "in_outfeed")
    #   * B's zone at the dropoff CP allows receiving ("infeed" or "in_outfeed")
    _CAN_SEND = {"outfeed", "in_outfeed"}
    _CAN_RECEIVE = {"infeed", "in_outfeed"}

    def _build_adjacency(self) -> dict[str, list[tuple[str, TransportEdge]]]:
        """For each transport T, expand the (CP_src, CP_dst) cross-product into edges,
        respecting each partner's ZoneType direction.
        """
        adj: dict[str, list[tuple[str, TransportEdge]]] = {}

        for transport_iri in self.transport_resource_ids:
            transport_cps: list[tuple[ConnectionPoint, list[ConnectedResource]]] = []
            for cp in self.config.connection_points:
                if not any(cr.resource_iri == transport_iri for cr in cp.connected):
                    continue
                partners = [
                    cr for cr in cp.connected if cr.resource_iri != transport_iri
                ]
                if partners:
                    transport_cps.append((cp, partners))

            transport_id = self._id_for(transport_iri)
            for src_cp, src_partners in transport_cps:
                for dst_cp, dst_partners in transport_cps:
                    for src in src_partners:
                        if src.zone_type not in self._CAN_SEND:
                            continue
                        for dst in dst_partners:
                            if dst.zone_type not in self._CAN_RECEIVE:
                                continue
                            if src.resource_iri == dst.resource_iri:
                                continue
                            edge = TransportEdge(
                                transport_resource_id=transport_id,
                                src_connection_point=src_cp.id_short,
                                dst_connection_point=dst_cp.id_short,
                                pickup_position=(src_cp.global_x, src_cp.global_y),
                                dropoff_position=(dst_cp.global_x, dst_cp.global_y),
                            )
                            adj.setdefault(src.resource_iri, []).append(
                                (dst.resource_iri, edge)
                            )
        return adj

    # ── IRI <-> idShort helpers ─────────────────────────────────────────────

    def _iri_for(self, resource_id: str) -> str | None:
        loc = self.config.locations.get(resource_id)
        return loc.resource_iri if loc else None

    def _id_for(self, iri: str) -> str:
        if iri in self.config.iri_to_id:
            return self.config.iri_to_id[iri]
        return iri.rstrip("/").split("/")[-1]


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
        transport_resource_ids: set[str] | None = None,
    ) -> None:
        self.config = line_config
        self.default_speed = default_speed
        self.default_accel = default_accel
        self.graph = LineGraph(line_config, transport_resource_ids=transport_resource_ids)

    # ── Routing ──────────────────────────────────────────────────────────────

    def find_route(
        self, src_resource_id: str, dst_resource_id: str
    ) -> list[RouteHop] | None:
        """Shortest (BFS) transport route from src to dst.

        Returns:
            - `[]` if both are the same resource (no transport needed).
            - `[RouteHop, ...]` where each hop is a single transport leg.
            - `None` if the LineConfiguration has no path between them.
        """
        return self.graph.find_route(src_resource_id, dst_resource_id)

    def transports_between(
        self, src_resource_id: str, dst_resource_id: str
    ) -> list[str]:
        """idShorts of transports that can carry src→dst in one hop."""
        return self.graph.transports_between(src_resource_id, dst_resource_id)

    # ── Position lookup ──────────────────────────────────────────────────────

    def handoff_position(self, resource_iri: str) -> tuple[float, float]:
        """Global (x, y) where a shuttle should sit to handoff with a resource.

        Args:
            resource_iri: full AAS shell IRI of the resource (e.g.
                "https://aausmartlab.org/Shells/Resources/Drilling_<uuid>").

        Returns:
            (x, y) in shuttle global coordinates.

        Raises:
            ValueError: if the resource is unknown or has no connection point.
        """
        loc = self.config.locations.get(resource_iri)
        if loc is None:
            raise ValueError(f"Resource '{resource_iri}' not in line configuration")

        for cp in self.config.connection_points:
            for cr in cp.connected:
                if cr.resource_iri == loc.resource_iri:
                    return (cp.global_x, cp.global_y)

        raise ValueError(f"No connection point connects to resource '{resource_iri}'")

    def resource_position(self, resource_iri: str) -> tuple[float, float]:
        """Global (x, y) of the resource itself (its center, not the handoff zone)."""
        loc = self.config.locations.get(resource_iri)
        if loc is None:
            raise ValueError(f"Resource '{resource_iri}' not in line configuration")
        return (loc.x, loc.y)

    def local_handoff_position(
        self, target_resource_iri: str, transport_iri: str
    ) -> tuple[float, float]:
        """Handoff position for `target_resource_iri` expressed in
        `transport_iri`'s LOCAL coordinate frame.

        Transport stations (shuttles, conveyors) typically declare moves
        in their own local coordinate system, bounded by the table size
        (e.g. 0..6600 mm). The connection-point's global coords would be
        out of range; we need the same point in the shuttle's frame.

        Each ConnectionPoint lists every connected resource with both
        global and local coords. The local coord on the transport's
        ConnectedResource entry IS the CP location in that transport's
        frame — exactly what the CMD needs.
        """
        for cp in self.config.connection_points:
            iris = {cr.resource_iri for cr in cp.connected}
            if target_resource_iri not in iris or transport_iri not in iris:
                continue
            for cr in cp.connected:
                if cr.resource_iri == transport_iri:
                    return (cr.local_x, cr.local_y)
        raise ValueError(
            f"No connection point links transport '{transport_iri}' to "
            f"target '{target_resource_iri}'"
        )

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
