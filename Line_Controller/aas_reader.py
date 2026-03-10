import requests

AAS_SERVER = "http://localhost:8081"


def get_shells():
    url = f"{AAS_SERVER}/shells"
    return requests.get(url).json()["result"]

def get_submodels(asset_id):
    """
    Henter submodels for et givent asset_id
    """
    # Husk at base64 encode hvis nødvendigt
    import base64
    encoded_id = base64.b64encode(asset_id.encode()).decode()
    url = f"{AAS_SERVER}/submodels?idShort={encoded_id}"
    response = requests.get(url)
    response.raise_for_status()  # sikrer at HTTP errors kastes
    return response.json().get("result", [])

def extract_skills(parsed_submodels):
    skills = {}
    skills_sm = parsed_submodels.get("Skills")
    if not skills_sm:
        return skills

    def parse_operations(level):
        results = {}
        for k, v in level.items():
            if isinstance(v, dict):
                # dybere niveau
                sub = parse_operations(v)
                if sub:
                    results[k] = sub
            else:
                results[k] = v
        return results

    skills = parse_operations(skills_sm)
    return skills

def parse_submodel_elements(elements):
    """
    Rekursivt parser alle submodelElements og nested collections/lists
    til et dictionary.
    """
    result = {}
    for el in elements:
        id_short = el.get("idShort")
        value = el.get("value")
        if isinstance(value, list):
            # rekursivt parse nested elements
            result[id_short] = parse_submodel_elements(value)
        else:
            result[id_short] = value
    return result