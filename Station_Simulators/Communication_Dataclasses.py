from dataclasses import dataclass, asdict
from typing import List, Optional

@dataclass
class Property:
    modelType: str
    idShort: str
    valueType: str
    value: str


@dataclass
class CommunicationMethod:
    name: str
    properties: List[Property]

    def to_dict(self):
        return {
            "modelType" : "SubmodelElementCollection",
            "idShort" : self.name,
            "value" : [asdict(property) for property in self.properties]
        }
    
@dataclass
class CommunicationSubmodelData:
    communication_methods: List[CommunicationMethod]

    def to_dict(self, shell_id: str):
        return {
            "idShort": "Communication",
            "id" : f"{shell_id}/Communication",
            "submodelElements": [
                [com_method.to_dict() for com_method in self.communication_methods]
            ]
        }