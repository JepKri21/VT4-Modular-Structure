#This should be a class that is able to run and keep track of multiple resources. It should have functions to add a resource, based on shell id
# and a function for starting that resource and one for terminating the resource.
import sys
from pathlib import Path
import time
import asyncio
from datetime import datetime
import random
import requests
import json
import Generic_Resource_Models as GRM
from Generic_Resource_Submodel_Parser import ResourceParser, AASResourceLoader

script_dir = Path(__file__).parent

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from ClassesAndBuilderMethods.MQTT.ResourceMQTT import MQTTClientResource
from ClassesAndBuilderMethods.PackML.PackMLMachineClass import StationBehavior, PackMLState,PackMLStateMachine
from ClassesAndBuilderMethods.InformationModels import MessageStructure as MS

#====== JUST FOR TESTING=========
BROKER = "localhost"
AAS_PORT = "8081"
SERVER_BASE = f"http://{BROKER}:{AAS_PORT}"  # your server base URL
SUBMODEL_ENDPOINT = f"{SERVER_BASE}/submodels"
SHELL_ENDPOINT = f"{SERVER_BASE}/shells"
#====== JUST FOR TESTING=========

class GenericResourceExecutor:

    def __init__(self, SERVER_BASE, SUBMODEL_ENDPOINT, SHELL_ENDPOINT, resource_shell_id):
        self.server_base = SERVER_BASE
        self.submodel_endpoint = SUBMODEL_ENDPOINT
        self.shell_endpoint = SHELL_ENDPOINT
        self.resource_shell_id = resource_shell_id
        self.resource_loader = AASResourceLoader(self.server_base, self.submodel_endpoint, self.shell_endpoint)
        self.resource_parser = ResourceParser()
        self.loaded_raw_resource = self.resource_loader.load(self.resource_shell_id)
        self.parsed_resource = self.resource_parser.parse(self.loaded_raw_resource)
        self.shell_id_short = None
        self.main_loop = None
        self.skill_executor = None
        self.actors = {}

        self.inventory_manager = InventoryManager(self.resource_loader,self.resource_parser,self.resource_shell_id,self.submodel_endpoint)

        self.refresh_resource()
        self.wait_for_communication_configuration()


    def attach_event_loop(self, loop):
        self.main_loop = loop

    def refresh_resource(self):

        raw_shell = self.resource_loader.read_shell(self.resource_shell_id)
        self.shell_id_short = raw_shell.id_short

        self.loaded_raw_resource = self.resource_loader.load(self.resource_shell_id)

        self.parsed_resource = self.resource_parser.parse(self.loaded_raw_resource)

    def wait_for_communication_configuration(self):
        while True:
            try:
                self.refresh_resource()
                communication = self.parsed_resource.get("Communication")
                if communication is None:
                    raise ValueError("Communication submodel not found")

                prefix = communication.production_line_prefix
                broker = communication.broker_id
                port = communication.broker_port

                if (prefix is not None and broker is not None and port is not None):
                    break

                print(
                    f"[{self.resource_shell_id}] "
                    f"Waiting for MQTT configuration..."
                )

            except Exception as e:

                print(
                    f"[{self.resource_shell_id}] "
                    f"Failed loading communication settings: {e}"
                )

            time.sleep(10)

        self.initialize_mqtt()

    def initialize_mqtt(self):

        communication = self.parsed_resource["Communication"]

        print(
            f"[{self.resource_shell_id}] "
            f"Connecting to MQTT broker {communication.broker_id}:{communication.broker_port} "
            f"(prefix={communication.production_line_prefix})",
            flush=True,
        )

        self.mqtt_client = MQTTClientResource(
            communication.broker_id,
            communication.broker_port,
            self.resource_shell_id.rsplit('/', 1)[-1],
            communication.production_line_prefix,
        )
        self.register_mqtt_handlers()

        self.mqtt_client.start_mqtt_connection()

        print(
            f"[{self.resource_shell_id}] "
            f"Connected to MQTT broker {communication.broker_id}:{communication.broker_port}",
            flush=True,
        )

        self.initialize_runtime()

    def register_mqtt_handlers(self):

        suffixes = self.parsed_resource["Communication"].suffixes
        prefix = self.parsed_resource["Communication"].production_line_prefix
        # Build the diagnostic base from the SAME identifier the MQTT client
        # actually subscribes/publishes with (client_id = the shell IRI's last
        # segment, e.g. "PhoneAssembler_<uuid>"), NOT shell_id_short (the AAS
        # id_short, e.g. "PhoneAssembler"). These differ when the IRI carries a
        # UUID; printing id_short here makes the log show a topic the resource
        # is not really listening on — defeating the whole point of this dump.
        base = f"{prefix}/{self.mqtt_client.client_id}"

        # Diagnostic: log every topic this resource will SUBSCRIBE to and the
        # ones it will PUBLISH to, fully-qualified. Grep the stdout for the
        # exact strings the controller is using and any mismatch jumps out
        # (e.g. 'PackMLState' vs 'State', 'InfoRequest' vs 'Request').
        print(f"[{self.resource_shell_id}] MQTT topics:")
        print(f"  SUBSCRIBE  CommandMessage  -> {base}/{suffixes.command_suffix}")
        print(f"  SUBSCRIBE  RequestMessage  -> {base}/{suffixes.info_request_suffix}")
        print(f"  PUBLISH    StateMessage    -> {base}/{suffixes.state_suffix}/<actor>")
        print(f"  PUBLISH    JobResult       -> {base}/{suffixes.job_result_suffix}/<actor>")
        inv = getattr(suffixes, "inventory_suffix", None)
        if inv:
            print(f"  PUBLISH    InventoryLevel  -> {base}/{inv}")

        self.mqtt_client.register_subscriber(
            suffixes.command_suffix,
            MS.CommandMessage,
            self.handle_command,
        )

        self.mqtt_client.register_subscriber(
            suffixes.info_request_suffix,
            MS.RequestMessage,
            self.handle_request,
        )

    def handle_command(self, msg: MS.CommandMessage):

        try:
            print(
                f"Received command "
                f"{msg.skill} "
                f"for actor "
                f"{msg.actor_name}"
            )

            actor_entry = self.actors.get(msg.actor_name)

            if not actor_entry:
                print(f"Unknown actor: {msg.actor_name}")
                return

            machine = actor_entry["machine"]
            behavior = actor_entry["behavior"]

            context = self.skill_executor.build_skill_context(
                msg.skill,
                msg
            )

            behavior.apply_context(context)

            asyncio.run_coroutine_threadsafe(
                machine.state_command_callback(msg.skill_trigger),
                self.main_loop
            )

        except Exception as e:
            print(f"[MQTT HANDLE_COMMAND ERROR] {e}")
            try:
                job_result_message = MS.JobResultMessage(
                    timestamp=datetime.now(),
                    resource_id=self.resource_shell_id,
                    order_id=getattr(msg, "order_id", None),
                    job_id=getattr(msg, "job_id", None),
                    ideal_cycle_time_ms=0,
                    actual_cycle_time_ms=0,
                    process_transformation=getattr(msg, "process_transformation", None),
                    result=MS.Result.INCOMPLETE,
                    quality=MS.Quality.NA,
                    output_parameters=None,
                )

                self.mqtt_client.publish(
                    f"{self.parsed_resource['Communication'].suffixes.job_result_suffix}/{msg.actor_name}",
                    job_result_message,
                )
            except Exception as publish_exc:
                print(f"[MQTT HANDLE_COMMAND RESULT ERROR] {publish_exc}")

            try:
                job_result_message = MS.JobResultMessage(
                    timestamp=datetime.now(),
                    resource_id=self.resource_shell_id,
                    order_id=getattr(msg, "order_id", None),
                    job_id=getattr(msg, "job_id", None),
                    ideal_cycle_time_ms=0,
                    actual_cycle_time_ms=0,
                    process_transformation=getattr(msg, "process_transformation", None),
                    result=MS.Result.INCOMPLETE,
                    quality=MS.Quality.NA,
                    output_parameters=[],
                )

                self.mqtt_client.publish(
                    f"{self.parsed_resource['Communication'].suffixes.job_result_suffix}/{msg.actor_name}",
                    job_result_message,
                )
            except Exception as publish_exc:
                print(f"[MQTT HANDLE_COMMAND RESULT ERROR] {publish_exc}")

    def handle_request(self, msg: MS.RequestMessage):
        print(f"[{self.resource_shell_id}] Info request for {msg.requested_topic_update}")
        suffixes = self.parsed_resource["Communication"].suffixes
        for actor_name, actor_entry in self.actors.items():
            machine = actor_entry["machine"]
            state_msg = MS.StateMessage(
                timestamp=datetime.now(),
                resource_id=self.shell_id_short,
                state=machine.state
            )
            self.mqtt_client.publish(
                f"{suffixes.state_suffix}/{actor_name}",
                state_msg
            )

    def initialize_runtime(self):

        # 1. Skill executor (shared across actors)
        self.skill_executor = SkillExecutor(self.parsed_resource)

        skills = self.parsed_resource["Skills"].skills

        # 2. Extract unique actors
        actor_set = set()

        for skill in skills.values():
            for actor in skill.actors:
                actor_set.add(actor)

        print(f"Detected actors: {actor_set}")

        # 3. Create behavior + state machine per actor
        for actor_name in actor_set:

            behavior = GenericStationBehavior(
                resource_id_short=self.shell_id_short,
                actor_name=actor_name,
                mqtt_client=self.mqtt_client,
                suffixes=self.parsed_resource["Communication"].suffixes,
                # All MQTT messages carry the SHORT id (not the full IRI) so
                # downstream metrics group cleanly. The full IRI lives in
                # the topic path; consumers can reconstruct it if needed.
                resource_id=self.shell_id_short,
                inventory_manager=self.inventory_manager
            )

            machine = PackMLStateMachine(behavior)

            self.actors[actor_name] = {
                "behavior": behavior,
                "machine": machine
            }

        print(f"[{self.resource_shell_id}] Runtime initialized with {len(self.actors)} actors")


