import json
import requests

# -------------------------------
# Configuration
# -------------------------------
SERVER_BASE = "http://localhost:8081"  # your server base URL
SUBMODEL_ENDPOINT = f"{SERVER_BASE}/submodels"  # change if needed
SHELL_ENDPOINT = f"{SERVER_BASE}/shells"             # change if needed

# Paths to your existing JSON files
classification_submodel_json_file = r"/Users/lucasn.bonde/Desktop/Privat/Programming/Speciale/VT4-Modular-Structure/DrillStationAssetClassification.json"
operation_submodel_json_file = r"/Users/lucasn.bonde/Desktop/Privat/Programming/Speciale/VT4-Modular-Structure/DrillStationVisualization.json"
communication_submodel_json_file = r"/Users/lucasn.bonde/Desktop/Privat/Programming/Speciale/VT4-Modular-Structure/CommunicationEndpoint.json"
shell_json_file = r"/Users/lucasn.bonde/Desktop/Privat/Programming/Speciale/VT4-Modular-Structure/Shell_object_template.json"

# Load files
with open(operation_submodel_json_file, "r") as f:
    operation_submodel_data = json.load(f)

with open(communication_submodel_json_file, "r") as f:
    communication_submodel_data = json.load(f)

with open(classification_submodel_json_file, "r") as f:
    classification_submodel_data = json.load(f)

with open(shell_json_file, "r") as f:
    shell_data = json.load(f)

import base64

def image_to_base64(image_path):
    with open(image_path, "rb") as img_file:
        return base64.b64encode(img_file.read()).decode("utf-8")

# Path to your local image
image_path = "/Users/lucasn.bonde/Desktop/Privat/Programming/Speciale/VT4-Modular-Structure/CircImage.png"

# Convert image
image_base64 = image_to_base64(image_path)

# Inject into shell JSON
shell_data["assetInformation"]["defaultThumbnail"] = {
    "contentType": "image/png",
    "value": image_base64
}

# 1️⃣ Post submodels FIRST
for sm in [
    operation_submodel_data,
    communication_submodel_data,
    classification_submodel_data
]:
    response = requests.post(
        SUBMODEL_ENDPOINT,
        json=sm,
        headers={"Content-Type": "application/json"}
    )
    print("Submodel POST:", response.status_code)

# 2️⃣ Post shell LAST
response = requests.post(
    SHELL_ENDPOINT,
    json=shell_data,
    headers={"Content-Type": "application/json"}
)
print("Shell POST:", response.status_code)

