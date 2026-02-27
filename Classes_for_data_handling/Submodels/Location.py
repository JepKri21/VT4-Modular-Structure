from dataclasses import dataclass, field
from typing import List, Dict


@dataclass
class ConnectionPoint:
    connection_point_id: str
    connection_type: str


@dataclass
class ResourceConnection:
    own_connection_point_id: str
    connected_resource_id: str
    other_resource_connection_point_id: str
    x: int
    y: int


@dataclass
class LocationSubmodel:
    submodel_id: str
    building: str
    production_line: str
    connection_points: List[ConnectionPoint] = field(default_factory=list)
    resource_connections: List[ResourceConnection] = field(default_factory=list)


def parse_location_submodel(data: dict) -> LocationSubmodel:
    submodel_id = data.get("id")
    elements = data.get("submodelElements", [])

    building = ""
    production_line = ""
    connection_points = []
    resource_connections = []

    for el in elements:
        if el["idShort"] == "General_Location_Information":
            for prop in el.get("value", []):
                if prop["idShort"] == "Building":
                    building = prop.get("value", "")
                elif prop["idShort"] == "Production_Line":
                    production_line = prop.get("value", "")

        elif el["idShort"] == "Connection_Points":
            for cp_col in el.get("value", []):
                cp_id = None
                cp_type = None
                for prop in cp_col.get("value", []):
                    if prop["idShort"] == "Connection_Point_Id":
                        cp_id = prop.get("value")
                    elif prop["idShort"] == "Connection_Type":
                        cp_type = prop.get("value")
                connection_points.append(ConnectionPoint(connection_point_id=cp_id, connection_type=cp_type))

        elif el["idShort"] == "Resource_Connections":
            for rc_col in el.get("value", []):
                own_cp = None
                connected_resource_id = None
                other_cp = None
                x_val = 0
                y_val = 0
                for prop in rc_col.get("value", []):
                    if prop["idShort"] == "Own_Connection_Point_Id":
                        own_cp = prop.get("value")
                    elif prop["idShort"] == "Connected_Resource_Id":
                        connected_resource_id = prop.get("value")
                    elif prop["idShort"] == "Other_Resource_Connection_Point_Id":
                        other_cp = prop.get("value")
                    elif prop["idShort"] == "Connection_Position_X_Value":
                        x_val = int(prop.get("value", 0))
                    elif prop["idShort"] == "Connection_Position_Y_Value":
                        y_val = int(prop.get("value", 0))
                resource_connections.append(
                    ResourceConnection(
                        own_connection_point_id=own_cp,
                        connected_resource_id=connected_resource_id,
                        other_resource_connection_point_id=other_cp,
                        x=x_val,
                        y=y_val
                    )
                )

    return LocationSubmodel(
        submodel_id=submodel_id,
        building=building,
        production_line=production_line,
        connection_points=connection_points,
        resource_connections=resource_connections
    )