class SkillExecutionContext:
    def __init__(self):
        self.skill_name = None
        self.skill = None

        self.capability = None
        self.process_transformation = None

        self.command = None

        # normalized validated parameters (flat or nested but clean)
        self.parameters = {}

        # precomputed execution metadata
        self.input_types = None
        self.output_types = None


class SkillExecutor:

    def __init__(self, parsed_resource):
        self.resource = parsed_resource
        self.skills = parsed_resource["Skills"].skills

    # ---------------------------
    # Skill resolution
    # ---------------------------
    def get_skill(self, skill_name: str):
        return self.skills.get(skill_name)

    def get_capability(self, skill: str):
        skill_obj = self.get_skill(skill)
        if not skill_obj:
            return None

        cap_id = skill_obj.capability.capability_type_id

        for value in self.resource.values():
            if hasattr(value, "capability_type") and value.capability_type == cap_id:
                return value

        return None

    # ---------------------------
    # Process transformation matching
    # ---------------------------
    def match_process_transformation(self, capability, command_pt):
        if not capability:
            return None

        cmd_in = command_pt.get("InputTypes") or []
        cmd_out = command_pt.get("OutputTypes") or []

        # Diagnostic: dump exactly what the CMD asked for AND what the
        # capability declares, so any mismatch is obvious from the log.
        print(
            f"[match-pt] cmd in={cmd_in!r} out={cmd_out!r}",
            flush=True,
        )
        for pt_name, pt in capability.process_transformations.items():
            print(
                f"[match-pt]   declared '{pt_name}': "
                f"in={pt.input_types!r} out={pt.output_types!r}",
                flush=True,
            )

        for pt in capability.process_transformations.values():

            cap_inputs = pt.input_types
            cap_outputs = pt.output_types

            if self._types_match(cap_inputs, cmd_in) and self._types_match(cap_outputs, cmd_out):
                return pt

        return None

    def _types_match(self, capability_types, command_types):
        # Both empty: identical (no-material transformation)
        if not capability_types and not command_types:
            return True
        # One empty, one not: mismatch
        if not capability_types or not command_types:
            return False

        for cap_type in capability_types:
            matched = any(cmd_type.startswith(cap_type) for cmd_type in command_types)
            if not matched:
                return False

        return True

    # ---------------------------
    # Parameter validation
    # supports:
    # - flat params
    # - nested collections
    # - range constraints
    # ---------------------------
    def validate_parameters(self, capability, parameters: dict):
        # The capability's Parameters block is the envelope: every parameter it
        # defines is a required runtime input the command must supply, EXCEPT
        # descriptors like OperationLabel (MultiLanguageProperty), which are
        # capability metadata, not command inputs. Each supplied value is range-
        # checked against its definition.
        definitions = capability.parameters or {}
        parameters = parameters or {}
        validated = {}

        for name, definition in definitions.items():

            param_type = getattr(definition, "parameter_type", None)

            # Descriptors are not command inputs — neither required nor validated.
            if param_type == "MultiLanguageProperty":
                continue

            if name not in parameters:
                raise ValueError(f"Missing parameter: {name}")

            value = parameters[name]

            # -------------------
            # Collection parameter (e.g. TargetPosition -> {XPos, YPos})
            # -------------------
            if param_type == "Collection":

                sub_defs = getattr(definition, "parameters", {}) or {}
                result = {}

                for sub_name, sub_def in sub_defs.items():

                    # Descriptors nested in a collection are likewise skipped.
                    if getattr(sub_def, "parameter_type", None) == "MultiLanguageProperty":
                        continue

                    if sub_name not in value:
                        raise ValueError(f"Missing sub-parameter: {sub_name}")

                    sub_value = value[sub_name]
                    self._check_range(sub_name, sub_value, sub_def)
                    result[sub_name] = sub_value

                validated[name] = result

            # -------------------
            # Flat parameter
            # -------------------
            else:
                self._check_range(name, value, definition)
                validated[name] = value

        return validated

    def _check_range(self, name, value, definition):
        min_val = getattr(definition, "min_value", None)
        max_val = getattr(definition, "max_value", None)
        if min_val is not None and max_val is not None:
            if not (min_val <= value <= max_val):
                raise ValueError(f"{name} out of range [{min_val}, {max_val}]: {value}")
        elif min_val is not None:
            if value < min_val:
                raise ValueError(f"{name} below minimum {min_val}: {value}")
        elif max_val is not None:
            if value > max_val:
                raise ValueError(f"{name} above maximum {max_val}: {value}")

    # ---------------------------
    # Build execution context
    # ---------------------------
    def build_skill_context(self, skill_name: str, command):

        context = SkillExecutionContext()
        context.skill_name = skill_name
        context.command = command

        skill = self.get_skill(skill_name)
        capability = self.get_capability(skill_name)

        if not skill or not capability:
            raise ValueError("Skill or capability not found")

        context.skill = skill
        context.capability = capability

        # Strict matching: every CMD must correspond to a ProcessTransformation
        # declared on the capability submodel. This catches accidental wrong
        # routing (e.g. a Drilling CMD for [Fuse] -> [Fuse]) instead of
        # silently executing it. Movement/inventory capabilities (Transport,
        # Handoff, Retrieve, Store) MUST therefore declare entries for every
        # CMD shape they accept — including degenerate ones like the empty
        # Transport leg (`[] -> []`). See each capability preset for the
        # explicit list.
        match = self.match_process_transformation(
            capability,
            command.process_transformation
        )

        if not match:
            raise ValueError("No matching process transformation")

        context.process_transformation = match
        context.input_types = match.input_types
        context.output_types = match.output_types

        context.parameters = self.validate_parameters(
            capability,
            command.parameters or {}
        )

        return context


