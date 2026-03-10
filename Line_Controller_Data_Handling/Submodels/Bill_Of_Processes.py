from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ProcessStep:
    name: str
    process_id: str
    depends_on: Optional[str]
    parameters: Dict[str, str] = field(default_factory=dict)


@dataclass
class BillOfProcessesSubmodel:
    submodel_id: str
    steps: List[ProcessStep] = field(default_factory=list)


def parse_bill_of_processes_submodel(data: dict) -> BillOfProcessesSubmodel:
    submodel_id = data.get("id")
    result = BillOfProcessesSubmodel(submodel_id=submodel_id)

    elements = data.get("submodelElements", [])
    if not elements:
        return result
    #These 0's only work because we only have a list at that level in the json
    process_list = elements[0].get("value", [])

    for process_collection in process_list:
        step = parse_process_step(process_collection)
        result.steps.append(step)

    return result


def parse_process_step(collection: dict) -> ProcessStep:
    name = collection.get("idShort")
    process_id = None
    depends_on = None
    parameters = {}

    for element in collection.get("value", []):

        if element["idShort"] == "Process_Id":
            process_id = element.get("value")

        elif element["idShort"] == "Execution_Constraints":
            for c in element.get("value", []):
                if c["idShort"] == "Constraint_Id":
                    depends_on = c.get("value") or None

        elif element["idShort"] == "Parameters":
            for p in element.get("value", []):
                parameters[p["idShort"]] = p.get("value")

    return ProcessStep(
        name=name,
        process_id=process_id,
        depends_on=depends_on,
        parameters=parameters,
    )