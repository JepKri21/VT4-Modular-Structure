import json
import paho.mqtt.client as mqtt
import sys
from pathlib import Path
import time
import asyncio
import threading
from datetime import datetime, timedelta


class CmdNoAckError(RuntimeError):
    """Raised when no AcknowledgementMessage arrives for a CMD after retries."""

sys.path.append(str(Path(__file__).resolve().parent.parent))

from ClassesAndBuilderMethods.InformationModels import MessageStructure as MS
from resource_manager import ResourceManager as RM
from product_property_matcher import ProductMatcher as PM


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

        # clean_session=False registers a persistent session with the
        # broker. The broker then queues any QoS>=1 messages addressed
        # to this client_id while we are disconnected and delivers them
        # on reconnect — so a dispatcher that releases WorkOrders while
        # the controller is offline doesn't lose them.
        self.client = mqtt.Client(
            client_id=self.client_id,
            clean_session=False,
            callback_api_version=mqtt.CallbackAPIVersion.VERSION1
        )

        # ── CMD ACK tracking (RR3 minimal) ──────────────────────────────────
        # Each CMD gets a per-resource seq_no; pending_acks holds the asyncio
        # Future the sender awaits. _loop is the event loop the sender runs
        # on — captured via set_event_loop() so the ACK handler (running on
        # paho's network thread) can resolve futures via call_soon_threadsafe.
        # alarm_publisher is optional and set by main.py after construction;
        # used to emit CMD_NO_ACK alarms when a retry exhausts.
        self._pending_acks: dict[tuple[str, int], asyncio.Future] = {}
        self._cmd_seq: dict[str, int] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self.alarm_publisher = None
        # Recovery hook: a callable(resource_id_short) fired when the
        # watchdog flips a resource to UNREACHABLE. Wired by main.py to
        # the OrderRecovery so in-flight orders using that resource get a
        # chance to reschedule rather than hang on a 180s CMD timeout.
        self.unreachable_callback = None

        # Internal ACK dispatch — keep this even if main.py never registers
        # a user handler for AcknowledgementMessage.
        self.register_handler(
            MS.AcknowledgementMessage,
            lambda _c, msg, info: self._handle_ack(msg, info),
        )

        self.watchdog_running = True
        self.watchdog_thread = threading.Thread(
            target=self._watch_last_seen_loop,
            daemon=True
        )
        self.watchdog_thread.start()

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Tell the controller which asyncio loop to schedule ACK
        resolutions on. Call this from main.py after the loop is running.
        """
        self._loop = loop

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
            
            #UPDATE TOPIC MAP to include the Occupancy and Cargo message type
            suffixes = self.RM.get_resource_MQTT_suffixes(resource_shell_id)
            self.topic_maps[resource_suffix] = {
                MS.CommandMessage: suffixes.get("CommandSuffix"),
                MS.StateMessage: suffixes.get("StateSuffix"),
                MS.RequestMessage: suffixes.get("InfoRequestSuffix"),
                MS.AlarmsMessage: suffixes.get("AlarmSuffix"),
                MS.AcknowledgementMessage: {"ResourceAcknowledgementSuffix": suffixes.get("ResourceAcknowledgementSuffix"), "ControllerAcknowledgementSuffix": suffixes.get("ControllerAcknowledgementSuffix") },
                MS.JobResultMessage: suffixes.get("JobResultSuffix"),
                MS.InventoryLevelMessage: suffixes.get("InventoryLevelSuffix"),
                MS.OccupancyMessage: suffixes.get("OccupancySuffix"),
                MS.CargoMessage: suffixes.get("CargoSuffix")
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

            shell_id = self.topic_to_shell_id[resource_suffix]
            prior_status = self.RM.resource_shell_ids.get(shell_id)
            self.RM.resource_shell_ids[shell_id] = MS.ResourceReachability.ACTIVE

            # If the watchdog had marked this resource UNREACHABLE and we
            # just heard from it again, auto-clear any active
            # RESOURCE_OFFLINE alarm so the dashboard reflects the recovery
            # without operator action.
            if (
                prior_status == MS.ResourceReachability.UNREACHABLE
                and self.alarm_publisher is not None
            ):
                self.alarm_publisher.clear(
                    category=MS.AlarmCategory.RESOURCE_OFFLINE,
                    resource_id=resource_suffix,
                    message=f"{resource_suffix} reconnected",
                )

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
        # When a resource goes silent for `timeout`, send an InfoRequest
        # and give it `probe_grace` to reply. Only declare RESOURCE_OFFLINE
        # if the probe also goes unanswered.
        probe_grace = timedelta(seconds=15)
        check_interval = 10

        # resource_id_short -> datetime when we last sent a probe. Cleared
        # implicitly: any new message updates last_seen past the probe
        # timestamp, so the comparison naturally resets.
        probed_at: dict[str, datetime] = {}

        while self.watchdog_running:

            now = datetime.now()

            for resource_id_short, resource_shell_id in self.topic_to_shell_id.items():

                # CASE 1: never heard from this resource — probe and wait.
                if resource_id_short not in self.last_seen:
                    if resource_id_short not in probed_at:
                        print(f"[WATCHDOG] {resource_id_short} never seen → probing")
                        self._request_resource_update(resource_id_short)
                        probed_at[resource_id_short] = now
                    continue

                last_time = self.last_seen[resource_id_short]
                if now - last_time <= timeout:
                    # Healthy. If we'd been probing, the reply cleared things up.
                    probed_at.pop(resource_id_short, None)
                    continue

                # Silence exceeds `timeout`.
                probe_time = probed_at.get(resource_id_short)
                if probe_time is None or last_time > probe_time:
                    # Either no probe outstanding, or the resource replied to
                    # a prior probe and went silent again. Send a fresh probe
                    # and wait one grace period before declaring offline.
                    print(f"[WATCHDOG] {resource_id_short} silent → probing")
                    self._request_resource_update(resource_id_short)
                    probed_at[resource_id_short] = now
                    continue

                # Probe outstanding. Still waiting within the grace window.
                if now - probe_time <= probe_grace:
                    continue

                # Probe went unanswered → declare offline.
                prior = self.RM.resource_shell_ids.get(resource_shell_id)
                print(
                    f"[WATCHDOG] {resource_id_short} did not reply to probe → "
                    f"marking UNREACHABLE"
                )
                self.RM.resource_shell_ids[resource_shell_id] = MS.ResourceReachability.UNREACHABLE

                # Fire the alarm exactly once per outage. The matching
                # auto-clear happens in on_message when the resource comes
                # back online.
                if (
                    prior != MS.ResourceReachability.UNREACHABLE
                    and self.alarm_publisher is not None
                ):
                    self.alarm_publisher.publish(
                        category=MS.AlarmCategory.RESOURCE_OFFLINE,
                        severity=MS.AlarmSeverity.ERROR,
                        message=(
                            f"{resource_id_short} unreachable for >"
                            f"{int((timeout + probe_grace).total_seconds())}s "
                            f"(probe unanswered)"
                        ),
                        resource_id=resource_id_short,
                    )

                if self.unreachable_callback is not None:
                    try:
                        self.unreachable_callback(resource_id_short)
                    except Exception as exc:
                        print(f"[WATCHDOG ERROR] callback failed: {exc}")

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

    #========================
    # CMD ACK retry (RR3 minimal)
    #
    # Follows the Intelligent Systems telegram protocol:
    #   - seq_no values 1..65535, wraps to 1 after 65535
    #   - seq_no 0 = counter reset, always accepted
    #   - default ACK timeout 1.0s
    #   - retransmissions reuse the same seq_no with retransmission=True;
    #     the station must re-ACK but not re-execute a duplicate seq_no
    #   - only one telegram in-flight per direction at a time (we serialize
    #     by awaiting each send_command_with_ack before the next)
    #========================

    _SEQ_NO_MAX = 65535

    def _next_seq_no(self, resource_suffix: str) -> int:
        current = self._cmd_seq.get(resource_suffix, 0)
        nxt = current + 1
        if nxt > self._SEQ_NO_MAX:
            nxt = 1
        self._cmd_seq[resource_suffix] = nxt
        return nxt

    def _handle_ack(self, msg, topic_info) -> None:
        """Resolve any pending future waiting on (resource, seq_no).

        Runs on paho's MQTT thread, so we hop back to the asyncio loop
        via call_soon_threadsafe before touching the Future.
        """
        if msg.seq_no is None:
            return
        key = (topic_info["resource_suffix"], msg.seq_no)
        future = self._pending_acks.get(key)
        if future is None or future.done() or self._loop is None:
            return
        self._loop.call_soon_threadsafe(future.set_result, msg)

    async def send_command_with_ack(
        self,
        resource_shell_id: str,
        command_message,
        *,
        timeout: float = 1.0,
        max_retries: int = 1,
    ):
        """Publish a CommandMessage and wait for its acknowledgement.

        On no-ack timeout, retransmits up to `max_retries` times — same
        seq_no, retransmission=True, otherwise an exact copy. Raises
        CmdNoAckError after the final attempt fails and publishes a
        CMD_NO_ACK alarm if an alarm_publisher has been attached.

        SEQ_TOO_LOW / SEQ_TOO_HIGH error codes still count as receipt
        confirmations — they only indicate counter drift. A future
        iteration will trigger a seq_no=0 reset telegram in response;
        for now we log and accept.
        """
        if self._loop is None:
            # Capture lazily so this works even when set_event_loop wasn't
            # called explicitly — provided we're inside a running loop.
            self._loop = asyncio.get_running_loop()

        resource_suffix = self.shell_id_to_topic[resource_shell_id]
        seq_no = self._next_seq_no(resource_suffix)
        cmd = command_message.model_copy(
            update={"seq_no": seq_no, "retransmission": False}
        )

        key = (resource_suffix, seq_no)
        for attempt in range(max_retries + 1):
            future: asyncio.Future = self._loop.create_future()
            self._pending_acks[key] = future
            try:
                # Retransmissions are byte-identical to the original except
                # for the retransmission flag — same seq_no, same payload.
                if attempt > 0:
                    cmd = cmd.model_copy(update={"retransmission": True})
                self.publish_message(resource_shell_id, cmd)
                ack = await asyncio.wait_for(future, timeout=timeout)
                if ack.error_code != MS.AcknowledgementErrorCodes.NO_ERROR:
                    print(
                        f"[ACK] {resource_suffix} seq={seq_no} "
                        f"returned {ack.error_code.value} — "
                        f"TODO: send seq_no=0 reset telegram"
                    )
                return ack
            except asyncio.TimeoutError:
                if attempt < max_retries:
                    print(
                        f"[ACK] no ack for {resource_suffix} seq={seq_no} "
                        f"after {timeout:.1f}s — retransmitting "
                        f"({attempt + 1}/{max_retries})"
                    )
                    continue
                message = (
                    f"no ACK from {resource_suffix} for CMD seq={seq_no} "
                    f"after {max_retries + 1} attempts"
                )
                print(f"[ACK ERROR] {message}")
                if self.alarm_publisher is not None:
                    self.alarm_publisher.publish(
                        category=MS.AlarmCategory.CMD_NO_ACK,
                        severity=MS.AlarmSeverity.ERROR,
                        message=message,
                        resource_id=resource_suffix,
                        order_id=getattr(cmd, "order_id", None),
                    )
                raise CmdNoAckError(message)
            finally:
                self._pending_acks.pop(key, None)