class InventoryManager:

    STORE_CAPABILITY = "https://aausmartlab.org/Submodels/Capability/Store"
    RETRIEVE_CAPABILITY = "https://aausmartlab.org/Submodels/Capability/Retrieve"
    ASSEMBLE_CAPABILITY = "https://aausmartlab.org/Submodels/Capability/Assemble"

    def __init__(self, resource_loader: AASResourceLoader, resource_parser: ResourceParser, resource_shell_id, submodel_endpoint):
        self.resource_loader = resource_loader
        self.resource_parser = resource_parser
        self.resource_shell_id = resource_shell_id
        self.submodel_endpoint = submodel_endpoint

        self.inventory_parser = None
        self.inventory_model = None
        encoded_id = self.resource_loader._base64encode(f"{resource_shell_id}/Inventory")
        self.inventory_url = f"{self.submodel_endpoint}/{encoded_id}"

        self._lock = asyncio.Lock()

    def load(self):
        # Fetch only the inventory submodel — no need to reload the whole resource shell
        raw_inventory = self.resource_loader.read_submodel(
            f"{self.resource_shell_id}/Inventory"
        )
        self.inventory_parser = self.resource_parser.get_parser(GRM.SubmodelSemanticIDs.INVENTORY)
        self.inventory_model = self.inventory_parser.parse(raw_inventory)
        return self.inventory_model

    async def execute_inventory_effect(self, context):

        cap = context.capability.capability_type

        if cap == self.STORE_CAPABILITY:
            return await self.store_component(context)

        if cap == self.RETRIEVE_CAPABILITY:
            return await self.retrieve_component(context)

        if cap == self.ASSEMBLE_CAPABILITY:
            return await self.consume_assembled_inputs(context)

    async def consume_assembled_inputs(self, context):
        """Remove any assembly input that was sourced from this resource's own
        inventory (e.g. a Fuse from the assembler's feeder).

        Inputs not physically held here — the transported-in sub-assembly, or
        the previous partial assembly carried over as an input on a subsequent
        assemble step — aren't in this inventory, so find_component_slot_optional
        returns None for them and they're left untouched. Without this, the
        consumed fuse stays listed in the assembler's Inventory submodel forever
        and every new order's matcher picks the same instance again.
        """
        input_ids = context.command.process_transformation.get("InputTypes") or []
        output_ids = set(context.command.process_transformation.get("OutputTypes") or [])

        consumed = []
        async with self._lock:
            try:
                model = self.load()
            except Exception as e:
                # Assemblers that only combine transported-in parts (e.g. the final
                # PhoneAssembler) have no own feeder Inventory submodel — there is
                # nothing here to consume, so skip gracefully instead of failing the
                # job. Without this guard the missing submodel raises and the whole
                # assemble step is reported INCOMPLETE, aborting the order.
                print(f"[inventory] {self.resource_shell_id}: no Inventory submodel — nothing to consume ({e})")
                return consumed
            for component_id in input_ids:
                if not component_id or component_id in output_ids:
                    continue
                slot = self.find_component_slot_optional(model, component_id)
                if slot is None:
                    continue
                inventory_name, slot_id = slot
                self.write_slot_component(
                    inventory_name=inventory_name,
                    slot_id=slot_id,
                    component_id=None,
                )
                consumed.append(component_id)

        print(f"[inventory] Assemble consumed from own inventory: {consumed}")
        return consumed

    async def retrieve_component(self, context):

        component_id = context.command.process_transformation.get("OutputTypes") or []
        if not component_id:
            raise ValueError("No OutputTypes in process transformation for Retrieve")
        component_id = component_id[0]

        async with self._lock:
            model = self.load()
            inventory_name, slot_id = self.find_component_slot(model, component_id)

            self.write_slot_component(
                inventory_name=inventory_name,
                slot_id=slot_id,
                component_id=None
            )

        return component_id

    async def store_component(self, context):

        component_id = context.command.process_transformation.get("InputTypes") or []
        if not component_id:
            raise ValueError("No InputTypes in process transformation for Store")
        component_id = component_id[0]

        async with self._lock:
            model = self.load()
            inventory_name, slot_id = self.find_free_slot(model, component_id)

            self.write_slot_component(
                inventory_name=inventory_name,
                slot_id=slot_id,
                component_id=component_id
            )

        return slot_id

    def find_component_slot(self, model, component_id):
        slot = self.find_component_slot_optional(model, component_id)
        if slot is None:
            raise ValueError(f"Component not found: {component_id}")
        return slot

    def find_component_slot_optional(self, model, component_id):
        """Like find_component_slot but returns None instead of raising when the
        component isn't held in any of this resource's inventories."""
        for inv_name, inv in model.inventories.items():
            for slot_id, slot in inv.storage.items():
                if slot.component_id == component_id:
                    return inv_name, slot_id
        return None

    def find_free_slot(self, model, component_id):
        for inv_name, inv in model.inventories.items():

            supports = any(
                component_id.startswith(s)
                for s in inv.supported_components
            )

            if not supports:
                continue

            for slot_id, slot in inv.storage.items():
                if slot.component_id is None:
                    return inv_name, slot_id

        raise ValueError("No free slot found")

    def write_slot_component(self, inventory_name, slot_id, component_id):
        """Write one slot's ComponentShellReference on the AAS, in place.

        Targets the single ComponentShellReference element via the BaSyx
        submodel-elements endpoint and leaves every other field untouched —
        notably SlotReserved, which the Line Controller writes independently.
        This replaces upload(), whose whole-submodel PUT serialized a snapshot
        taken at load() and would clobber any field another writer had changed
        in between (the cross-order reservation race).

        component_id=None empties the slot. The reference *value* is dropped
        entirely rather than set to an empty-keys reference, which would crash
        the slot parser at value["keys"][0].
        """
        headers = {"Content-Type": "application/json"}
        path = (
            f"Inventories.{inventory_name}.StoredComponents."
            f"{slot_id}.ComponentShellReference"
        )
        url = f"{self.inventory_url}/submodel-elements/{path}"

        resp = requests.get(url, headers=headers)
        if not resp.ok:
            raise RuntimeError(f"GET {path} failed: {resp.status_code} {resp.text}")
        element = resp.json()

        if component_id is None:
            element.pop("value", None)
        else:
            element["value"] = {
                "type": "ExternalReference",
                "keys": [{"type": "GlobalReference", "value": str(component_id)}],
            }

        r = requests.put(url, headers=headers, data=json.dumps(element).encode("utf-8"))
        if r.status_code not in (200, 201, 204):
            raise RuntimeError(f"PUT {path} failed: {r.status_code} {r.text}")


