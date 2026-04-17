from basyx.aas import model
import copy


# Functions for making submodels required or optional
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