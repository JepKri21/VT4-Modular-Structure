import json
import paho.mqtt.client as mqtt
import sys
from pathlib import Path
import time
import asyncio
import threading
from datetime import datetime, timedelta

sys.path.append(str(Path(__file__).resolve().parent.parent))

from ClassesAndBuilderMethods.InformationModels import MessageStructure as MS
from resource_manager import ResourceManager as RM


class MQTTClientController:

    def __init__(self,broker,port,client_id,base_topic,resource_manager: RM):

        self.broker = broker
        self.port = port
        self.client_id = client_id
        self.base_topic = base_topic
        self.RM = resource_manager

        self.last_seen = {}
        """
        self.last_seen = {
            resource_idShort: datetime.now(),
            resource_idShort: datetime.now()
            }
        """


        #This one can just be called to get the shell ids, but we do need a function that updates to ACTIVE if we get a state update
        """
        self.RM.resource_shell_ids = {
            resource_shell_id: MS.ResourceReachability.ACTIVE,
            resource_shell_id: MS.ResourceReachability.INACTIVE,
            resource_shell_id: MS.ResourceReachability.UNREACHABLE
            }
        """

        #This one can just be called to get the specific suffixes used for that resource
        """
        self.RM.get_resource_MQTT_suffixes(resource_shell_id) returns: {
            "CommandSuffix": "string_value",
            "StateSuffix": "string_value",
            "InfoRequestSuffix": "string_value",
            "AlarmSuffix": "string_value",
            "JobResultSuffix": "string_value",
            "InventoryLevelSuffix": "string_value",
            "ResourceAcknowledgementSuffix": "string_value",
            "ControllerAcknowledgementSuffix": "string_value"
            }
        """
        
        #self.topic_to_shell_id and self.shell_id_to_topic can both be made from self.RM.resource_shell_ids, just by taking the last string split by "/"
        self.topic_to_shell_id = {}
        """
        self.topic_to_shell_id = {
            resource_idShort: resource_shell_id,
            #example ("Drilling_12345678": "https://aausmartlab.org/Shells/Resources/Drilling_12345678"),
            resource_idShort: resource_shell_id
            }
        """

        self.shell_id_to_topic = {}
        """
        self.topic_to_shell_id = {
            resource_shell_id: resource_idShort,
            #example ("https://aausmartlab.org/Shells/Resources/Drilling_12345678": "Drilling_12345678"),
            resource_shell_id: resource_idShort
            }
        """

        #
        self.handlers = {}
        """
        self.handlers = {
            message_type: handler_method,
            message_type: handler_method
            }
        """

        #This will be called to make a map of what topic to use for a specific message type
        #This will be used in publish_message, which checks the message type and uses the corresponding suffix to send the message
        self.topic_maps = {}
        """
        suffixes = self.RM.get_resource_MQTT_suffixes(resource_shell_id)
        self.topic_maps = {
            resource_shell_id: {MS.CommandMessage: suffixes.get("CommandSuffix"),
                                MS.StateMessage: suffixes.get("StateSuffix"),
                                MS.RequestMessage: suffixes.get("InfoRequestSuffix"),
                                MS.AlarmsMessage: suffixes.get("AlarmSuffix"),
                                MS.AcknowledgementMessage: {"ResourceAcknowledgementSuffix": suffixes.get("ResourceAcknowledgementSuffix"), "ControllerAcknowledgementSuffix": suffixes.get("ControllerAcknowledgementSuffix") },
                                MS.JobResultMessage: suffixes.get("JobResultSuffix"),
                                MS.InventoryLevelMessage: suffixes.get("InventoryLevelSuffix")},
            resource_shell_id: {MS.CommandMessage: suffixes.get("CommandSuffix"),
                                MS.StateMessage: suffixes.get("StateSuffix"),
                                MS.RequestMessage: suffixes.get("InfoRequestSuffix"),
                                MS.AlarmsMessage: suffixes.get("AlarmSuffix"),
                                MS.AcknowledgementMessage: {"ResourceAcknowledgementSuffix": suffixes.get("ResourceAcknowledgementSuffix"), "ControllerAcknowledgementSuffix": suffixes.get("ControllerAcknowledgementSuffix") },
                                MS.JobResultMessage: suffixes.get("JobResultSuffix"),
                                MS.InventoryLevelMessage: suffixes.get("InventoryLevelSuffix")}
        }
        """


        #This will be called when receiving a message, you get the message on a topic and you can easily find the suffix
        #With this, you find out what type of message should have been sent to that topic.
        #From there you can use self.handlers to figure out which handler to use and give it the message
        self.reverse_topic_maps = {}
        """
        #NOTE that CommandSuffix will be the specific CommandSuffix for a unique resource, not just "CommandSuffix"
        self.reverse_topic_maps = {
            resource_shell_id: {CommandSuffix: MS.CommandMessage,
                                StateSuffix: MS.StateMessage,
                                InfoRequestSuffix: MS.RequestMessage,
                                AlarmSuffix: MS.AlarmsMessage,
                                ResourceAcknowledgementSuffix: MS.AcknowledgementMessage,
                                ControllerAcknowledgementSuffix: MS.AcknowledgementMessage,
                                JobResultSuffix: MS.JobResultMessage,
                                InventoryLevelSuffix: MS.InventoryLevelMessage},
            resource_shell_id: {CommandSuffix: MS.CommandMessage,
                                StateSuffix: MS.StateMessage,
                                InfoRequestSuffix: MS.RequestMessage,
                                AlarmSuffix: MS.AlarmsMessage,
                                ResourceAcknowledgementSuffix: MS.AcknowledgementMessage,
                                ControllerAcknowledgementSuffix: MS.AcknowledgementMessage,
                                JobResultSuffix: MS.JobResultMessage,
                                InventoryLevelSuffix: MS.InventoryLevelMessage}
        }
        """

        self.shared_handler_variable = {}
        """
        This variable is where the handlers can write their data and make it accesible to the controller
        It is just an empty dict, but the controller will define what the handlers write to
        So a handler for the state messages will write to a key called "state" or whatever they want
        It could look something like this:
        self.shared_handler_variable = {
            "state": {resource_shell_id: {actor_name : "PackMLState.Idle"}},
            "inventory": {resource_shell_id: InventoryLevelMessage,
            "inventory": {resource_shell_id: {inventory_name: {"InventorySize": int, "SupportedComponents": list[str], AccesibleActors: list[str], Storage: }}},
            "job_result": {resource_shell_id: {actor_name : JobResultMessage}}
            }
        """

        self.client = mqtt.Client(
            client_id=self.client_id,
            callback_api_version=mqtt.CallbackAPIVersion.VERSION1
        )

        self.watchdog_running = True
        self.watchdog_thread = threading.Thread(
            target=self._watch_last_seen_loop,
            daemon=True
        )
        self.watchdog_thread.start()

    #=================
    #Helper functions
    #=================

    def parse_topic(self, topic: str):

        parts = topic.split("/")

        resource_suffix = None
        suffix = None

        # Find resource ID dynamically
        for part in parts:
            if part in self.topic_to_shell_id:
                resource_suffix = part
                break

        if resource_suffix is None:
            raise ValueError(f"[PARSE_TOPIC ERROR] Unknown resource in topic: {topic}")

        # Find suffix dynamically
        reverse_map = self.reverse_topic_maps.get(resource_suffix, {})

        for part in parts:
            if part in reverse_map:
                suffix = part
                break

        if suffix is None:
            raise ValueError(f"[PARSE_TOPIC ERROR] Unknown suffix in topic: {topic}")

        # Optional actor ID:
        actor_id = None

        suffix_index = parts.index(suffix)

        if suffix_index + 1 < len(parts):
            actor_id = parts[suffix_index + 1]

        return {
            "resource_suffix": resource_suffix,
            "topic_suffix": suffix,
            "actor_id": actor_id,
            "full_topic": topic
        }

    def register_handler(self, message_type, handler):
        self.handlers[message_type] = handler

    def classify_reachability(self, state_message):
    
        inactive_states = {
            MS.PackMLState.ABORTED,
            MS.PackMLState.ABORTING,
            MS.PackMLState.CLEARING,
            MS.PackMLState.STOPPING,
            MS.PackMLState.STOPPED
        }
    
        if state_message.state in inactive_states:
            return MS.ResourceReachability.INACTIVE
    
        return MS.ResourceReachability.ACTIVE

    def _request_resource_data(self,resource_suffix: str,message_type):

        try:
            topic_map = self.topic_maps.get(resource_suffix)
            if topic_map is None:
                print(f"[REQUEST_MESSAGE ERROR] No topic map for {resource_suffix}")
                return

            # =====================================
            # Determine requested topic suffix
            # =====================================
            requested_suffix = topic_map.get(message_type)

            if requested_suffix is None:
                print(f"[REQUEST_MESSAGE ERROR] {resource_suffix} does not support "f"{message_type}")
                return

            # =====================================
            # Determine request topic suffix
            # =====================================
            request_suffix = topic_map.get(MS.RequestMessage)

            if request_suffix is None:
                print(f"[REQUEST_MESSAGE ERROR] {resource_suffix} has no RequestMessage topic")
                return

            # =====================================
            # Construct requested topic
            # =====================================
            requested_topic = (f"{self.base_topic}/"f"{resource_suffix}/"f"{requested_suffix}")

            # =====================================
            # Build request message
            # =====================================
            resource_shell_id = self.topic_to_shell_id[resource_suffix]
            request_message = MS.RequestMessage(
                timestamp=datetime.now(),
                requested_topic_update=requested_topic,
                resource_id=resource_shell_id
            )

            # =====================================
            # Publish request
            # =====================================
            self.publish_message(resource_shell_id,request_message)

            print(f"[REQUEST_MESSAGE] Requested {message_type.__name__} "f"from {resource_suffix}")

        except Exception as e:
            print(f"[REQUEST_MESSAGE ERROR] Request failed: {e}")

    #=====================
    #Controller functions
    #=====================

    def update_information(self):
        #This method should update self.reverse_topic_maps, self.topic_maps, self.shell_id_to_topic and self.topic_to_shell_id
        self.RM.update_resource_availablility() #This one should probably not overwrite the status if the resource already exists in the list
        
        
        for resource_shell_id in self.RM.resource_shell_ids:
            resource_suffix = resource_shell_id.rstrip("/").split("/")[-1]
            #===============
            #Updating self.shell_id_to_topic
            #===============
            self.shell_id_to_topic[resource_shell_id] = resource_suffix

            #===============
            #Updating self.topic_to_shell_id
            #===============
            self.topic_to_shell_id[resource_suffix] = resource_shell_id

            #===============
            #Updating self.topic_maps
            #===============
            suffixes = self.RM.get_resource_MQTT_suffixes(resource_shell_id)
            self.topic_maps[resource_suffix] = {
                MS.CommandMessage: suffixes.get("CommandSuffix"),
                MS.StateMessage: suffixes.get("StateSuffix"),
                MS.RequestMessage: suffixes.get("InfoRequestSuffix"),
                MS.AlarmsMessage: suffixes.get("AlarmSuffix"),
                MS.AcknowledgementMessage: {"ResourceAcknowledgementSuffix": suffixes.get("ResourceAcknowledgementSuffix"), "ControllerAcknowledgementSuffix": suffixes.get("ControllerAcknowledgementSuffix") },
                MS.JobResultMessage: suffixes.get("JobResultSuffix"),
                MS.InventoryLevelMessage: suffixes.get("InventoryLevelSuffix")
                }
            
            # ===============================
            # Updating self.reverse_topic_maps
            # ===============================

            reverse = {}

            for message_type, suffix in self.topic_maps[resource_suffix].items():
            
                if suffix is None:
                    continue
                
                # Acknowledgement suffixes are stored as dicts
                if isinstance(suffix, dict):
                
                    for ack_suffix in suffix.values():
                    
                        if ack_suffix is not None:
                            reverse[ack_suffix] = message_type

                else:
                    reverse[suffix] = message_type

            self.reverse_topic_maps[resource_suffix] = reverse

    def request_data(self,message_type,resource_shell_id: str | None = None):
        resource_suffix = None
        # =====================================
        # CASE 1:
        # Single specific resource
        # =====================================
        if resource_shell_id is not None:
            resource_suffix = self.shell_id_to_topic[resource_shell_id]
            if resource_suffix is not None:
                self._request_resource_data(resource_suffix,message_type)
                return

        
        # =====================================
        # CASE 2:
        # Request from all compatible resources
        # =====================================
        else:
            for resource_suffix, topic_map in self.topic_maps.items():

                # Skip resources without this topic
                if message_type not in topic_map:
                    continue

                topic_suffix = topic_map.get(message_type)

                if topic_suffix is None:
                    continue

                self._request_resource_data(resource_suffix,message_type)

    def publish_message(self,resource_shell_id: str,message):
        
        try:
            resource_suffix = self.shell_id_to_topic[resource_shell_id]

            # ==========================
            # Get topic mapping
            # ==========================
            topic_map = self.topic_maps.get(resource_suffix)

            if topic_map is None:
                raise ValueError(
                    f"[PUBLISH_MESSAGE ERROR] No topic map found for resource: {resource_suffix}"
                )

            # ==========================
            # Determine suffix
            # ==========================
            topic_suffix = topic_map.get(type(message))

            if topic_suffix is None:
                raise ValueError(
                    f"[PUBLISH_MESSAGE ERROR] No topic suffix for message type "
                    f"{type(message)} on resource {resource_suffix}"
                )

            # ==========================
            # Special handling for ACKs
            # ==========================
            if isinstance(topic_suffix, dict):

                topic_suffix = topic_suffix.get(
                    "ControllerAcknowledgementSuffix"
                )

                if topic_suffix is None:
                    raise ValueError(
                        f"[PUBLISH_MESSAGE ERROR] No ControllerAcknowledgementSuffix "
                        f"defined for resource {resource_suffix}"
                    )

            # ==========================
            # Construct topic
            # ==========================

            topic = (
                f"{self.base_topic}/"
                f"{resource_suffix}/"
                f"{topic_suffix}"
            )

            # ==========================
            # Serialize message
            # ==========================
            payload = message.model_dump(mode="json")

            # ==========================
            # Publish
            # ==========================
            self.client.publish(
                topic,
                json.dumps(payload)
            )

            print(f"[PUBLISH_MESSAGE] Published to {topic}")

        except Exception as e:
            print(f"[PUBLISH_MESSAGE ERROR] Failed to publish message: {e}")

    #========================
    #MQTT functions
    #========================

    def on_connect(self, client, userdata, flags, rc):

        if rc == 0:
            print(f"[ON_CONNECT] Connected to MQTT broker: {self.broker}:{self.port}")

        else:
            print(f"[ON_CONNECT ERROR] Failed to connect to MQTT broker. Return code: {rc}")
            return

        # Refresh all topic/resource mappings
        self.update_information()

        # Subscribe to every resource namespace
        for resource_shell_id in self.RM.resource_shell_ids.keys():
            resource_topic = self.shell_id_to_topic[resource_shell_id]

            topic = f"{self.base_topic}/{resource_topic}/#"

            client.subscribe(topic)

            print(f"[ON_CONNECT] Subscribed to: {topic}")

    def on_message(self, client, userdata, msg):

        try:

            # ==========================
            # Parse MQTT topic
            # ==========================
            topic_info = self.parse_topic(msg.topic)

            resource_suffix = topic_info["resource_suffix"]
            topic_suffix = topic_info["topic_suffix"]

            # ==========================
            # Determine message type
            # ==========================
            reverse_map = self.reverse_topic_maps.get(resource_suffix, {})

            message_type = reverse_map.get(topic_suffix)

            if message_type is None:
                print(f"[ON_MESSAGE ERROR] No message type mapping for suffix: {topic_suffix}")
                return

            # ==========================
            # Deserialize payload
            # ==========================
            payload_dict = json.loads(msg.payload.decode())

            parsed_message = message_type(**payload_dict)

            # ==========================
            # Update reachability
            # ==========================
            self.last_seen[resource_suffix] = datetime.now()

            # Optional:
            self.RM.resource_shell_ids[self.topic_to_shell_id[resource_suffix]] = MS.ResourceReachability.ACTIVE

            # ==========================
            # Dispatch handler
            # ==========================
            handler = self.handlers.get(message_type)

            if handler is not None:
                handler(self, parsed_message, topic_info)

            else:
                print(f"[ON_MESSAGE] No handler registered for {message_type}")

        except json.JSONDecodeError as e:
            print(f"[ON_MESSAGE ERROR] JSON decode error: {e}")

        except Exception as e:
            print(f"[ON_MESSAGE ERROR] MQTT message handling failed: {e}")

    def start_mqtt_connection(self):
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

        self.client.connect(self.broker, self.port)
        self.client.loop_start()

    def _watch_last_seen_loop(self):

        timeout = timedelta(minutes=1)
        check_interval = 10

        while self.watchdog_running:

            now = datetime.now()

            # ==========================
            # Check ALL known resources
            # ==========================
            for resource_id_short, resource_shell_id in self.topic_to_shell_id.items():

                # ---------------------------------
                # CASE 1: never seen before
                # ---------------------------------
                if resource_id_short not in self.last_seen:

                    print(f"[WATCHDOG] {resource_id_short} never seen → requesting update")

                    self._request_resource_update(resource_id_short)

                    continue

                last_time = self.last_seen[resource_id_short]

                # ---------------------------------
                # CASE 2: timeout
                # ---------------------------------
                if now - last_time > timeout:

                    print(f"[WATCHDOG] {resource_id_short} timed out")

                    self.RM.resource_shell_ids[resource_shell_id] = MS.ResourceReachability.UNREACHABLE

                    self._request_resource_update(resource_id_short)

            time.sleep(check_interval)

    def _request_resource_update(self, resource_suffix: str):

        try:

            request_topic = self.topic_maps[resource_suffix].get(MS.RequestMessage)

            if request_topic is None:
                print(f"[WATCHDOG ERROR] No request suffix for {resource_suffix}")
                return

            full_topic_update = (
                f"{self.base_topic}/"
                f"{resource_suffix}/"
                f"{request_topic}"
            )

            # Build request message
            msg = MS.RequestMessage(
                timestamp=datetime.now(),
                requested_topic_update=(
                    f"{self.base_topic}/"
                    f"{resource_suffix}/"
                    f"{self.topic_maps[resource_suffix][MS.StateMessage]}"
                ),
                resource_id=resource_suffix,
                seq_no=None
            )

            payload = msg.model_dump(mode="json")

            self.client.publish(
                full_topic_update,
                json.dumps(payload)
            )

            print(f"[WATCHDOG] Sent InfoRequest to {resource_suffix}")

        except Exception as e:
            print(f"[WATCHDOG ERROR] {e}")

