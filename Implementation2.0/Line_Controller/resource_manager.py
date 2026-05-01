import json
from datetime import datetime
from pathlib import Path
import enum

class ResourceManager:
    """
    Resource Manager Should Read all currently available resouces at a defined producton line, from the AAS Server with their Capabilities and Parameters? 
    """

    def __init__(self, aas_capabilities):
        self.capabilities = aas_capabilities

    def find_by_capability(self, capability_id):
        for cap in self.capabilities:
            if cap["id"] == capability_id:
                return cap["ResourceReference"]["keys"][0]["value"]

        return None
    
