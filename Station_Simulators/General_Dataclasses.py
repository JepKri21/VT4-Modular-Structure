from dataclasses import dataclass
from typing import List, Union

@dataclass
class Property:
    idShort: str
    valueType: str
    value: str

    def to_dict(self):
        return {
            "modelType": "Property",
            "idShort": self.idShort,
            "valueType": self.valueType,
            "value": self.value
        }


@dataclass
class Range:
    idShort: str
    valueType: str
    min: str
    max: str

    def to_dict(self):
        return {
            "modelType": "Range",
            "idShort": self.idShort,
            "valueType": self.valueType,
            "min": self.min,
            "max": self.max
        }


@dataclass
class SubmodelElementCollection:
    idShort: str
    value: List[Union['Property', 'Range', 'SubmodelElementCollection', 'SubmodelElementList']]

    def to_dict(self):
        return {
            "modelType": "SubmodelElementCollection",
            "idShort": self.idShort,
            "value": [v.to_dict() for v in self.value]
        }
    

@dataclass
class SubmodelElementList:
    idShort: str
    typeValueListElement: str          
    value: List[Union['Property', 'Range', 'SubmodelElementCollection', 'SubmodelElementList']]
    orderRelevant: bool = True          # optional  
    valueTypeListElement: str = None    # optional

    def to_dict(self):
        return {
            "modelType": "SubmodelElementList",
            "idShort": self.idShort,
            "typeValueListElement": self.typeValueListElement,
            "valueTypeListElement": self.valueTypeListElement,
            "orderRelevant": self.orderRelevant,
            "value": [v.to_dict() for v in self.value]
        }