#=========================
#Defining message handlers (should be done in the controller, but we do it here to test)
#=========================


def handle_job_result_message(controller: MQTTClientController,message,topic_info):

    resource_suffix = topic_info["resource_suffix"]

    actor_id = topic_info.get("actor_id","default")

    # =====================================
    # Convert MQTT suffix -> shell id
    # =====================================
    resource_shell_id = (controller.topic_to_shell_id[resource_suffix])

    # =====================================
    # Creating or updating the job_result data structure with the job_result from the actor
    # =====================================
    job_store = (controller.shared_handler_variable.setdefault("job_result", {}))

    resource_jobs = job_store.setdefault(resource_shell_id,{})

    resource_jobs[actor_id] = message

    print(f"[JOB RESULT] "f"{resource_suffix}/{actor_id}")

def handle_inventory_level_message(controller: MQTTClientController,message,topic_info):

    resource_suffix = topic_info["resource_suffix"]

    # =====================================
    # Convert MQTT suffix -> shell id
    # =====================================
    resource_shell_id = (controller.topic_to_shell_id[resource_suffix])

    # =====================================
    # Directly inserting the message into the data structure
    # =====================================
    controller.shared_handler_variable.setdefault("inventory",{})
    controller.shared_handler_variable["inventory"][resource_shell_id] = message.inventory

    print(f"[INVENTORY] "f"{resource_suffix} "f"updated inventory "f"{message.inventory}")

