import json
from datetime import datetime, timedelta
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

        # ── Fault-injection state (RR1 / RR2 / RR3 demos) ────────────
        # All three knobs default to "no effect". A station opts in by
        # calling `enable_fault_injection()` after registering its
        # normal subscribers; the dashboard then publishes to that
        # station's TestInjection topic to set these knobs at runtime.
        self._drop_acks_remaining = 0          # RR3 — skip next N ACKs
        self._next_incomplete = False          # RR2 — flip next result
        self._mute_until = None                # RR1 — suppress publishes

        # topic_suffix -> {
        #   "model": PydanticModel,
        #   "handler": function,
        #   "auto_ack": bool
        # }
        self.subscribers = {}

        # Fully-qualified topics outside this resource's own namespace (e.g. the
        # line-level Controller/ReloadConfig). Routed by per-topic paho
        # callbacks, NOT the suffix-based on_message dispatch, and re-subscribed
        # on every (re)connect. topic -> callback(client, userdata, msg).
        self.absolute_subscribers = {}

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

    def register_absolute_subscriber(self, topic, callback):
        """Subscribe to a fully-qualified topic outside this resource's
        namespace (e.g. the line-level Controller/ReloadConfig).

        The callback receives the raw paho message and bypasses the
        suffix-based on_message dispatch. Stored so it is re-subscribed on
        reconnect (see on_connect).
        """
        self.absolute_subscribers[topic] = callback
        self.client.message_callback_add(topic, callback)
        self.client.subscribe(topic)
        print(f"Registered absolute subscriber: {topic}")

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

            # Re-subscribe absolute (cross-namespace) topics on every connect so
            # a reconnect doesn't silently drop e.g. ReloadConfig handling.
            for topic, callback in self.absolute_subscribers.items():
                client.message_callback_add(topic, callback)
                client.subscribe(topic)
                print(f"Subscribed to {topic}")

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
        # RR1 test hook: while muted we simulate going offline. Drop the
        # message entirely — state, JobResult, ACK all included. The
        # controller's watchdog will probe and eventually publish
        # RESOURCE_OFFLINE.
        if self._mute_until is not None and datetime.now() < self._mute_until:
            print(
                f"[TEST MUTE] suppressed publish to {topic_suffix} "
                f"(silent until {self._mute_until.isoformat(timespec='seconds')})"
            )
            return

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

    # =========================================================
    # Fault Injection (RR1 / RR2 / RR3 demos)
    # =========================================================

    def enable_fault_injection(self) -> None:
        """Opt this station into runtime fault injection.

        Subscribes to <line>/<resource>/TestInjection. Auto-ack is False
        — the bridge / dashboard fires-and-forgets, no controller-style
        retry needed.
        """
        self.register_subscriber(
            topic_suffix="TestInjection",
            model=MS.TestInjectionMessage,
            handler=self._handle_test_injection,
            auto_ack=False,
        )

    def consume_next_incomplete(self) -> bool:
        """Behaviors call this when computing a JobResult: returns True
        (and clears the flag) if a test injection asked the next result
        to be INCOMPLETE. Returns False under normal operation.
        """
        if self._next_incomplete:
            self._next_incomplete = False
            return True
        return False

    def _handle_test_injection(self, msg) -> None:
        cmd = msg.command
        if cmd == MS.TestInjectionCommand.DROP_ACKS:
            n = max(1, msg.count or 1)
            self._drop_acks_remaining += n
            print(f"[TEST] will drop next {n} ACK(s)")
        elif cmd == MS.TestInjectionCommand.NEXT_INCOMPLETE:
            self._next_incomplete = True
            print("[TEST] next JobResult will be INCOMPLETE")
        elif cmd == MS.TestInjectionCommand.GO_SILENT:
            duration = max(1, msg.duration_s or 60)
            self._mute_until = datetime.now() + timedelta(seconds=duration)
            print(f"[TEST] muting publishes for {duration}s")
        else:
            print(f"[TEST] unknown command: {cmd}")