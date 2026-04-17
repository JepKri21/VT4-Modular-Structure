from basyx.aas import model
from basyx.aas.adapter.json import AASToJsonEncoder
from basyx.aas.model import Key, KeyTypes, ModelReference
import copy
import json
import basyx.aas.adapter.xml
import basyx.aas.adapter.json
from Instance_Creating_Methods import required, optional
import requests


# The Submodel
drill_resource_skills = model.Submodel(
    id_='https://aausmartlab.org/SubmodelInstance/Skills',
    id_short="Skills",
    description=model.MultiLanguageTextType({"en": "List of skills for a resource"}), 
    kind = model.ModellingKind.INSTANCE,
    submodel_element={}
)


start_skill = model.SubmodelElementCollection(
    id_short="StartSkill",
    description=model.MultiLanguageTextType({"en": "Submodel for the start skill"}),
    value = [
        model.SubmodelElementCollection(
            id_short="CapabilityReferences",
            description=model.MultiLanguageTextType({"en": "List of capabilities that can be realized by the specified skill"}),
            value = [
                model.SubmodelElementCollection(
                id_short="Drilling",
                description=model.MultiLanguageTextType({"en": "List of parameters for the specified capability"}),
                value = [
                        model.ReferenceElement(
                            id_short="CapabilityReference",
                            value=model.ExternalReference(
                                key=(model.Key(type_=model.KeyTypes.GLOBAL_REFERENCE,value="https://aausmartlab.org/SubmodelInstance/Capability/Drilling/DrillingStation1"),)),
                            description=model.MultiLanguageTextType({"en": "Reference to capability"})
                        ),
                        model.SubmodelElementCollection(
                            id_short="Actors", 
                            description=model.MultiLanguageTextType({"en": "List of references to actors that can realize the specified capability."}),
                            value = [
                                model.Property(
                                    id_short="Actor1", 
                                    value_type=model.datatypes.String, 
                                    value="KUKAManipulator", 
                                    description=model.MultiLanguageTextType({"en": "Reference to the actor that is capable of realizing this specific capability"})
                                ),
                                model.Property(
                                    id_short="Actor2", 
                                    value_type=model.datatypes.String, 
                                    value="UR5", 
                                    description=model.MultiLanguageTextType({"en": "Reference to the actor that is capable of realizing this specific capability"})
                                )
                            ]
                        )
                    ]
                )
            ]
        )
    ]
)



stop_skill = model.SubmodelElementCollection(
    id_short="StopSkill",
    description=model.MultiLanguageTextType({"en": "Submodel for the stop skill"}),
    value = [
        model.SubmodelElementCollection(
            id_short="CapabilityReferences",
            description=model.MultiLanguageTextType({"en": "List of capabilities that can be realized by the specified skill"}),
            value = [
                model.SubmodelElementCollection(
                id_short="Stop",
                description=model.MultiLanguageTextType({"en": "List of parameters for the specified capability"}),
                value = [
                        model.ReferenceElement(
                            id_short="CapabilityReference",
                            value=model.ExternalReference(
                                key=(model.Key(type_=model.KeyTypes.GLOBAL_REFERENCE,value="https://aausmartlab.org/SubmodelInstance/Capability/Stop/DrillingStation1"),)),
                            description=model.MultiLanguageTextType({"en": "Reference to capability"})
                        ),
                        model.SubmodelElementCollection(
                            id_short="Actors", 
                            description=model.MultiLanguageTextType({"en": "List of references to actors that can realize the specified capability."}),
                            value = [
                                model.Property(
                                    id_short="Actor1", 
                                    value_type=model.datatypes.String, 
                                    value="KUKAManipulator", 
                                    description=model.MultiLanguageTextType({"en": "Reference to the actor that is capable of realizing this specific capability"})
                                ),
                                model.Property(
                                    id_short="Actor2", 
                                    value_type=model.datatypes.String, 
                                    value="UR5", 
                                    description=model.MultiLanguageTextType({"en": "Reference to the actor that is capable of realizing this specific capability"})
                                )
                            ]
                        )
                    ]
                )
            ]
        )
    ]
)


reset_skill = model.SubmodelElementCollection(
    id_short="ResetSkill",
    description=model.MultiLanguageTextType({"en": "Submodel for the reset skill"}),
    value = [
        model.SubmodelElementCollection(
            id_short="CapabilityReferences",
            description=model.MultiLanguageTextType({"en": "List of capabilities that can be realized by the specified skill"}),
            value = [
                model.SubmodelElementCollection(
                id_short="Reset",
                description=model.MultiLanguageTextType({"en": "List of parameters for the specified capability"}),
                value = [
                        model.ReferenceElement(
                            id_short="CapabilityReference",
                            value=model.ExternalReference(
                                key=(model.Key(type_=model.KeyTypes.GLOBAL_REFERENCE,value="https://aausmartlab.org/SubmodelInstance/Capability/Reset/DrillingStation1"),)),
                            description=model.MultiLanguageTextType({"en": "Reference to capability"})
                        ),
                        model.SubmodelElementCollection(
                            id_short="Actors", 
                            description=model.MultiLanguageTextType({"en": "List of references to actors that can realize the specified capability."}),
                            value = [
                                model.Property(
                                    id_short="Actor1", 
                                    value_type=model.datatypes.String, 
                                    value="KUKAManipulator", 
                                    description=model.MultiLanguageTextType({"en": "Reference to the actor that is capable of realizing this specific capability"})
                                ),
                                model.Property(
                                    id_short="Actor2", 
                                    value_type=model.datatypes.String, 
                                    value="UR5", 
                                    description=model.MultiLanguageTextType({"en": "Reference to the actor that is capable of realizing this specific capability"})
                                )
                            ]
                        )
                    ]
                )
            ]
        )
    ]
)


drill_resource_skills.submodel_element.add(start_skill)
drill_resource_skills.submodel_element.add(stop_skill)
drill_resource_skills.submodel_element.add(reset_skill)


submodel_json_string = json.dumps(drill_resource_skills, cls=basyx.aas.adapter.json.AASToJsonEncoder)

aas_dict = json.loads(submodel_json_string)


AAS_SERVER_URL = "http://localhost:8081"  # change to your server URL

response = requests.post(
    f"{AAS_SERVER_URL}/submodels",
    headers={"Content-Type": "application/json"},
    json=aas_dict
)

if response.status_code in (200, 201):
    print("Submodel uploaded successfully!")
else:
    print(f"Upload failed: {response.status_code} - {response.text}")