def handle_state_message(controller: MQTTClientController, message, topic_info):

    resource_suffix = topic_info["resource_suffix"]
    actor_id = topic_info.get("actor_id", "default")

    # =====================================
    # Convert MQTT suffix -> shell id
    # =====================================
    resource_shell_id = (controller.topic_to_shell_id[resource_suffix])

    # =====================================
    # Classify reachability
    # =====================================
    reachability = controller.classify_reachability(message)

    controller.RM.resource_shell_ids[resource_shell_id] = reachability

    # =====================================
    # Update last_seen
    # =====================================
    controller.last_seen[resource_suffix] = (datetime.now())

    # =====================================
    # Initialize shared state namespace
    # =====================================
    state_store = (controller.shared_handler_variable.setdefault("state", {}))

    resource_store = state_store.setdefault(resource_shell_id,{})

    # =====================================
    # Store actor state
    # =====================================
    resource_store[actor_id] = message.state

    print(f"[STATE] "f"{resource_suffix}/{actor_id} "f"→ {message.state}")

BROKER = "localhost"
MQTT_PORT = 1883
BASE_TOPIC = "AAUSmartLab/ProductionLine1" 
CLIENT_ID = "Controller_12345678"

AAS_BROKER = "localhost"
BASE_TOPIC = "AAUSmartLab/ProductionLine1"
AAS_PORT = "8081"
resources_url = "https://aausmartlab.org/Shells/Resources"

