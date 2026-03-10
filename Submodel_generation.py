import json
import requests

# -------------------------------
# Configuration
# -------------------------------
SERVER_BASE = "http://localhost:5001"  # your server base URL
SUBMODEL_ENDPOINT = f"{SERVER_BASE}/submodels"  # change if needed
SHELL_ENDPOINT = f"{SERVER_BASE}/shells"             # change if needed

# Paths to your existing JSON files
operation_submodel_json_file = r"C:\Users\silas\Desktop\Manufacturing_Technology_4\Software\Python_Tests\Submodel_object_template.json"
communication_submodel_json_file = r"C:\Users\silas\Desktop\Manufacturing_Technology_4\Software\Python_Tests\CommunicationEndpoint.json"
shell_json_file = r"C:\Users\silas\Desktop\Manufacturing_Technology_4\Software\Python_Tests\Shell_object_template.json"


# -------------------------------
# Step 1: Load JSON files
# -------------------------------
with open(operation_submodel_json_file, "r", encoding="utf-8") as f:
    operation_submodel_data = json.load(f)

with open(communication_submodel_json_file, "r", encoding="utf-8") as f:
    communication_submodel_data = json.load(f)

with open(shell_json_file, "r", encoding="utf-8") as f:
    shell_data = json.load(f)


# -------------------------------
# Step 3: Post the Shell next
# -------------------------------
response = requests.post(
    SHELL_ENDPOINT,
    json=shell_data,  # requests will serialize automatically
    headers={"Content-Type": "application/json"}
)
print("Shell POST:", response.status_code, response.text)


# -------------------------------
# Step 2: Post the Submodel first
# -------------------------------
response = requests.post(
    SUBMODEL_ENDPOINT,
    json=operation_submodel_data,  # requests will serialize automatically
    headers={"Content-Type": "application/json"}
)
print("Operational Submodel POST:", response.status_code, response.text)


response = requests.post(
    SUBMODEL_ENDPOINT,
    json=communication_submodel_data,  # requests will serialize automatically
    headers={"Content-Type": "application/json"}
)
print("Communication Submodel POST:", response.status_code, response.text)

#{
#  "idShort": "DrillStationOperationalData",
#  "id": "https://aausmartlab.com/submodels/DrillStationOperationalData",
#  "submodelElements": [
#    {
#      "idShort": "Temperature",
#      "valueType": "xs:integer",
#      "value": "25",
#      "modelType": "Property"
#    },
#    {
#      "idShort": "Pressure",
#      "valueType": "xs:float",
#      "value": "101.3",
#      "modelType": "Property"
#    }
#  ],
#  "modelType": "Submodel"
#}
