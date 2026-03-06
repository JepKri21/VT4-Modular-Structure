from dataclasses import dataclass, asdict
from typing import List, Optional

@dataclass
class SubmodelReference:
    submodel_name: str

    def convert_to_dict(self, shell_id):
        return  { 
                  "type": "ModelReference",
                  "keys": [
                    {
                      "type": "Submodel",
                      "value": f"{shell_id}/{self.submodel_name}"
                    }
                  ]
                }


@dataclass
class ResourceShellData:
    references: List[SubmodelReference]
    id: str
    idShort: str

    def convert_to_dict(self):
        return {
            "idShort" : self.idShort,
            "id" : self.id,
            "modelType": "AssetAdministrationShell",
            "assetInformation": {
                "assetKind": "Instance",
                "globalAssetId": self.id
                },
            "submodels": [reference.convert_to_dict(self.id) for reference in self.references]
        }