rm = RM(MQTT_PORT,BASE_TOPIC,AAS_BROKER,AAS_PORT,resources_url)

controller_mqtt = MQTTClientController(BROKER,MQTT_PORT,CLIENT_ID,BASE_TOPIC,rm)

controller_mqtt.register_handler(MS.StateMessage, handle_state_message)
controller_mqtt.register_handler(MS.JobResultMessage, handle_job_result_message)
controller_mqtt.register_handler(MS.InventoryLevelMessage,handle_inventory_level_message)

params = {
    "BitDiameter": 5.0,
    "DrillDepth": 50.0,
    "SpindleSpeed": 800.0,
    "SpindleFeed": 20.0,
    "TargetPosition": {
      "XPos": 20.0,
      "YPos": 10.0
    },
    "ComponentReference": "BottomCover_ALU"
}



command = MS.CommandMessage(timestamp=datetime.now(), resource_id="Drilling_12345678",actor_name="KUKAManipulator", skill="Drilling", skill_trigger="START", order_id="asudyg1123", job_id="job_XDDD", parameters=params, seq_no=5)


async def main():
    global main_loop
    main_loop = asyncio.get_running_loop()
    controller_mqtt.start_mqtt_connection()
    controller_mqtt.update_information()
    #print("============================================================================")
    #print(f"shell_id_to_topic: {controller_mqtt.shell_id_to_topic}")
    #print("============================================================================")
    #print(f"topic_to_shell_id: {controller_mqtt.topic_to_shell_id}")
    #print("============================================================================")
    #print(f"topic_maps: {controller_mqtt.topic_maps}")
    #print("============================================================================")
    #print(f"reverse_topic_maps: {controller_mqtt.reverse_topic_maps}")
    #print("============================================================================")

    controller_mqtt.publish_message(controller_mqtt.topic_to_shell_id["Drilling_12345678"],command)
    controller_mqtt.request_data(MS.InventoryLevelMessage)
    i = 0
    while i < 120:
        i = i+1
        print(controller_mqtt.shared_handler_variable)
        time.sleep(5)
    
    # Keep machine alive forever
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())