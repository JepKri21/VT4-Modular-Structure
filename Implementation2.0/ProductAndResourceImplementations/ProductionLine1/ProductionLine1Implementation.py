#This should first create the shell and submodels from the yaml files and publish them to the server.

#It should also contain the PackML implementation, aka, this should be the main script for this resource
#Technically this isn't a resource, but it would still make sense that a production line has a PackML implementation
#This could also be the way to communicate line-relevant things, and potentially store orders or something
#This should NOT be the line-controller implementation. 
#Or, I mean, maybe it could be, where using START would just result in it running the control loop until every order is finished
#Orders could just be messages, OR they could be submodels published to the shell 
#However, I'm not sure how that would work, if you have to update the shell every time a new order is given? As I don't think you can just "add" a submodel


import asyncio
import time
import random
import sys
from pathlib import Path
import json
from datetime import datetime
from math import ceil
import basyx.aas.adapter.json

script_dir = Path(__file__).parent

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))


from ClassesAndBuilderMethods.BaSyx_AAS_Generator import yaml_to_instance, yaml_to_shell

BROKER = "localhost"
MQTT_PORT = 1883
BASE_TOPIC = "AAUSmartLab/ProductionLine1"

AAS_PORT = "8081"
SERVER_BASE = f"http://{BROKER}:{AAS_PORT}"  # your server base URL
SUBMODEL_ENDPOINT = f"{SERVER_BASE}/submodels"
SHELL_ENDPOINT = f"{SERVER_BASE}/shells"

#=============== UPLOADING SHELL ======================
shell = yaml_to_shell.load_shell_from_yaml(f"{script_dir}/Shell.yaml")
json_str = json.dumps(shell,cls=basyx.aas.adapter.json.AASToJsonEncoder,indent=2,ensure_ascii=False)
result = yaml_to_shell.upload_shell(json_str, SERVER_BASE)
print(result)  # "created" or "updated"

json_shell = json.loads(json_str)
CLIENT_ID = json_shell["idShort"]

#=============== UPLOADING SUBMODELS ======================



with open(f"{script_dir}/LineConfiguration.json") as f:
    json_str = json.load(f)

result = yaml_to_instance.upload_submodel(json_str, SERVER_BASE)
print(result)  # "created" or "updated"