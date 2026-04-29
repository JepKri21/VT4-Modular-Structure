import json
from datetime import datetime
import paho.mqtt.client as mqtt
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from InformationModels import MessageStructure as MS


class MQTTClientResource:
    def __init__(
        self,
        broker,
        port,
        client_id,
        base_topic,
    ):
        self.broker = broker
        self.port = port
        self.client_id = client_id
        self.base_topic = base_topic

        # Outgoing messages from resource
        self.station_seq_no = 1

        # Expected incoming seq_no from controller
        self.controller_seq_no = 1

        # topic_suffix -> {
        #   "model": PydanticModel,
        #   "handler": function,
        #   "auto_ack": bool
        # }
        self.subscribers = {}

        self.client = mqtt.Client(
            client_id=self.client_id,
            callback_api_version=mqtt.CallbackAPIVersion.VERSION1
        )

        # Built-in ACK handling
        self.register_subscriber(
            topic_suffix="ControllerAck",
            model=MS.AcknowledgementMessage,
            handler=self.handle_controller_ack,
            auto_ack=False
        )

    # =========================================================
    # Dynamic Registration
    # =========================================================

    def register_subscriber(
        self,
        topic_suffix,
        model,
        handler,
        auto_ack=True
    ):
        self.subscribers[topic_suffix] = {
            "model": model,
            "handler": handler,
            "auto_ack": auto_ack
        }

        print(f"Registered subscriber: {topic_suffix}")

        # If already connected, subscribe immediately
        full_topic = f"{self.base_topic}/{self.client_id}/{topic_suffix}"
        self.client.subscribe(full_topic)

    # =========================================================
    # MQTT Events
    # =========================================================

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print(f"{self.client_id} connected")

            for topic_suffix in self.subscribers:
                full_topic = f"{self.base_topic}/{self.client_id}/{topic_suffix}"
                client.subscribe(full_topic)
                print(f"Subscribed to {full_topic}")

        else:
            print(f"Connection failed: {rc}")

    def on_message(self, client, userdata, msg):
        try:
            topic = msg.topic
            payload = json.loads(msg.payload.decode())

            print(f"Received on {topic}: {payload}")

            topic_suffix = topic.split("/")[-1]

            if topic_suffix not in self.subscribers:
                print(f"No handler for topic: {topic_suffix}")
                return

            config = self.subscribers[topic_suffix]
            model = config["model"]
            handler = config["handler"]
            auto_ack = config["auto_ack"]

            parsed_message = model(**payload)

            # Automatic ACK handling
            if auto_ack and hasattr(parsed_message, "seq_no"):
                self.publish_acknowledgement(parsed_message.seq_no)

            # Custom business logic
            handler(parsed_message)

        except Exception as e:
            print("MQTT parse error:", e)

    # =========================================================
    # Publish
    # =========================================================

    def publish(self, topic_suffix, message_model):
        topic = f"{self.base_topic}/{self.client_id}/{topic_suffix}"

        data = message_model.model_dump()

        # Inject seq_no ONLY if model has it
        if hasattr(message_model, "seq_no"):
            data["seq_no"] = self.station_seq_no
            self.station_seq_no += 1

        self.client.publish(
            topic,
            json.dumps(data)
        )

        print(f"Published to {topic}")

    # =========================================================
    # Built-in ACK Logic
    # =========================================================

    def publish_acknowledgement(self, received_seq_no):
        if self.controller_seq_no == received_seq_no:
            error_code = MS.AcknowledgementErrorCodes.NO_ERROR

        elif self.controller_seq_no > received_seq_no:
            error_code = MS.AcknowledgementErrorCodes.SEQ_TOO_LOW

        else:
            error_code = MS.AcknowledgementErrorCodes.SEQ_TOO_HIGH

        ack = MS.AcknowledgementMessage(
            timestamp=datetime.now(),
            resource_id=self.client_id,
            seq_no=self.controller_seq_no,
            error_code=error_code
        )

        self.publish("ResourceAck", ack)

        self.controller_seq_no += 1

    def publish_reset_acknowledgement(self):
        self.station_seq_no = 1

        ack = MS.AcknowledgementMessage(
            timestamp=datetime.now(),
            resource_id=self.client_id,
            seq_no=0,
            error_code=MS.AcknowledgementErrorCodes.NO_ERROR
        )

        self.publish("ResourceAck", ack)

    def handle_controller_ack(self, msg):
        print(f"Received controller ACK: {msg}")

        if msg.seq_no == 0:
            print("Reset ACK received")
            self.controller_seq_no = 1
            return

        if msg.error_code in [
            MS.AcknowledgementErrorCodes.SEQ_TOO_LOW,
            MS.AcknowledgementErrorCodes.SEQ_TOO_HIGH
        ]:
            print("Controller requested ACK reset")
            self.publish_reset_acknowledgement()

    # =========================================================
    # Start
    # =========================================================

    def start_mqtt_connection(self):
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

        self.client.connect(self.broker, self.port)
        self.client.loop_start()