from basyx.aas import model
from basyx.aas.adapter.json import AASToJsonEncoder
import copy
import json
import basyx.aas.adapter.xml
import basyx.aas.adapter.json
from Instance_Creating_Methods import required, optional
import requests



# The Submodel
drill_capability_instance = model.Submodel(
    id_='https://aausmartlab.org/SubmodelInstance/Capability/Drilling/DrillingStation1',
    id_short="DrillingCapability",
    description=model.MultiLanguageTextType({"en": "..."}), 
    kind = model.ModellingKind.INSTANCE,
    submodel_element={}
)



DrillingParameters = model.SubmodelElementCollection(
    id_short="DrillingParameters",
    description=model.MultiLanguageTextType({"en": "Drilling parameters defining the capabilities of the drilling operation"}),
    value=[
        model.Property(
            id_short="BitDiameter_mm",
            value_type=model.datatypes.Float,
            description=model.MultiLanguageTextType({"en": "Drill bit diameter in mm"}),
            value = 5.0,
            qualifier={
                model.Qualifier(
                    type_="range_min",
                    value_type=model.datatypes.Float,
                    value=1.0,
                    kind=model.QualifierKind.VALUE_QUALIFIER,
                ),
                model.Qualifier(
                    type_="range_max",
                    value_type=model.datatypes.Float,
                    value=20.0,
                    kind=model.QualifierKind.VALUE_QUALIFIER,
                ),
            }
        ),
        model.Range(
            id_short="DrillDepth_mm",
            value_type=model.datatypes.Float,
            min=0.0,
            max=200.0,
            description=model.MultiLanguageTextType({"en": "..."}),
        ),
        model.Range(
            id_short="SpindleSpeed_RPM",
            value_type=model.datatypes.Float,
            min=0.0,
            max=1200.0,
            description=model.MultiLanguageTextType({"en": "..."}),
        ),
        model.Range(
            id_short="SpindleFeed_mm_per_s",
            value_type=model.datatypes.Float,
            min=0.0,
            max=50.0,
            description=model.MultiLanguageTextType({"en": "..."}),
        ),
        model.Range(
            id_short="HolePlacement_x_mm",
            value_type=model.datatypes.Float,
            min=-50.0,
            max=50.0,
            description=model.MultiLanguageTextType({"en": "Possible range of X-coordiante position of hole to be drilled out relative to product placement point"}),
        ),
        model.Range(
            id_short="HolePlacement_y_mm",
            value_type=model.datatypes.Float,
            min=-50.0,
            max=50.0,
            description=model.MultiLanguageTextType({"en": "Possible range of Y-coordiante position of hole to be drilled out relative to product placement point"}),
        )
    ]
)



SupportedComponets = model.SubmodelElementList(
    id_short="SupportedComponents",
    description=model.MultiLanguageTextType({"en": "List of components supported by this capability"}),
    type_value_list_element= model.Property,
    value_type_list_element=model.datatypes.String,
    value = [
        model.Property(
            id_short=None, 
            value_type=model.datatypes.String, 
            value="Bottom Cover", 
            description=model.MultiLanguageTextType({"en": "Bottom Housing Cover"}),
        ),
        model.Property(
            id_short=None, 
            value_type=model.datatypes.String, 
            value="Top Cover", description=model.MultiLanguageTextType({"en": "Top Housing Cover"}),
        )
    ]
)


AllowedMaterials = model.SubmodelElementList(
    id_short="AllowedMaterials",
    description=model.MultiLanguageTextType({"en": "List of materials allowed for use with this capability"}),
    type_value_list_element= model.Property,
    value_type_list_element=model.datatypes.String,
    value = [
        model.Property(
            id_short=None, 
            value_type=model.datatypes.String, 
            value="PLA", 
            description=model.MultiLanguageTextType({"en": "Polylactic Acid"}),
        ),
        model.Property(
            id_short=None, 
            value_type=model.datatypes.String, 
            value="ABS", 
            description=model.MultiLanguageTextType({"en": "Acrylonitrile Butadiene Styrene"}),
        )
    ]
)



drill_capability_instance.submodel_element.add(DrillingParameters)
drill_capability_instance.submodel_element.add(SupportedComponets)
drill_capability_instance.submodel_element.add(AllowedMaterials)



submodel_json_string = json.dumps(drill_capability_instance, cls=basyx.aas.adapter.json.AASToJsonEncoder)
print(drill_capability_instance)
aas_dict = json.loads(submodel_json_string)
print(aas_dict)

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