class GenericStationBehavior(StationBehavior):

    def __init__(self, resource_id_short: str, actor_name: str, mqtt_client, suffixes, resource_id: str, inventory_manager: InventoryManager):
        self.actor_name = actor_name
        self.resource_id_short = resource_id_short
        self.mqtt_client = mqtt_client
        self.suffixes = suffixes
        self.resource_id = resource_id

        self.inventory_manager = inventory_manager

        # execution context (set per job)
        self.context = None

        # runtime outputs (always reset per job)
        self.result = None
        self.quality = None
        self.ideal_cycle_time = None
        self.actual_cycle_time = None

    # =========================================================
    # CONTEXT INJECTION (THIS is where SkillExecutor connects)
    # =========================================================
    def apply_context(self, context):
        """
        THIS is the ONLY entry point from SkillExecutor → behavior
        """
        self.context = context

        self.skill = context.skill_name
        self.capability = context.capability
        self.process_transformation = context.process_transformation
        self.parameters = context.parameters

    # =========================================================
    # PACKML STATES
    # =========================================================

    async def idle(self, machine):
        msg = MS.StateMessage(
            timestamp=datetime.now(),
            resource_id=self.resource_id,
            state=PackMLState.IDLE
        )
        self.mqtt_client.publish(f"{self.suffixes.state_suffix}/{self.actor_name}", msg)

    async def starting(self, machine):
        msg = MS.StateMessage(
            timestamp=datetime.now(),
            resource_id=self.resource_id_short,
            state=PackMLState.STARTING
        )
        self.mqtt_client.publish(f"{self.suffixes.state_suffix}/{self.actor_name}", msg)

        if not self.context:
            raise ValueError("No execution context applied")

        print(f"[{self.actor_name}] STARTING skill={self.skill}")
        print(f"ProcessTransformation={self.context.command.process_transformation}")
        print(f"Parameters={self.parameters}")

        await asyncio.sleep(1)

        await machine.transition_to(PackMLState.EXECUTE)

    async def execute(self, machine):

        msg = MS.StateMessage(
            timestamp=datetime.now(),
            resource_id=self.resource_id_short,
            state=PackMLState.EXECUTE
        )
        self.mqtt_client.publish(f"{self.suffixes.state_suffix}/{self.actor_name}", msg)

        if not self.context:
            raise ValueError("No execution context applied")

        try:
            await self.inventory_manager.execute_inventory_effect(self.context)
        except Exception as e:
            print(f"[{self.actor_name}] Job failed: {e}")
            self.ideal_cycle_time = 0
            self.actual_cycle_time = 0
            self.result = MS.Result.INCOMPLETE
            self.quality = MS.Quality.NA
            await machine.transition_to(PackMLState.COMPLETING)
            return

        self.ideal_cycle_time = self._estimate_cycle_time(self.parameters)
        self.actual_cycle_time = self.ideal_cycle_time + random.randint(100, 800)

        await asyncio.sleep(self.actual_cycle_time / 1000)

        self.result = MS.Result.COMPLETE
        self.quality = MS.Quality.GOOD

        await machine.transition_to(PackMLState.COMPLETING)

    async def completing(self, machine):
        msg = MS.StateMessage(
            timestamp=datetime.now(),
            resource_id=self.resource_id_short,
            state=PackMLState.COMPLETING
        )
        self.mqtt_client.publish(f"{self.suffixes.state_suffix}/{self.actor_name}", msg)

        job_result_message = MS.JobResultMessage(
            timestamp=datetime.now(),
            resource_id=self.resource_id,
            order_id=self.context.command.order_id,
            job_id=self.context.command.job_id,
            ideal_cycle_time_ms=self.ideal_cycle_time,
            actual_cycle_time_ms=self.actual_cycle_time,
            process_transformation=self.context.command.process_transformation,
            result=self.result,
            quality=self.quality,
            output_parameters=self._build_output_parameters()
        )

        self.mqtt_client.publish(
            f"{self.suffixes.job_result_suffix}/{self.actor_name}",
            job_result_message
        )

        await asyncio.sleep(1)
        await machine.transition_to(PackMLState.COMPLETE)

    async def resetting(self, machine):
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=self.resource_id_short, state=PackMLState.RESETTING)
        self.mqtt_client.publish(f"{self.suffixes.state_suffix}/{self.actor_name}", state_message)
        print("Resetting Assembler")

        self.context = None
        self.result = None
        self.quality = None
        self.ideal_cycle_time = None
        self.actual_cycle_time = None

        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.IDLE)

    async def stopping(self, machine):
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=self.resource_id_short, state=PackMLState.STOPPING)
        self.mqtt_client.publish(f"{self.suffixes.state_suffix}/{self.actor_name}", state_message)
        print("Stopping")
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.STOPPED)

    async def holding(self, machine):
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=self.resource_id_short, state=PackMLState.HOLDING)
        self.mqtt_client.publish(f"{self.suffixes.state_suffix}/{self.actor_name}", state_message)
        print("Holding")
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.HELD)

    async def unholding(self, machine):
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=self.resource_id_short, state=PackMLState.UNHOLDING)
        self.mqtt_client.publish(f"{self.suffixes.state_suffix}/{self.actor_name}", state_message)
        print("Unholding Assembler")
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.EXECUTE)

    async def suspending(self, machine):
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=self.resource_id_short, state=PackMLState.SUSPENDING)
        self.mqtt_client.publish(f"{self.suffixes.state_suffix}/{self.actor_name}", state_message)
        print("Suspending Assembler")
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.SUSPENDED)

    async def unsuspending(self, machine):
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=self.resource_id_short, state=PackMLState.UNSUSPENDING)
        self.mqtt_client.publish(f"{self.suffixes.state_suffix}/{self.actor_name}", state_message)
        print("Unsuspending Assembler")
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.EXECUTE)

    async def aborting(self, machine):
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=self.resource_id_short, state=PackMLState.ABORTING)
        self.mqtt_client.publish(f"{self.suffixes.state_suffix}/{self.actor_name}", state_message)
        print("Aborting Assembler")
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.ABORTED)

    async def clearing(self, machine):
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=self.resource_id_short, state=PackMLState.CLEARING)
        self.mqtt_client.publish(f"{self.suffixes.state_suffix}/{self.actor_name}", state_message)
        print("Clearing Assembler")

        self.context = None
        self.result = None
        self.quality = None
        self.ideal_cycle_time = None
        self.actual_cycle_time = None

        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.STOPPED)

    # =========================================================
    # CYCLE TIME ESTIMATION
    # TODO: Replace with a capability-specific model derived from
    #       the capability's RangeParameter definitions.
    # =========================================================
    def _estimate_cycle_time(self, parameters):
        # TODO: Replace with a capability-specific model derived from
        #       self.capability's RangeParameter definitions.
        return 3000 + len(parameters) * 500

    # =========================================================
    # OUTPUT PARAMETER BUILDER
    # =========================================================
    def _build_output_parameters(self):

        params = self.parameters
        cap_params = self.context.capability.parameters if self.context else {}

        elements = []

        for key, value in params.items():

            # flat parameter
            if not isinstance(value, dict):
                param_def = cap_params.get(key)
                unit = getattr(param_def, "unit", None) or "https://aausmartlab.org/Semantics/unitless"
                elements.append(
                    MS.PropertyElement(
                        id_short=key,
                        value=value,
                        semantic_id=unit
                    )
                )

            # nested parameter (Collection)
            else:
                sub_elements = []
                collection_def = cap_params.get(key)
                sub_params = getattr(collection_def, "parameters", {}) or {}

                for sub_key, sub_value in value.items():
                    sub_def = sub_params.get(sub_key)
                    unit = getattr(sub_def, "unit", None) or "https://aausmartlab.org/Semantics/unitless"
                    sub_elements.append(
                        MS.PropertyElement(
                            id_short=sub_key,
                            value=sub_value,
                            semantic_id=unit
                        )
                    )

                elements.append(
                    MS.CollectionElement(
                        id_short=key,
                        semantic_id="https://aausmartlab.org/Semantics/Parameters",
                        elements=sub_elements
                    )
                )

        return MS.CollectionElement(
            id_short="Parameters",
            semantic_id="https://aausmartlab.org/Semantics/Parameters",
            elements=elements
        )



#resource_executor = GenericResourceExecutor(SERVER_BASE, SUBMODEL_ENDPOINT, SHELL_ENDPOINT, resource_shell_id)

#print(resource_executor.parsed_resource)

resource_executor = None


if __name__ == "__main__":
     import argparse
     ap = argparse.ArgumentParser(description="Generic Resource Runner")
     ap.add_argument("--shell-id", required=True, help="Full AAS shell IRI for this resource")
     ap.add_argument("--server", default="http://localhost:8081", help="AAS server base URL")
     _args = ap.parse_args()

     _server = _args.server.rstrip("/")
     _sub_ep = f"{_server}/submodels"
     _shell_ep = f"{_server}/shells"

     async def main():
         global resource_executor
         resource_executor = GenericResourceExecutor(
             _server, _sub_ep, _shell_ep, _args.shell_id
         )
         loop = asyncio.get_running_loop()
         resource_executor.attach_event_loop(loop)
         await asyncio.Event().wait()

     asyncio.run(main())

