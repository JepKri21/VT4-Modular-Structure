import json
from datetime import datetime
import paho.mqtt.client as mqtt
import sys
from pathlib import Path
import time
import asyncio

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

        self.topic_to_shell_id = {}

        # Incoming seq numbers from resources
        self.expected_resource_seq = {}

        self.last_state_update = {}

        self.pending_state_requests = {}

        # Outgoing seq numbers to resources
        self.controller_seq = {}

        #self.subscribers = {}
        self.handlers = {}
        self.topic_type_lookup = {}

        self.topic_maps = {}
        self.reverse_topic_maps = {}

        self.client = mqtt.Client(
            client_id=self.client_id,
            callback_api_version=mqtt.CallbackAPIVersion.VERSION1
        )

        self.register_handler(
        MS.StateMessage,
        MS.StateMessage,
        self.handle_state_message
        )


    def initialize_resources(self):
        #In theory, the MQTT class might actually be the one that should ping the resources
        resources = self.get_all_resource_readiness()

        print(f"Got Resources {resources}")

        for resource_id, status in resources.items():

            if status != "Active":
                continue

            if resource_id not in self.expected_resource_seq:
                self.expected_resource_seq[resource_id] = 1

            if resource_id not in self.controller_seq:
                self.controller_seq[resource_id] = 1
            
        return resources

    def register_handler(self,message_type,model,handler,auto_ack=True):
        self.handlers[message_type] = {
        "model": model,
        "handler": handler,
        "auto_ack": auto_ack
        }

    def on_connect(self, client, userdata, flags, rc):

        if rc != 0:
            print(f"Connection failed: {rc}")
            return

        print(f"{self.client_id} connected")

        self.RM.update_resource_availablility()
        resources = self.RM.resource_shell_ids

        for resource_id in resources:

            resource_name = self.get_resource_topic_id(resource_id, True)
            self.topic_to_shell_id[resource_name] = resource_id

            topic_map = self.generate_topic_map(resource_id)


            if not topic_map:
                continue
            
            print("Topic map made, now storing it and creating a reverse version")
            self.topic_maps[resource_id] = topic_map
            self.reverse_topic_maps[resource_id] = self.generate_reverse_topic_map(topic_map)


            # =====================================================
            # Build reverse lookup (IMPORTANT)
            # =====================================================

            #reverse_map = {}
            #for msg_type, suffix in topic_map.items():
            #    if isinstance(suffix, dict):
            #        continue
            #    if suffix:
            #        reverse_map[suffix] = msg_type

            #self.topic_type_lookup[resource_id] = reverse_map

            # =====================================================
            # Subscribe to actor-scoped topics
            # =====================================================

            actor_scoped = [
                MS.StateMessage,
                MS.JobResultMessage
            ]

            for msg_type in actor_scoped:

                suffix = topic_map.get(msg_type)

                if suffix is None:
                    continue

                topic = (
                    f"{self.base_topic}/"
                    f"{resource_name}/"
                    f"{suffix}/+"
                )

                client.subscribe(topic)
                print(f"Subscribed to {topic}")

            # =====================================================
            # Subscribe to resource-scoped topics
            # =====================================================

            resource_scoped = [
                MS.AlarmsMessage,
                MS.InventoryLevelMessage,
                MS.AcknowledgementMessage
            ]

            for msg_type in resource_scoped:

                suffix = topic_map.get(msg_type)

                if suffix is None:
                    continue

                if isinstance(suffix, dict):
                    suffix = suffix.get("ResourceAcknowledgementSuffix")

                topic = (
                    f"{self.base_topic}/"
                    f"{resource_name}/"
                    f"{suffix}"
                )

                client.subscribe(topic)
                print(f"Subscribed to {topic}")

    def parse_topic(self, topic):

        parts = topic.split("/")
        #This is quite hard coded, but I'm just tryna get something to work.
        result = {
            "line_id": parts[1],
            "resource_id": self.mqtt_to_aas_id(parts[2]),
            "topic_type": parts[3],
            "actor_id": parts[4] if len(parts) > 4 else None
        }

        # Actor scoped topics
        if len(parts) > 4:
            result["actor_id"] = parts[4]

        return result

    def get_resource_topic_id(self, resource_id, replace: bool = False):
        #It also needs to turn any "-"" into "_" because AAS does not accept - in the name
        if replace:
            return resource_id.rstrip("/").split("/")[-1].replace("-","_")
        else:
            return resource_id.rstrip("/").split("/")[-1]

    def mqtt_to_aas_id(self, mqtt_resource_id):

        aas_name = mqtt_resource_id.replace("_", "-")

        return f"https://aausmartlab.org/Shells/Resources/{aas_name}"

    def on_message(self, client, userdata, msg):
    
        try:
        
            # =====================================================
            # Decode payload
            # =====================================================
    
            topic = msg.topic
            payload = json.loads(msg.payload.decode())
    
            # =====================================================
            # Parse topic
            # =====================================================
    
            topic_info = self.parse_topic(topic)
    
            #resource_id = topic_info["resource_id"]
            topic_resource_id = topic_info["resource_id"]

            resource_id = self.topic_to_shell_id.get(
                topic_resource_id,
                topic_resource_id
            )
            topic_type = topic_info["topic_type"]
            actor_id = topic_info["actor_id"]
    
            # =====================================================
            # Find subscriber config
            # =====================================================
    
            reverse_map = self.reverse_topic_maps.get(resource_id)
            if not reverse_map:
                return

            #print("TOPIC:", topic)
            #print("PARSED:", topic_info)
            #print("REVERSE MAP:", self.topic_type_lookup.get(topic_info["resource_id"]))
            #print("Other REVERSE MAP:", reverse_map)

            if reverse_map is None:
                return

            message_type = reverse_map.get(topic_type)

            if message_type is None:
                return

            if message_type not in self.handlers:
                return

            config = self.handlers[message_type]

            model = config["model"]
            handler = config["handler"]
            auto_ack = config["auto_ack"]
    
            # =====================================================
            # Parse message model
            # =====================================================
    
            parsed_message = model(**payload)
    
            # =====================================================
            # Ensure communication tracking exists
            # =====================================================
    
            self.ensure_resource_tracking(resource_id)
    
            # =====================================================
            # Update communication timestamps
            # =====================================================
    
            self.last_seen[resource_id] = datetime.now()
    
            # =====================================================
            # Automatic acknowledgement handling
            # =====================================================
    
            if auto_ack and parsed_message.seq_no is not None:
            
                self.publish_acknowledgement(
                    resource_id=resource_id,
                    received_seq_no=parsed_message.seq_no
                )
    
            # =====================================================
            # Execute business logic handler
            # =====================================================
    
            handler(
                parsed_message,
                actor_id=actor_id,
                topic_info=topic_info
            )
    
        except Exception as e:
        
            print("MQTT parse error:", e)
    
    def ensure_resource_tracking(self, resource_id):

        if resource_id not in self.expected_resource_seq:
            self.expected_resource_seq[resource_id] = 1

        if resource_id not in self.controller_seq:
            self.controller_seq[resource_id] = 1

    def generate_topic_map(self,resource_id):
        suffixes = self.RM.get_resource_MQTT_suffixes(resource_id)
        time.sleep(0.3)
        #print("SUFFIXES:", suffixes)

        MESSAGE_TOPIC_MAP = {
            MS.CommandMessage: suffixes.get("CommandSuffix"),
            MS.StateMessage: suffixes.get("StateSuffix"),
            MS.RequestMessage: suffixes.get("InfoRequestSuffix"),
            MS.AlarmsMessage: suffixes.get("AlarmSuffix"),
            MS.AcknowledgementMessage: {"ResourceAcknowledgementSuffix": suffixes.get("ResourceAcknowledgementSuffix"), "ControllerAcknowledgementSuffix": suffixes.get("ControllerAcknowledgementSuffix") },
            MS.JobResultMessage: suffixes.get("JobResultSuffix"),
            MS.InventoryLevelMessage: suffixes.get("InventoryLevelSuffix")
        }

        return MESSAGE_TOPIC_MAP

    def generate_reverse_topic_map(self,forward):
        #print("FORWARD:", forward)
        reverse = {}
    
        for msg_type, suffix in forward.items():
            if isinstance(suffix, dict):
                continue
            if suffix:
                reverse[suffix] = msg_type
    
        return reverse

    def publish_message(self, resource_id, message):

        self.ensure_resource_tracking(resource_id)
        resource_name = self.get_resource_topic_id(resource_id,True)
        
        MESSAGE_TOPIC_MAP = self.generate_topic_map(resource_id)
        topic_suffix = MESSAGE_TOPIC_MAP[type(message)]

    

        if topic_suffix == None:
            print(f"The topic for the message type: {type(message)} is not provided for this resource: {resource_id}")
            return
        
        if type(message) == MS.AcknowledgementMessage:
            controller_ack_topic_suffix = topic_suffix.get("ControllerAcknowledgementSuffix")
            topic = (
            f"{self.base_topic}/"
            f"{resource_name}/"
            f"{controller_ack_topic_suffix}"
            )
        else:
            topic = (
            f"{self.base_topic}/"
            f"{resource_name}/"
            f"{topic_suffix}"
            )
            
        #If the topic suffix is equal to {'ResourceAcknowledgementSuffix': 'ResourceAck', 'ControllerAcknowledgementSuffix': 'ControllerAck'}
        # It should only pick the one used for "ControllerAcknowledgementSuffix"
        
        data = message.model_dump(mode="json")


        if hasattr(message, "seq_no"):

            data["seq_no"] = self.controller_seq[resource_id]

            self.controller_seq[resource_id] += 1

        self.client.publish(
            topic,
            json.dumps(data)
        )

        print(f"Published to {topic}")
        #print(f"Published to {topic} with DATA: {data}")

    def publish_acknowledgement(self,resource_id,received_seq_no):
        #CURRENTLY THE SEQUENCE NUMBERS ARE ALWAYS TOO HIGH BECAUSE THE CONTROLLER DOES NOT SEE EVERY MESSAGE
        expected_seq = self.expected_resource_seq[resource_id]

        if expected_seq == received_seq_no:
            error_code = MS.AcknowledgementErrorCodes.NO_ERROR
            self.expected_resource_seq[resource_id] += 1

        elif expected_seq > received_seq_no:
            error_code = MS.AcknowledgementErrorCodes.SEQ_TOO_LOW

        else:
            error_code = MS.AcknowledgementErrorCodes.SEQ_TOO_HIGH

        ack = MS.AcknowledgementMessage(
            timestamp=datetime.now(),
            resource_id=self.client_id,
            seq_no=expected_seq,
            error_code=error_code
        )

        self.publish_message(resource_id, ack)

    def publish_reset_acknowledgement(self, resource_id):

        self.expected_resource_seq[resource_id] = 1

        ack = MS.AcknowledgementMessage(
            timestamp=datetime.now(),
            resource_id=self.client_id,
            seq_no=0,
            error_code=MS.AcknowledgementErrorCodes.NO_ERROR
        )

        self.publish_message(resource_id, ack)

    def handle_resource_ack(self, msg):

        resource_id = msg.get("resource_id")

        print(f"Received ACK from {resource_id}")

        if msg.seq_no == 0:

            print("Reset ACK received")

            self.controller_seq[resource_id] = 1
            return

        if msg.error_code in [
            MS.AcknowledgementErrorCodes.SEQ_TOO_LOW,
            MS.AcknowledgementErrorCodes.SEQ_TOO_HIGH
        ]:

            print("Resource requested ACK reset")

            self.publish_reset_acknowledgement(resource_id)

    def request_topic_update(self,resource_id,requested_suffix):
        resource_name = self.get_resource_topic_id(resource_id,True)

        full_topic_to_request = f"{self.base_topic}/{resource_name}/{requested_suffix}"

        request = MS.RequestMessage(
            timestamp=datetime.now(),
            requested_topic_update=full_topic_to_request,
            resource_id=self.client_id
        )

        self.publish_message(resource_id, request)

    def check_resource_reachability(self,resource_id,timeout=5):

        topic_map = self.generate_topic_map(resource_id)

        state_suffix = topic_map.get(MS.StateMessage)

        if state_suffix is None:

            self.RM.resource_shell_ids[resource_id] = (MS.ResourceReachability.UNREACHABLE)

            return MS.ResourceReachability.UNREACHABLE

        # Remove old state timestamp
        self.last_state_update.pop(resource_id, None)

        # Request state update
        self.request_topic_update(resource_id=resource_id,requested_suffix=state_suffix)
        self.client.loop_write()
        time.sleep(0.05)

        start = time.time()

        while time.time() - start < timeout:
            time.sleep(0.5)
            if resource_id in self.last_state_update:

                return self.RM.resource_shell_ids.get(resource_id,MS.ResourceReachability.ACTIVE)

            time.sleep(0.1)

        self.RM.resource_shell_ids[resource_id] = (MS.ResourceReachability.UNREACHABLE)

        return MS.ResourceReachability.UNREACHABLE

    def get_all_resource_readiness(self):

        result = {}

        for resource_id in list(self.RM.resource_shell_ids.keys()):
            print(f"Checking resource ID {resource_id} for reachability")

            result[resource_id] = (
                self.check_resource_reachability(resource_id)
            )

        return result

    def start_mqtt_connection(self):
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

        self.client.connect(self.broker, self.port)
        self.client.loop_start()

        time.sleep(1)
        self.initialize_resources()

    #==================
    # State handling logic (identitcal for all resources)
    #==================

    def handle_state_message(self, msg, actor_id=None, topic_info=None):
    
        short_id = topic_info["resource_id"]
    
        self.last_state_update[short_id] = datetime.now()
        self.last_seen[short_id] = datetime.now()

        inactive_states = [
            MS.PackMLState.STOPPED,
            MS.PackMLState.ABORTED,
            MS.PackMLState.STOPPING,
            MS.PackMLState.ABORTING,
            MS.PackMLState.CLEARING
        ]

        if msg.state in inactive_states:
            self.RM.resource_shell_ids[short_id] = MS.ResourceReachability.INACTIVE
        else:
            self.RM.resource_shell_ids[short_id] = MS.ResourceReachability.ACTIVE




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
    
 
    controller_mqtt.publish_message(controller_mqtt.mqtt_to_aas_id("Drilling_12345678"),command)


    #machine.active_alarms = [51,62]
    # Keep machine alive forever
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
