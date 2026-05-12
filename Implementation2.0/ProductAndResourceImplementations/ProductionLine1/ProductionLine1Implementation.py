import asyncio
import sys
from pathlib import Path
import json
import basyx.aas.adapter.json

script_dir = Path(__file__).parent

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from ClassesAndBuilderMethods.BaSyx_AAS_Generator import yaml_to_instance, yaml_to_shell

BROKER = "localhost"
MQTT_PORT = 1883
BASE_TOPIC = "AAUSmartLab/ProductionLine1"

AAS_PORT = "8081"
SERVER_BASE = f"http://{BROKER}:{AAS_PORT}"
SUBMODEL_ENDPOINT = f"{SERVER_BASE}/submodels"
SHELL_ENDPOINT = f"{SERVER_BASE}/shells"

#=============== UPLOADING SHELL ======================
shell = yaml_to_shell.load_shell_from_yaml(f"{script_dir}/Shell.yaml")
json_str = json.dumps(shell, cls=basyx.aas.adapter.json.AASToJsonEncoder, indent=2, ensure_ascii=False)
result = yaml_to_shell.upload_shell(json_str, SERVER_BASE)
print(result)

json_shell = json.loads(json_str)
CLIENT_ID = json_shell["idShort"]

#=============== UPLOADING SUBMODELS ======================

with open(f"{script_dir}/LineConfiguration.json") as f:
    data = json.load(f)
json_str = json.dumps(data, indent=2, ensure_ascii=False)
result = yaml_to_instance.upload_submodel(json_str, SERVER_BASE)
print(result)

#=============== SERVICE SUBMODELS ======================
# Add YAML-based service submodels here using the pattern below.
# Each file should be a YAML instance definition compatible with yaml_to_instance.
#
# Example:
#   builder = yaml_to_instance.load_instance_from_yaml(f"{script_dir}/Communication.yaml")
#   json_str = json.dumps(builder.get(), cls=basyx.aas.adapter.json.AASToJsonEncoder, indent=2, ensure_ascii=False)
#   result = yaml_to_instance.upload_submodel(json_str, SERVER_BASE)
#   print(result)
#
# Remember to also add a submodel reference entry in Shell.yaml for each new submodel.

#=============== MAIN ======================

async def main():
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())