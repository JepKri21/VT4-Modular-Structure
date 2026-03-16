from typing import List
import requests
import urllib.parse
from collections import defaultdict


class AASNode:

    def __init__(self, data, parent=None):
        self.data = data
        self.parent = parent
        self.id_short = data.get("idShort")
        self.children = {}
        self._parse_children()

    def _parse_children(self):
        # Submodel elements
        if "submodelElements" in self.data:
            for elem in self.data["submodelElements"]:
                node = AASNode(elem, parent=self)
                self.children[node.id_short] = node
        # Collections
        elif isinstance(self.data.get("value"), list):
            for elem in self.data["value"]:
                if isinstance(elem, dict) and "idShort" in elem:
                    node = AASNode(elem)
                    self.children[node.id_short] = node
    # -------------------------
    # Navigation
    # -------------------------
    def __getitem__(self, key):
        return self.children[key]

    def __getattr__(self, name):
        if name in self.children:
            return self.children[name]
        raise AttributeError(name)

    def keys(self):
        return self.children.keys()

    def __call__(self):
        if self.range is not None:
            return self.range
        if self.value is not None:
            return self.value
        return self.children
        
    def path(self):
        node = self
        p = []
        while node:
            if node.id_short:
                p.append(node.id_short)
            node = node.parent
    
        return list(reversed(p))
    # -------------------------
    # Value helpers
    # -------------------------
    @property
    def value(self):
        v = self.data.get("value")
        if not isinstance(v, list):
            return v
        return None

    @property
    def range(self):
        if "min" in self.data and "max" in self.data:
            return {"min": self.data["min"], "max": self.data["max"]}
        return None

    @property
    def type(self):
        return self.data.get("modelType", {}).get("name")

    def __repr__(self):
        return f"AASNode({self.id_short}, children={list(self.children)})"



class AAS:
    def __init__(self, shell_json, submodels_json: List):
        self.shell_json = shell_json
        self.submodels_json = submodels_json
        self.submodels = {}
        self._index = defaultdict(list)
        self._parse()

        self.shell_id = shell_json["id"]
        self.shell_idShort = shell_json["idShort"]

    def _parse(self):
        for submodel in self.submodels_json:
            node = AASNode(submodel)
            self.submodels[node.id_short] = node
            self._index_tree(node)

    def _index_tree(self, node):
        if node.id_short:
            self._index[node.id_short].append(node)
        for child in node.children.values():
            self._index_tree(child)

    def __getitem__(self, key):
        if key not in self.submodels:
            raise KeyError(
                f"Submodel '{key}' not found. Available: {list(self.submodels.keys())}"
            )
        return self.submodels[key]

    def __getattr__(self, name):
        if name in self.submodels:
            return self.submodels[name]
        raise AttributeError(name)

    def find(self, id_short):
        return self._index.get(id_short, [])
        
    def keys(self):
        return self.submodels.keys()

    def __repr__(self):
        return f"AAS(submodels={list(self.submodels.keys())})"
        

    
class AASShellReader:

    def __init__(self, aas_server_ip: str):
        self.shells = None
        self.submodels = None
        self.AAS_SERVER = aas_server_ip

    def get_shells(self):
        response = requests.get(f"{self.AAS_SERVER}/shells")
        if response.ok:
            self.shells = response.json().get("result", [])
            return self.shells

        print("Shells error:", response)
        return []
    
    def get_submodels(self):
        response = requests.get(f"{self.AAS_SERVER}/submodels")

        if response.ok:
            self.submodels = response.json().get("result", [])
            return self.submodels

        print("Submodels error:", response)
        return []

    def return_correlated_assets(self):
        asset_list = []
        
        self.get_shells()
        self.get_submodels()
        
        for shell in self.shells:
            shell_list = []
            shell_id = shell["id"]
            shell_list.append(shell)
            
            is_resource = "/Resource/" in shell_id
            is_product = "/Product/" in shell_id
        
            if not (is_resource or is_product):
                continue
            
            for submodel in self.submodels:
                sm_id = submodel["id"]
                is_submodel_in_shell = shell_id in sm_id
                if is_submodel_in_shell:
                    shell_list.append(submodel)
                else:
                    continue

            asset_list.append(shell_list)

        resource_assets = {}
        product_assets = {}

        for asset in range(len(asset_list)):
            AAS_asset = AAS(asset_list[asset][0], [submodel for submodel in asset_list[asset][1:]])

            if "/Resource/" in AAS_asset.shell_id:
                resource_assets[AAS_asset.shell_id] = AAS_asset
            elif "/Product/" in AAS_asset.shell_id:
                product_assets[AAS_asset.shell_id] = AAS_asset


        return asset_list, resource_assets, product_assets



if __name__ == "__main__":
    AAS_SERVER = "http://localhost:8081"
    Reader = AASShellReader(AAS_SERVER)

    All_Assets, Resources, Products = Reader.return_correlated_assets()

    # Products[""]

    print(f"===============================================================================================================\n")
    print(Resources)
    print(f"===============================================================================================================\n")
    print(Products)
    print(f"===============================================================================================================\n")

    #These has to be the actual ids, can no longer just be the idShort (as many products have the same idShort)
    print(Resources["Drill_Station_Asset"].Communication.UNS_Communication.Broker_Address())
    print(Resources["Drill_Station_Asset"].Skills.Agents.KUKA_Manipulator.Drilling.Parameters.DrillDepth.range)
