from basyx.aas import model
import copy

identifier = 'https://aausmartlab.org/capability'
capability_submodel = model.Submodel(
    id_=identifier, 
    id_short="Capability",
    description="A capability represents the ability of an asset to perform a specific function or task. It defines what an asset can do, rather than how it does it. Capabilities are often used to describe the potential functionalities of an asset, and they can be associated with specific properties that provide more details about the capability.",
    kind = model.SubmodelKind.TEMPLATE)

# Submodel Property Semantic ID and External Global Reference
semantic_reference = model.ExternalReference(
    (model.Key(
        type_=model.KeyTypes.GLOBAL_REFERENCE,
        value='http://aausmartlab.org/Properties/Capability'
    ),)
)



drill_capability_template = model.Submodel(
    id_='https://aausmartlab.org/Capability/Drilling',
    id_short="DrillingCapability",
    description="Capability for drilling operations",
    kind = model.SubmodelKind.TEMPLATE,
    submodel_element={
        model.SubmodelElementCollection(
            id_short="DrilllingParameters",
            description={model.LangStringTextType("en", "Parameters for a drilling process")},
            kind=model.ModellingKind.TEMPLATE,
            value={
                model.Property(
                    id_short="BitDiameter_mm",
                    value_type=model.datatypes.Float,
                    description={model.LangStringTextType("en", "Drill bit diameter in mm")},
                    kind=model.ModellingKind.TEMPLATE,
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
                    kind=model.ModellingKind.TEMPLATE,
                    description={model.LangStringTextType("en", "Drill depth in milimeters")},
                ),
                model.Range(
                    id_short="SpindleSpeed_RPM",
                    value_type=model.datatypes.Float,
                    min=None,
                    max=None,
                    kind=model.ModellingKind.TEMPLATE,
                    description={model.LangStringTextType("en", "Spindle speed in RPM")},
                ),
                model.Range(
                    id_short="SpindleFeed_mm/s",
                    value_type=model.datatypes.Float,
                    min=None,
                    max=None,
                    kind=model.ModellingKind.TEMPLATE,
                    description={model.LangStringTextType("en", "Spindle feed in milimeters per second")},
                )
            }  
    )}
)

model.Qualifier(
    type_="allowedValues",
    value_type=model.datatypes.String,
    value="Red,Blue,Green,Yellow,Black,White",
    kind=model.QualifierKind.TEMPLATE_QUALIFIER,
)

 value='["Red", "Blue", "Green", "Yellow", "Black", "White"]',

qualifier={
        model.Qualifier(type_="allowedValue", value_type=model.datatypes.String, value="Red",    kind=model.QualifierKind.TEMPLATE_QUALIFIER),
        model.Qualifier(type_="allowedValue", value_type=model.datatypes.String, value="Blue",   kind=model.QualifierKind.TEMPLATE_QUALIFIER),
        model.Qualifier(type_="allowedValue", value_type=model.datatypes.String, value="Green",  kind=model.QualifierKind.TEMPLATE_QUALIFIER),
        model.Qualifier(type_="allowedValue", value_type=model.datatypes.String, value="Yellow", kind=model.QualifierKind.TEMPLATE_QUALIFIER),
    }


model.Property(
    id_short="Color",
    value_type=model.datatypes.String,
    kind=model.ModellingKind.TEMPLATE,
    qualifier={
        model.Qualifier(type_="allowedValue", value_type=model.datatypes.String, value="Red",    kind=model.QualifierKind.TEMPLATE_QUALIFIER),
        model.Qualifier(type_="allowedValue", value_type=model.datatypes.String, value="Blue",   kind=model.QualifierKind.TEMPLATE_QUALIFIER),
        model.Qualifier(type_="allowedValue", value_type=model.datatypes.String, value="Green",  kind=model.QualifierKind.TEMPLATE_QUALIFIER),



    }
)


drill_capability = copy.deepcopy(drill_capability_template)
drill_capability.id_ = submodel_id
drill_capability.kind = model.ModellingKind.INSTANCE
drill_capability.id_short = f"DrillingCapability_{drill_name}"


aas, submodel = create_drill_instance(
    asset_id   = "https://aausmartlab.org/assets/DrillMaster5000",
    aas_id     = "https://aausmartlab.org/aas/DrillMaster5000",
    submodel_id= "https://aausmartlab.org/submodels/DrillMaster5000",
    drill_name = "DrillMaster5000",
    values={
        "DrillBit": {
            "BitDiameter_mm":  (3.0, 20.0),   # Range
            "MaxBitLength_mm": (10.0, 150.0),  # Range
            "BitMaterial":     "Carbide",      # Property
        },
        "Spindle": {
            "SpindleSpeed_RPM":  (500.0, 8000.0),  # Range
            "RotationDirection": "CW",              # Property
        },
        "Feed": {
            "FeedRate_mmPerMin":  (10.0, 300.0),  # Range
            "DrillingDepth_mm":   (1.0, 100.0),   # Range
            "PeckDrillingEnabled": True,           # Property
        },
        "WorkpieceMaterial": {
            "MaterialType":    "Aluminium",  # Property
            "MaxHardness_HRC": (0.0, 45.0), # Range
        },
        "Coolant": {
            "CoolantAvailable": True,    # Property
            "CoolantType":      "Flood", # Property
        },
    }
)