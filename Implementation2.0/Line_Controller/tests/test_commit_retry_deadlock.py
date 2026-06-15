"""Regression tests for the commit-retry / re-plan deadlock fix.

No pytest dependency — run directly:

    python tests/test_commit_retry_deadlock.py

Covers the scheduler change that broke the ORD-7 <-> ORD-9 circular wait:
a BoP step whose actors can't be reserved must roll back to PENDING and return
(so the next tick re-plans and re-picks a free shuttle) rather than spin on a
stale reservation list forever — and must eventually abort via RuntimeError so
a genuinely stuck step can't wedge the line.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import aas_writer  # noqa: E402
# Stub the network fetch Scheduler.__init__ performs, before constructing one.
aas_writer.fetch_process_tracking_template = lambda *a, **k: None  # noqa: E305

import scheduler as scheduler_mod  # noqa: E402
from scheduler import Scheduler, PLAN_RETRY_BUDGET  # noqa: E402
from workorder_handler import StepStates  # noqa: E402
from occupancy_manager import OccupancyManager  # noqa: E402


# ── Minimal stubs ────────────────────────────────────────────────────────────

TARGET_IRI = "https://aausmartlab.org/Shells/Resources/BCPCBAssembler_x"
TARGET_TOPIC = "BCPCBAssembler_x"
ACTOR = "KUKAManipulator"
STEP_ID = "2x1"


class _StubMatcher:
    def match(self, info, excluded_resources=None):
        return [{"resource_id": TARGET_IRI, "skill_name": "Assemble"}]


class _StubRM:
    @staticmethod
    def topic_id_for_iri(iri):
        return iri.rsplit("/", 1)[-1]

    def actors_for_skill(self, iri, skill):
        return [ACTOR]

    def has_handoff(self, iri):
        return True


class _StubHandler:
    def __init__(self):
        self.workorder = {"OrderId": "ORD-VICTIM"}
        self.step_states: dict[str, StepStates] = {}
        self._info = {
            "Ingredient": "BottomCoverPCB",
            "ComponentReference": "https://aausmartlab.org/Shells/Assembly/BottomCoverPCB/x",
            "ComponentTypeReference": "https://aausmartlab.org/Shells/Assembly/BottomCoverPCB",
            "CapabilityReference": "https://aausmartlab.org/Submodels/Capability/Assemble",
            "InputIngredients": [],
            "Material": None,
        }

    def get_step_execution_info(self, step_id):
        return dict(self._info)

    def get_excluded_resources(self):
        return set()

    def update_step(self, step_id, state, resource=None):
        self.step_states[step_id] = state


def _make_scheduler():
    rm = _StubRM()
    # ResourceManager.topic_id_for_iri is called as Scheduler uses the *class*;
    # the real Scheduler does `ResourceManager.topic_id_for_iri`, so patch the
    # symbol the module resolved at import time.
    scheduler_mod.ResourceManager = _StubRM
    sched = Scheduler(
        controller=None,
        resource_manager=rm,
        matcher=_StubMatcher(),
        pre_process_planner=None,
        transport_planner=None,
        job_tracker=None,
        product_matcher=None,
        occupancy=OccupancyManager(controller=None),
        aas_server_base="http://localhost:8081",
    )
    # No transport: the single input is "already at target", so the only
    # reservation is the target endpoint itself. Isolates the commit branch
    # from the (separately tested) shuttle planner.
    def _no_transport(*a, **k):
        return (None, {}, [])

    sched._plan_arrival_for_input = _no_transport  # type: ignore[assignment]
    sched._refresh_inventory_for_step = lambda info: asyncio.sleep(0)  # type: ignore[assignment]
    return sched


def test_blocked_commit_rolls_back_and_does_not_raise():
    """Target held by another order -> step goes PENDING, no raise, counter=1."""
    sched = _make_scheduler()
    handler = _StubHandler()
    # Another order owns the assembler this step needs.
    sched.occupancy.commit("ORD-HOLDER", [(TARGET_TOPIC, ACTOR)])

    asyncio.run(sched._execute_bop_step(handler, {"step_id": STEP_ID}))

    assert handler.step_states.get(STEP_ID) == StepStates.PENDING, handler.step_states
    assert sched._commit_retry_counts[("ORD-VICTIM", STEP_ID)] == 1
    # We must NOT have stolen/committed anything for the victim.
    assert sched.occupancy.owner_of(TARGET_TOPIC, ACTOR) == "ORD-HOLDER"


def test_commit_retry_eventually_aborts():
    """A permanently-held target aborts via RuntimeError past the budget."""
    sched = _make_scheduler()
    handler = _StubHandler()
    sched.occupancy.commit("ORD-HOLDER", [(TARGET_TOPIC, ACTOR)])

    # Burn the budget. Each blocked attempt returns without raising...
    for _ in range(PLAN_RETRY_BUDGET):
        asyncio.run(sched._execute_bop_step(handler, {"step_id": STEP_ID}))
    assert sched._commit_retry_counts[("ORD-VICTIM", STEP_ID)] == PLAN_RETRY_BUDGET

    # ...the next attempt exceeds it and raises so run_order routes to recovery.
    raised = False
    try:
        asyncio.run(sched._execute_bop_step(handler, {"step_id": STEP_ID}))
    except RuntimeError as exc:
        raised = True
        assert TARGET_TOPIC in str(exc) and "ORD-HOLDER" in str(exc), str(exc)
    assert raised, "expected RuntimeError after exhausting PLAN_RETRY_BUDGET"
    # Counter cleared so a later attempt (e.g. after restart) starts fresh.
    assert ("ORD-VICTIM", STEP_ID) not in sched._commit_retry_counts


def test_free_target_commits_and_clears_counter():
    """When the target frees, commit succeeds and the retry counter resets."""
    sched = _make_scheduler()
    handler = _StubHandler()

    executed = {"plan": False, "cmd": False, "released": False}

    async def _exec_plan(*a, **k):
        executed["plan"] = True

    async def _exec_cmd(*a, **k):
        executed["cmd"] = True

    sched._print_and_execute_plan = _exec_plan  # type: ignore[assignment]
    sched._execute_bop_command = _exec_cmd  # type: ignore[assignment]

    # Pre-seed a stale counter to prove a successful commit clears it.
    sched._commit_retry_counts[("ORD-VICTIM", STEP_ID)] = 5

    asyncio.run(sched._execute_bop_step(handler, {"step_id": STEP_ID}))

    assert executed["plan"] and executed["cmd"], executed
    assert ("ORD-VICTIM", STEP_ID) not in sched._commit_retry_counts
    # Target released in the finally (no cargo held in this stubbed path).
    assert sched.occupancy.owner_of(TARGET_TOPIC, ACTOR) is None


class _NoMatchMatcher:
    def match(self, info, excluded_resources=None):
        return []


def test_unmatchable_step_aborts_instead_of_parking_forever():
    """A capability that never matches must abort via RuntimeError past the
    budget rather than park the step forever holding earlier cargo."""
    sched = _make_scheduler()
    sched.matcher = _NoMatchMatcher()
    handler = _StubHandler()

    # Each parked attempt returns without raising and bumps the plan-retry
    # counter (shared budget) — never stealing or committing anything.
    for _ in range(PLAN_RETRY_BUDGET):
        asyncio.run(sched._execute_bop_step(handler, {"step_id": STEP_ID}))
    assert sched._plan_retry_counts[("ORD-VICTIM", STEP_ID)] == PLAN_RETRY_BUDGET
    assert handler.step_states.get(STEP_ID) != StepStates.ASSIGNED

    raised = False
    try:
        asyncio.run(sched._execute_bop_step(handler, {"step_id": STEP_ID}))
    except RuntimeError as exc:
        raised = True
        assert "no matching resource" in str(exc), str(exc)
    assert raised, "expected RuntimeError after exhausting the retry budget"
    assert ("ORD-VICTIM", STEP_ID) not in sched._plan_retry_counts


def _run():
    tests = [
        test_blocked_commit_rolls_back_and_does_not_raise,
        test_commit_retry_eventually_aborts,
        test_free_target_commits_and_clears_counter,
        test_unmatchable_step_aborts_instead_of_parking_forever,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {t.__name__}: {exc!r}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run())
