"""Order-restart recovery policy.

When a step fails for any of the four reasons we care about (CMD ACK
exhausted, JobResult timeout, JobResult INCOMPLETE, or the resource
went offline mid-execution), the scheduler calls
`OrderRecovery.handle_failure(...)`. This module decides whether to:

  - restart the whole order with the failed resource excluded, or
  - abort the order and raise a NO_ALTERNATIVE alarm.

It also marks any stuck cargo in the occupancy ledger before releasing
the non-stuck reservations. Per design decision in the resilience plan:

  - reschedule granularity = whole-order restart, not per-step
  - stuck cargo = keep the actor reserved as STUCK, operator must
    physically clear the part and publish a ClearStuckCargo message

Recovery is intentionally state-light. All persistent state (attempt
count, excluded resources, step states) lives on the WorkOrderHandler.
This module owns only the *policy*: when to restart, when to give up.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ClassesAndBuilderMethods.InformationModels import MessageStructure as MS

if TYPE_CHECKING:
    from capability_matcher import CapabilityMatcher
    from controller_alarms import ControllerAlarmPublisher
    from occupancy_manager import OccupancyManager
    from workorder_handler import WorkOrderHandler


MAX_ATTEMPTS = 3


class RecoveryReason(str, enum.Enum):
    CMD_NO_ACK = "CMD_NO_ACK"
    JOB_TIMEOUT = "JOB_TIMEOUT"
    JOB_INCOMPLETE = "JOB_INCOMPLETE"
    RESOURCE_OFFLINE = "RESOURCE_OFFLINE"


class RecoveryAction(str, enum.Enum):
    RESTART = "RESTART"
    ABORT = "ABORT"


@dataclass
class RecoveryDecision:
    action: RecoveryAction
    attempt: int
    excluded_resources: list[str]


class OrderRecovery:
    def __init__(
        self,
        *,
        capability_matcher: "CapabilityMatcher",
        occupancy: "OccupancyManager",
        alarm_publisher: "ControllerAlarmPublisher",
    ) -> None:
        self.matcher = capability_matcher
        self.occupancy = occupancy
        self.alarms = alarm_publisher

    def handle_failure(
        self,
        *,
        handler: "WorkOrderHandler",
        reason: RecoveryReason,
        failed_resource_iri: str | None,
        failed_resource_topic: str | None,
        failed_step_info: dict | None,
        detail: str,
    ) -> RecoveryDecision:
        """Run the full recovery flow for one failure.

        Args:
            handler: the WorkOrderHandler of the failing order.
            reason: which detection path triggered the failure.
            failed_resource_iri: shell IRI of the resource that failed
                (None if the failure can't be attributed to one).
            failed_resource_topic: topic id of the same resource — used
                for alarm payloads only.
            failed_step_info: get_step_execution_info() of the failed
                step, so we can check if an alternative exists.
            detail: human-readable detail line for the alarm payload.
        """
        order_id = handler.workorder["OrderId"]

        # 1. Raise the cause alarm so the operator sees what broke.
        self._publish_cause_alarm(reason, order_id, failed_resource_topic, detail)

        # 2. Anything this order has cargo on must stay reserved as STUCK
        #    so a future order doesn't try to use a physically-loaded actor.
        #    The non-cargo reservations are released so other orders can move.
        stuck = self.occupancy.stuck_pairs_for_order(order_id)
        for resource_id, actor_name in stuck:
            self.occupancy.mark_stuck(resource_id, actor_name)
            self.alarms.publish(
                category=MS.AlarmCategory.STUCK_CARGO,
                severity=MS.AlarmSeverity.WARNING,
                message=(
                    f"{resource_id}/{actor_name} holding cargo from failed "
                    f"order {order_id} — operator must clear manually"
                ),
                resource_id=resource_id,
                actor_name=actor_name,
                order_id=order_id,
            )
        # release_one() is a no-op when cargo is present, so the stuck
        # ones stay claimed; the rest free up.
        self.occupancy.release(order_id)

        # 3. Decide: restart or abort.
        attempt = handler.get_attempt_count()
        if attempt >= MAX_ATTEMPTS:
            self._publish_no_alternative(
                order_id,
                failed_resource_topic,
                f"max attempts ({MAX_ATTEMPTS}) reached",
            )
            return RecoveryDecision(
                action=RecoveryAction.ABORT,
                attempt=attempt,
                excluded_resources=sorted(handler.get_excluded_resources()),
            )

        # 4. If we can attribute the failure to a specific resource, check
        #    whether the matcher has an alternative once that one is
        #    excluded. Without a failed_resource_iri (e.g. an INCOMPLETE
        #    result where the resource is still healthy) we still let the
        #    restart proceed — same resource is allowed to try again.
        #
        #    A restart normally excludes the resource that just failed so the
        #    matcher reaches for a different one. We override that to None when
        #    the failed resource is the ONLY provider (see below).
        exclude_on_restart: str | None = failed_resource_iri
        if failed_resource_iri and failed_step_info:
            tentative_excluded = handler.get_excluded_resources() | {
                failed_resource_iri
            }
            alternatives = self.matcher.match(
                failed_step_info, excluded_resources=tentative_excluded
            )
            if not alternatives:
                # The failed resource is the sole provider for this step.
                # Excluding it would guarantee an immediate re-abort and strand
                # the order's cargo on the line — even when the failure is
                # transient (e.g. a station that wasn't subscribed yet and
                # missed its CMD window, which is exactly the CMD_NO_ACK case).
                # The MAX_ATTEMPTS gate above has already passed, so give the
                # same resource another whole-order attempt instead of giving
                # up. A genuinely dead station simply fails again and trips
                # MAX_ATTEMPTS on the next pass, aborting then.
                print(
                    f"[recovery] {failed_resource_iri} is the sole provider for "
                    f"the failed step — retrying it instead of aborting "
                    f"(attempt {attempt + 1}/{MAX_ATTEMPTS})"
                )
                exclude_on_restart = None

        # 5. Restart: reset non-COMPLETED steps to PENDING and bump attempt.
        new_attempt = handler.reset_for_retry(
            failed_resource=exclude_on_restart
        )
        self.alarms.publish(
            category=MS.AlarmCategory.ORDER_RESTARTED,
            severity=MS.AlarmSeverity.INFO,
            message=(
                f"order {order_id} restarted (attempt {new_attempt}/"
                f"{MAX_ATTEMPTS}); reason={reason.value}; "
                f"excluded={sorted(handler.get_excluded_resources())}"
            ),
            resource_id=failed_resource_topic,
            order_id=order_id,
        )
        return RecoveryDecision(
            action=RecoveryAction.RESTART,
            attempt=new_attempt,
            excluded_resources=sorted(handler.get_excluded_resources()),
        )

    # ── alarm helpers ────────────────────────────────────────────────────
    def _publish_cause_alarm(
        self,
        reason: RecoveryReason,
        order_id: str,
        resource_topic: str | None,
        detail: str,
    ) -> None:
        category = {
            RecoveryReason.CMD_NO_ACK: MS.AlarmCategory.CMD_NO_ACK,
            RecoveryReason.JOB_TIMEOUT: MS.AlarmCategory.JOB_INCOMPLETE,
            RecoveryReason.JOB_INCOMPLETE: MS.AlarmCategory.JOB_INCOMPLETE,
            RecoveryReason.RESOURCE_OFFLINE: MS.AlarmCategory.RESOURCE_OFFLINE,
        }[reason]
        # CMD_NO_ACK + RESOURCE_OFFLINE already have their own publish
        # sites; firing again here would double-up. Skip if there's no
        # new info to add beyond what the original publisher emitted.
        if reason in {
            RecoveryReason.CMD_NO_ACK,
            RecoveryReason.RESOURCE_OFFLINE,
        }:
            return
        self.alarms.publish(
            category=category,
            severity=MS.AlarmSeverity.ERROR,
            message=detail,
            resource_id=resource_topic,
            order_id=order_id,
        )

    def _publish_no_alternative(
        self,
        order_id: str,
        resource_topic: str | None,
        detail: str,
    ) -> None:
        self.alarms.publish(
            category=MS.AlarmCategory.NO_ALTERNATIVE,
            severity=MS.AlarmSeverity.CRITICAL,
            message=f"order {order_id} halted: {detail}",
            resource_id=resource_topic,
            order_id=order_id,
        )
