
from dataclasses import dataclass, field
from typing import List, Union, Optional

import sys
from pathlib import Path

# Add Station_Simulators to import path
#sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from .General_Dataclasses import *


@dataclass
class CommunicationMethod(AutoCollection):
    idShort: str
    extra_elements: List[Union[Property, Range, SubmodelElementCollection]] = field(default_factory=list)

@dataclass
class CommunicationMethods(AutoCollection):
    idShort = "Communication_Methods"
    communication_methods: List[CommunicationMethod]


@dataclass
class CommunicationSubmodelData(AutoSubmodel):
    idShort: str = "Communication"          # enforced submodel name
    submodel_data: AutoCollection = None     # the collection for the submodel
    shell_id: Optional[str] = None          # can be set later
