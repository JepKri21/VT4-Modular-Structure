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

        # ── Test hook for RR3 ────────────────────────────────────────
        # When `_drop_acks_remaining > 0`, the next outgoing ACK is
        # silently skipped (the counter decrements). Stations enable this
        # by setting the field after constructing the client. Leave at
        # zero in production — does nothing.
        self._drop_acks_remaining = 0

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

            for topic_suffix in list(self.subscribers.keys()):
                full_topic = f"{self.base_topic}/{self.client_id}/{topic_suffix}"
                client.subscribe(full_topic)
                print(f"Subscribed to {full_topic}")

        else:
            print(f"Connection failed: {rc}")

    def on_message(self, client, userdata, msg):
        try:
            topic = msg.topic
            payload = json.loads(msg.payload.decode())

            #print(f"Received on {topic}: {payload}")

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
            if auto_ack and getattr(parsed_message, "seq_no", None) is not None:
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

        data = message_model.model_dump(mode="json")

        # Inject a fresh outbound seq_no ONLY when the message doesn't
        # already carry one. Acknowledgements (and any other reply that
        # echoes a received seq_no) set their own value before calling
        # publish — overwriting it here would break the controller's
        # ACK→CMD matching.
        if hasattr(message_model, "seq_no") and data.get("seq_no") is None:
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
        # RR3 test hook: silently drop an ACK if a test asked us to.
        # controller_seq_no still advances so the next legitimate ACK
        # doesn't return SEQ_TOO_LOW for a non-test reason.
        if self._drop_acks_remaining > 0:
            self._drop_acks_remaining -= 1
            print(
                f"[TEST] dropping ACK for seq={received_seq_no} "
                f"(remaining drops: {self._drop_acks_remaining})"
            )
            self.controller_seq_no += 1
            return

        if self.controller_seq_no == received_seq_no:
            error_code = MS.AcknowledgementErrorCodes.NO_ERROR

        elif self.controller_seq_no > received_seq_no:
            error_code = MS.AcknowledgementErrorCodes.SEQ_TOO_LOW

        else:
            error_code = MS.AcknowledgementErrorCodes.SEQ_TOO_HIGH

        # Per the protocol, an ACK carries the seq_no of the telegram it
        # acknowledges — not our own expected counter. They match in the
        # happy path; on SEQ_TOO_LOW/HIGH they differ, and the controller
        # needs the received value to know which CMD failed.
        ack = MS.AcknowledgementMessage(
            timestamp=datetime.now(),
            resource_id=self.client_id,
            seq_no=received_seq_no,
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
        #We need to be able to make a list of acknowledgements or a queue that we ensure are acknowledged within some time
        #We may also have to limit which messages send acknowledges, since it will be a lot of messages
        #print(f"Received controller ACK: {msg}")

        if msg.seq_no == 0:
            print("Reset ACK received")
            self.controller_seq_no = 1
            return

        if msg.error_code in [
            MS.AcknowledgementErrorCodes.SEQ_TOO_LOW,
            MS.AcknowledgementErrorCodes.SEQ_TOO_HIGH
        ]:
            #print("Controller requested ACK reset")
            self.publish_reset_acknowledgement()

    # =========================================================
    # Start
    # =========================================================

    def start_mqtt_connection(self):
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

        self.client.connect(self.broker, self.port)
        self.client.loop_start()