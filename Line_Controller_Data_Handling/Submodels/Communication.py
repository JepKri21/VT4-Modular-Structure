from dataclasses import dataclass

@dataclass
class CommunicationSubmodel:
    submodel_id: str
    broker: str
    protocol: str
    topic: str
    qos: int


def parse_communication_submodel(data: dict) -> CommunicationSubmodel:
    submodel_id = data.get("id")

    elements = data.get("submodelElements", [])
    if not elements:
        raise ValueError("Communication submodel has no elements")

    collection = elements[0]
    props = {p["idShort"]: p.get("value") for p in collection.get("value", [])}

    return CommunicationSubmodel(
        submodel_id=submodel_id,
        broker=props.get("Broker_Address"),
        protocol=props.get("Protocol"),
        topic=props.get("Topic"),
        qos=int(props.get("QoS", 0)),
    )