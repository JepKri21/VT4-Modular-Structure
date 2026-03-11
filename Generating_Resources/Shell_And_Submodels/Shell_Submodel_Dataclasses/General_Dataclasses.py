from dataclasses import dataclass, fields, is_dataclass
from typing import List, Union, Optional

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
    


#This one class will can be inherited to other data classes such that they automatically have the convert_to_collection function
class AutoCollection:

    extra_elements: List[Union[Property, Range, SubmodelElementCollection]] = None

    def convert_to_collection(self) -> SubmodelElementCollection:
        elements = []

        for f in fields(self):
            name = f.name
            value = getattr(self, name)

            if name in ["idShort", "extra_elements"]:
                continue

            # Nested AutoCollection
            if isinstance(value, AutoCollection):
                elements.append(value.convert_to_collection())

            # List of AutoCollections
            elif isinstance(value, list):
                sub_elements = []
            
                for v in value:
                    if isinstance(v, AutoCollection):
                        sub_elements.append(v.convert_to_collection())
            
                if sub_elements:
                    elements.append(
                        SubmodelElementCollection(
                            idShort=name,
                            value=sub_elements
                        )
                    )

            # int -> Property
            elif isinstance(value, int):
                elements.append(Property(idShort=name, valueType="xs:integer", value=str(value)))

            # str -> Property
            elif isinstance(value, str):
                elements.append(Property(idShort=name, valueType="xs:string", value=value))

        # Append any extra elements (Property, Range, Collection)
        if getattr(self, "extra_elements", None):
            elements.extend(self.extra_elements)

        return SubmodelElementCollection(
            idShort=self.idShort,
            value=elements
        )
    

#Allows a class to inherit the covert_to_dict function
class AutoSubmodel:
    """
    Base class for automatically converting a root AutoCollection into a full submodel dict.
    """

    idShort: str  # fixed submodel name
    submodel_data: List[AutoCollection]
    shell_id: Optional[str] = None

    def convert_to_dict(self):
        if self.shell_id is None:
            raise ValueError("shell_id must be set before generating the submodel dict")
        
        elements = []

        for element in self.submodel_data:
            elements.append(element.convert_to_collection().to_dict())

        return {
            "idShort": self.idShort,
            "id": f"{self.shell_id}/{self.idShort}",
            "submodelElements": elements
        }