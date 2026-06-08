import json
from datetime import datetime

from ClassesAndBuilderMethods.InformationModels import MessageStructure as MS


class ControllerAlarmPublisher:
    """Publishes controller-originated alarms on a fixed topic.

    The topic lives outside the per-resource namespace because the
    controller has no AAS Communication submodel of its own:

        AAUSmartLab/<line_id>/Controller/Alarms

    The MES psql bridge subscribes to this topic and persists each alarm
    to the `alarms` table so the React dashboard can display it.
    """

    def __init__(self, mqtt_controller) -> None:
        # mqtt_controller is an MQTTClientController instance — we only
        # need its raw paho client and its base topic.
        self._client = mqtt_controller.client
        self._topic = f"{mqtt_controller.base_topic}/Controller/Alarms"

    def publish(
        self,
        category: MS.AlarmCategory,
        severity: MS.AlarmSeverity,
        message: str,
        *,
        resource_id: str | None = None,
        actor_name: str | None = None,
        order_id: str | None = None,
    ) -> None:
        alarm = MS.ControllerAlarmMessage(
            timestamp=datetime.now(),
            category=category,
            severity=severity,
            message=message,
            resource_id=resource_id,
            actor_name=actor_name,
            order_id=order_id,
        )
        payload = alarm.model_dump(mode="json")
        self._client.publish(self._topic, json.dumps(payload))
        print(
            f"[ALARM] {category.value}/{severity.value} "
            f"resource={resource_id} actor={actor_name} order={order_id}: {message}"
        )

    def clear(
        self,
        category: MS.AlarmCategory,
        *,
        resource_id: str | None = None,
        actor_name: str | None = None,
        order_id: str | None = None,
        message: str = "auto-cleared",
    ) -> None:
        """Mark active alarms matching (category, resource_id, actor_name,
        order_id) as resolved. The bridge translates this into an UPDATE
        on rows where cleared_at IS NULL, instead of inserting a new row.
        """
        alarm = MS.ControllerAlarmMessage(
            timestamp=datetime.now(),
            category=category,
            severity=MS.AlarmSeverity.INFO,
            message=message,
            resource_id=resource_id,
            actor_name=actor_name,
            order_id=order_id,
            cleared=True,
        )
        payload = alarm.model_dump(mode="json")
        self._client.publish(self._topic, json.dumps(payload))
        print(
            f"[ALARM CLEAR] {category.value} "
            f"resource={resource_id} actor={actor_name} order={order_id}"
        )
