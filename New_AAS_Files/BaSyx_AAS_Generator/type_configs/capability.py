from basyx.aas import model
from basyx.aas.adapter.json import AASToJsonEncoder
import copy
import json
import basyx.aas.adapter.xml
import basyx.aas.adapter.json
    
def required(collection):
    collection.qualifier.add(
        model.Qualifier(
            type_="Cardinality",
            value_type=model.datatypes.String,
            value="1",
            kind=model.QualifierKind.TEMPLATE_QUALIFIER
        )
    )
    return collection


def optional(collection):
    collection.qualifier.add(
        model.Qualifier(
            type_="Cardinality",
            value_type=model.datatypes.String,
            value="0..1",
            kind=model.QualifierKind.TEMPLATE_QUALIFIER
        )
    )
    return collection


drill_capability_template = model.Submodel(
    id_='https://aausmartlab.org/Capability/Drilling',
    id_short="DrillingCapability",
    description=[model.MultiLanguageTextType({"en": "Capability for drilling operations"})], 
    kind = model.ModellingKind.TEMPLATE,
    submodel_element={}
)

DrillingParameters = required(model.SubmodelElementCollection(
    id_short="DrillingParameters",
    description=[model.MultiLanguageTextType({"en": "Drilling parameters defining the capabilities of the drilling operation"})],
    value={
        model.Property(
            id_short="BitDiameter_mm",
            value_type=model.datatypes.Float,
            description=[model.MultiLanguageTextType({"en": "Drill bit diameter in mm"})],
            qualifier={
                model.Qualifier(
                    type_="range_min",
                    value_type=model.datatypes.Float,
                    value=None,
                    kind=model.QualifierKind.TEMPLATE_QUALIFIER,
                ),
                model.Qualifier(
                    type_="range_max",
                    value_type=model.datatypes.Float,
                    value=None,
                    kind=model.QualifierKind.TEMPLATE_QUALIFIER,
                ),
            }
        ),
        model.Range(
            id_short="DrillDepth_mm",
            value_type=model.datatypes.Float,
            min=None,
            max=None,
            description=[model.MultiLanguageTextType({"en": "Drill depth in milimeters"})],
        ),
        model.Range(
            id_short="SpindleSpeed_RPM",
            value_type=model.datatypes.Float,
            min=None,
            max=None,
            description=[model.MultiLanguageTextType({"en": "Spindle speed in RPM"})],
        ),
        model.Range(
            id_short="SpindleFeed_mm_per_s",
            value_type=model.datatypes.Float,
            min=None,
            max=None,
            description=[model.MultiLanguageTextType({"en": "Spindle feed in milimeters per second"})],
        )
    }  
)
)


SupportedComponets = required(model.SubmodelElementList(
    id_short="SupportedComponents",
    description=[model.MultiLanguageTextType({"en": "List of components supported by this capability"})],
    type_value_list_element= model.Property,
    value_type_list_element=model.datatypes.String,
    value = [
        model.Property(
            id_short=None, value_type=model.datatypes.String, value="Bottom Cover", description=[model.MultiLanguageTextType({"en": "Bottom Housing Cover"})],
        ),
        model.Property(
            id_short=None, value_type=model.datatypes.String, value="Top Cover", description=[model.MultiLanguageTextType({"en": "Top Housing Cover"})],
        ),
    ]
)
)

AllowedMaterials = required(model.SubmodelElementList(
    id_short="AllowedMaterials",
    description=[model.MultiLanguageTextType({"en": "List of materials allowed for use with this capability"})],
    type_value_list_element= model.Property,
    value_type_list_element=model.datatypes.String,
    value = [
        model.Property(
            id_short=None, value_type=model.datatypes.String, value="PLA", description=[model.MultiLanguageTextType({"en": "Polylactic Acid"})],
        ),
        model.Property(
            id_short=None, value_type=model.datatypes.String, value="ABS", description=[model.MultiLanguageTextType({"en": "Acrylonitrile Butadiene Styrene"})],
        ),
    ]
)
)

drill_capability_template.submodel_element.add(DrillingParameters)
drill_capability_template.submodel_element.add(SupportedComponets)
drill_capability_template.submodel_element.add(AllowedMaterials)


aashell_json_string = json.dumps(drill_capability_template, cls=basyx.aas.adapter.json.AASToJsonEncoder)

print(aashell_json_string)

# Deep copy så template ikke ændres
drill_instance = copy.deepcopy(drill_capability_template)

# Skift til instans
drill_instance.id_ = 'https://aausmartlab.org/Capability/Drilling/Instance_001'
drill_instance.kind = model.ModellingKind.INSTANCE

def get_element(namespace_set, id_short):
    return next(e for e in namespace_set if e.id_short == id_short)

# Tilgå DrillingParameters collection
drilling_params = get_element(drill_instance.submodel_element, "DrillingParameters")

# Tilgå Property inde i collection
bit_diameter = get_element(drilling_params.value, "BitDiameter_mm")
bit_diameter.value = 6.0



